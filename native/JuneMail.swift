// June Mail: fixed operations on the Mail app. Values reach AppleScript only as Apple Event
// parameters of fixed handlers, never as script text, so no subject, body or address can run code.
import AppKit
import Foundation
import SQLite3

func emit(_ value: [String:Any]) -> Never {
    if let data = try? JSONSerialization.data(withJSONObject:value) { FileHandle.standardOutput.write(data) }
    exit(value["ok"] as? Bool == true ? 0 : 1)
}
func validAddress(_ a:String) -> Bool {
    a.count <= 254 && a.range(of:"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,24}$", options:.regularExpression) != nil
}
func validLine(_ s:String, _ limit:Int) -> Bool { s.count <= limit && s.range(of:"[\\x00-\\x1f\\x7f]", options:.regularExpression) == nil }
func validBody(_ s:String) -> Bool { s.count <= 20000 && s.range(of:"[\\x00-\\x08\\x0b\\x0c\\x0e-\\x1f\\x7f]", options:.regularExpression) == nil }
func fourCC(_ s:String) -> UInt32 { s.utf8.reduce(0) { ($0 << 8) | UInt32($1) } }

// macOS attributes Automation consent to the responsible process: become our own, so the grant belongs to "June Mail".
func becomeResponsibleForSelf() {
    let marker = "JUNE_MAIL_SELF_RESPONSIBLE"
    if getenv(marker) != nil { return }
    typealias Disclaim = @convention(c) (UnsafeMutablePointer<posix_spawnattr_t?>, Int32) -> Int32
    guard let symbol = dlsym(UnsafeMutableRawPointer(bitPattern: -2), "responsibility_spawnattrs_setdisclaim"),
          let path = Bundle.main.executablePath else { return }
    var attributes: posix_spawnattr_t? = nil
    guard posix_spawnattr_init(&attributes) == 0 else { return }
    defer { posix_spawnattr_destroy(&attributes) }
    guard posix_spawnattr_setflags(&attributes, Int16(POSIX_SPAWN_SETEXEC)) == 0,
          unsafeBitCast(symbol, to: Disclaim.self)(&attributes, 1) == 0 else { return }
    setenv(marker, "1", 1)
    var arguments: [UnsafeMutablePointer<CChar>?] = CommandLine.arguments.map { strdup($0) } + [nil]
    var pid: pid_t = 0
    _ = posix_spawn(&pid, path, nil, &attributes, &arguments, environ)
    unsetenv(marker)
    arguments.forEach { free($0) }
}

let source = """
on mailStatus()
    tell application "Mail"
        set names to name of every account
        set unread to unread count of inbox
        return {names, unread}
    end tell
end mailStatus

on composeMail(addresses, subjectText, bodyText, showIt)
    tell application "Mail"
        set msg to make new outgoing message with properties {subject:subjectText, content:bodyText, visible:showIt}
        tell msg
            repeat with a in addresses
                make new to recipient at end of to recipients with properties {address:(a as text)}
            end repeat
        end tell
        set readBack to ""
        repeat with r in (to recipients of msg)
            set readBack to readBack & (address of r) & ","
        end repeat
        if showIt then save msg
        -- Mail can number the first composed email 0, and may not have an id for a moment: wait briefly.
        set mid to missing value
        repeat 10 times
            try
                set mid to id of msg
            end try
            if mid is not missing value then exit repeat
            delay 0.2
        end repeat
        if mid is missing value then set mid to -1
        return {mid, subject of msg, content of msg, readBack}
    end tell
end composeMail

-- Line endings only: CRLF and CR become LF, then whitespace at the very start and end is trimmed.
-- Every space and line break inside the body must match exactly.
on normalizeBody(t)
    set saved to AppleScript's text item delimiters
    repeat with mark in {return & linefeed, return}
        set AppleScript's text item delimiters to (mark as text)
        set parts to text items of t
        set AppleScript's text item delimiters to linefeed
        set t to parts as text
    end repeat
    set AppleScript's text item delimiters to saved
    set edges to {space, tab, linefeed}
    repeat while (count of t) > 0 and edges contains (character 1 of t)
        if (count of t) is 1 then return ""
        set t to text 2 thru -1 of t
    end repeat
    repeat while (count of t) > 0 and edges contains (character -1 of t)
        if (count of t) is 1 then return ""
        set t to text 1 thru -2 of t
    end repeat
    return t
end normalizeBody

-- Send only if the composed email is still exactly the approved one: same To addresses (no Cc or Bcc),
-- no attachments, same subject, same body (line endings aside). Checked and sent in one step, so nothing can change it in between.
on sendChecked(composedId, expectedTo, expectedSubject, expectedBody)
    tell application "Mail"
        set found to (outgoing messages whose id is composedId)
        if (count of found) is 0 then error number -1728
        set msg to item 1 of found
        set gotTo to address of every to recipient of msg
        -- A composed email has no "mail attachment" elements (only received messages do): an attachment
        -- shows up inside its rich-text content as the object replacement character, checked below.
        set extra to (count of cc recipients of msg) + (count of bcc recipients of msg)
        set gotSubject to subject of msg
        set gotBody to content of msg
    end tell
    if extra is not 0 then error number 9001
    if (gotBody as text) contains (character id 65532) then error number 9001
    if (count of gotTo) is not (count of expectedTo) then error number 9001
    ignoring case
        repeat with a in gotTo
            if expectedTo does not contain {(a as text)} then error number 9001
        end repeat
        repeat with a in expectedTo
            if gotTo does not contain {(a as text)} then error number 9001
        end repeat
    end ignoring
    considering case
        if (gotSubject as text) is not expectedSubject then error number 9001
        if my normalizeBody(gotBody as text) is not my normalizeBody(expectedBody) then error number 9001
    end considering
    tell application "Mail" to send msg
    return "sent"
end sendChecked

on discardComposed(composedId)
    tell application "Mail"
        set found to (outgoing messages whose id is composedId)
        if (count of found) > 0 then close (item 1 of found) saving no
        return "discarded"
    end tell
end discardComposed

"""

func call(_ handler:String, _ args:[NSAppleEventDescriptor]) -> NSAppleEventDescriptor {
    var error:NSDictionary?
    guard let script = NSAppleScript(source:source), script.compileAndReturnError(&error) else { emit(["ok":false,"code":"mail-unavailable","detail":"compile"]) }
    let event = NSAppleEventDescriptor(eventClass:fourCC("ascr"), eventID:fourCC("psbr"), targetDescriptor:NSAppleEventDescriptor.null(),
                                       returnID:AEReturnID(kAutoGenerateReturnID), transactionID:AETransactionID(kAnyTransactionID))
    event.setParam(NSAppleEventDescriptor(string:handler.lowercased()), forKeyword:fourCC("snam"))
    let list = NSAppleEventDescriptor.list()
    for (i, a) in args.enumerated() { list.insert(a, at:i + 1) }
    event.setParam(list, forKeyword:fourCC("----"))
    let result = script.executeAppleEvent(event, error:&error)
    if let error = error {
        let code = (error[NSAppleScript.errorNumber] as? NSNumber)?.intValue ?? 0
        emit(["ok":false, "code": code == -1743 ? "automation-permission" : code == -1728 ? "not-found" : code == 9001 ? "changed" : "mail-unavailable", "number":code,
              "detail":String(((error[NSAppleScript.errorMessage] as? String) ?? "").prefix(200))])
    }
    return result
}
func str(_ d:NSAppleEventDescriptor?, _ limit:Int) -> String { String((d?.stringValue ?? "").prefix(limit)) }
func iso(_ d:NSAppleEventDescriptor?) -> String {
    guard let date = d?.dateValue else { return "" }
    return ISO8601DateFormatter().string(from:date)
}
func list(_ strings:[String]) -> NSAppleEventDescriptor {
    let l = NSAppleEventDescriptor.list()
    for (i, s) in strings.enumerated() { l.insert(NSAppleEventDescriptor(string:s), at:i + 1) }
    return l
}

// --- Mail's own local index ------------------------------------------------------------------------------
// Mail keeps an SQLite index of every message ("Envelope Index"). Reading it is instant even for a huge
// inbox, unlike Mail's scripting interface. Opened read-only; needs Full Disk Access for June Mail.
var mailRoot = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Mail")
func mailVersionFolder() -> URL? {
    let names = (try? FileManager.default.contentsOfDirectory(atPath:mailRoot.path)) ?? []
    let versions = names.filter { $0.range(of:"^V\\d+$", options:.regularExpression) != nil }.sorted { Int($0.dropFirst()) ?? 0 > Int($1.dropFirst()) ?? 0 }
    return versions.first.map { mailRoot.appendingPathComponent($0) }
}
func openIndex() -> OpaquePointer {
    guard let folder = mailVersionFolder() else {
        let blocked = (try? FileManager.default.contentsOfDirectory(atPath:mailRoot.path)) == nil
        emit(["ok":false, "code": blocked ? "disk-access" : "no-index"])
    }
    var db:OpaquePointer?
    let path = folder.appendingPathComponent("MailData/Envelope Index").path
    guard sqlite3_open_v2(path, &db, SQLITE_OPEN_READONLY, nil) == SQLITE_OK, let handle = db else { emit(["ok":false, "code":"disk-access"]) }
    sqlite3_busy_timeout(handle, 3000)
    return handle
}
func query(_ db:OpaquePointer, _ sql:String, _ binds:[Any] = []) -> [[String:Any]] {
    var statement:OpaquePointer?
    guard sqlite3_prepare_v2(db, sql, -1, &statement, nil) == SQLITE_OK else {
        emit(["ok":false, "code":"index-unreadable", "detail":String(String(cString:sqlite3_errmsg(db)).prefix(200))])
    }
    defer { sqlite3_finalize(statement) }
    let transient = unsafeBitCast(-1, to:sqlite3_destructor_type.self)
    for (i, value) in binds.enumerated() {
        if let v = value as? Int { sqlite3_bind_int64(statement, Int32(i + 1), Int64(v)) }
        else if let v = value as? Double { sqlite3_bind_double(statement, Int32(i + 1), v) }
        else if let v = value as? String { sqlite3_bind_text(statement, Int32(i + 1), v, -1, transient) }
    }
    var rows:[[String:Any]] = []
    while sqlite3_step(statement) == SQLITE_ROW {
        var row:[String:Any] = [:]
        for c in 0..<sqlite3_column_count(statement) {
            let name = String(cString:sqlite3_column_name(statement, c))
            switch sqlite3_column_type(statement, c) {
            case SQLITE_INTEGER: row[name] = Int(sqlite3_column_int64(statement, c))
            case SQLITE_FLOAT: row[name] = sqlite3_column_double(statement, c)
            case SQLITE_TEXT: row[name] = String(cString:sqlite3_column_text(statement, c))
            default: row[name] = NSNull()
            }
        }
        rows.append(row)
        if rows.count >= 2000 { break }
    }
    return rows
}
func columns(_ db:OpaquePointer, _ table:String) -> Set<String> {
    Set(query(db, "PRAGMA table_info(\(table))").compactMap { $0["name"] as? String })
}
// Messages in mailboxes whose address ends with INBOX (every account), newest first.
func indexRows(_ db:OpaquePointer, where extra:String, _ binds:[Any], limit:Int) -> [[String:Any]] {
    let m = columns(db, "messages")
    let deleted = m.contains("deleted") ? " AND m.deleted = 0" : ""
    let summary = m.contains("summary") && columns(db, "summaries").contains("summary") ? ", (SELECT s2.summary FROM summaries s2 WHERE s2.ROWID = m.summary) AS preview" : ", '' AS preview"
    // Gmail keeps each email once (in All Mail) and marks Inbox with a label, so an inbox email is one
    // stored in an INBOX mailbox or labelled with one.
    let ids = { (sql:String) in query(db, sql).compactMap { $0["id"] as? Int }.map(String.init).joined(separator:",") }
    let inbox = ids("SELECT ROWID AS id FROM mailboxes WHERE url LIKE '%/INBOX' OR url LIKE '%/Inbox'")
    // The label table's columns, found by name: one points at the message, one at the mailbox.
    let labelColumns = columns(db, "labels")
    let messageColumn = labelColumns.first { $0.lowercased().contains("message") }
    let boxColumn = labelColumns.first { $0.lowercased().contains("mailbox") }
    var condition = ""
    if !inbox.isEmpty {
        condition = "m.mailbox IN (\(inbox))"
        if let mc = messageColumn, let bc = boxColumn { condition += " OR m.ROWID IN (SELECT l.\(mc) FROM labels l WHERE l.\(bc) IN (\(inbox)))" }
        let found = query(db, "SELECT count(*) AS n FROM messages m WHERE (\(condition))").first?["n"] as? Int ?? 0
        if found == 0 { condition = "" }
    }
    if condition.isEmpty {
        // No inbox found: everything received, without Sent, Drafts, Outbox, Spam, Junk or Trash.
        let received = ids("SELECT ROWID AS id FROM mailboxes WHERE url NOT LIKE '%Sent%' AND url NOT LIKE '%Draft%' AND url NOT LIKE '%Outbox%' AND url NOT LIKE '%Spam%' AND url NOT LIKE '%Junk%' AND url NOT LIKE '%Trash%' AND url NOT LIKE '%SendLater%' AND url NOT LIKE '%Notes%'")
        if received.isEmpty { return [] }
        condition = "m.mailbox IN (\(received))"
    }
    let sql = """
    SELECT m.ROWID AS rowid, a.address AS address, a.comment AS name, s.subject AS subject, m.date_received AS received, m.read AS read\(summary)
    FROM messages m LEFT JOIN addresses a ON a.ROWID = m.sender LEFT JOIN subjects s ON s.ROWID = m.subject
    WHERE (\(condition))\(deleted)\(extra)
    ORDER BY m.date_received DESC LIMIT ?
    """
    return query(db, sql, binds + [limit]).map { row in
        let name = (row["name"] as? String ?? "").trimmingCharacters(in:.whitespaces)
        let address = row["address"] as? String ?? ""
        let date = Date(timeIntervalSince1970:Double(row["received"] as? Int ?? 0))
        return ["id":String(row["rowid"] as? Int ?? 0), "from": name.isEmpty ? address : "\(name) <\(address)>", "subject":String((row["subject"] as? String ?? "").prefix(300)),
                "date":ISO8601DateFormatter().string(from:date), "read":(row["read"] as? Int ?? 1) != 0, "preview":String((row["preview"] as? String ?? "").prefix(400))]
    }
}
// Recently sent emails whose full subject is exactly `subject`, with their raw source: stored in a Sent
// mailbox, or (Gmail) stored in All Mail and labelled with a Sent mailbox. Newest first, deleted ones left out.
let sentSourceLimit = 60000
func sentCandidates(_ db:OpaquePointer, subject:String, limit:Int) -> [[String:Any]] {
    let m = columns(db, "messages")
    let sent = query(db, "SELECT ROWID AS id FROM mailboxes WHERE url LIKE '%Sent%'").compactMap { $0["id"] as? Int }.map(String.init).joined(separator:",")
    if sent.isEmpty { return [] }
    var condition = "m.mailbox IN (\(sent))"
    let labelColumns = columns(db, "labels")
    if let mc = labelColumns.first(where: { $0.lowercased().contains("message") }), let bc = labelColumns.first(where: { $0.lowercased().contains("mailbox") }) {
        condition += " OR m.ROWID IN (SELECT l.\(mc) FROM labels l WHERE l.\(bc) IN (\(sent)))"
    }
    // Mail may keep "Re: " apart from the rest of the subject.
    let full = m.contains("subject_prefix") ? "(COALESCE(m.subject_prefix, '') || COALESCE(s.subject, ''))" : "COALESCE(s.subject, '')"
    let deleted = m.contains("deleted") ? " AND m.deleted = 0" : ""
    let rows = query(db, "SELECT m.ROWID AS rowid FROM messages m LEFT JOIN subjects s ON s.ROWID = m.subject WHERE (\(condition)) AND \(full) = ?\(deleted) ORDER BY m.date_received DESC, m.ROWID DESC LIMIT ?",
                     [subject, limit])
    return rows.compactMap { row in
        guard let rowid = row["rowid"] as? Int else { return nil }
        return ["id":String(rowid), "source":String((emlx(db, rowid) ?? "").prefix(sentSourceLimit))]
    }
}

// The .emlx file Mail stored for a message: <ROWID>.emlx (or .partial.emlx) inside its mailbox folder.
func emlx(_ db:OpaquePointer, _ rowid:Int) -> String? {
    guard let url = query(db, "SELECT b.url AS url FROM messages m JOIN mailboxes b ON b.ROWID = m.mailbox WHERE m.ROWID = ?", [rowid]).first?["url"] as? String,
          let parsed = URL(string:url), let host = parsed.host, let version = mailVersionFolder() else { return nil }
    var folder = version.appendingPathComponent(host)
    for part in parsed.path.split(separator:"/") { folder.appendPathComponent((String(part).removingPercentEncoding ?? String(part)) + ".mbox") }
    let wanted = ["\(rowid).emlx", "\(rowid).partial.emlx"]
    guard let walk = FileManager.default.enumerator(at:folder, includingPropertiesForKeys:nil, options:[.skipsHiddenFiles]) else { return nil }
    for case let file as URL in walk where wanted.contains(file.lastPathComponent) {
        guard let data = try? Data(contentsOf:file, options:.mappedIfSafe) else { return nil }
        // First line is the message length; the message follows, then Mail's own property list.
        guard let newline = data.firstIndex(of:10), let length = Int(String(decoding:data[..<newline], as:UTF8.self).trimmingCharacters(in:.whitespaces)) else { return nil }
        let start = data.index(after:newline)
        let body = data[start..<min(data.endIndex, start + min(length, 400000))]
        return String(decoding:body, as:UTF8.self)
    }
    return nil
}

// --- Self-test: argument guards, plus queries against a small fixture index shaped like this Mac's Mail ---
func fixtureTest() -> [String] {
    var failures:[String] = []
    func check(_ ok:Bool, _ what:String) { if !ok { failures.append(what) } }
    check(validAddress("me@example.com") && !validAddress("x\"@y.com") && !validAddress("a@b"), "addresses")
    check(validLine("Hello there", 200) && !validLine("a\nb", 200), "lines")
    check(validBody("Hi,\nthanks.\n") && !validBody(String(repeating:"x", count:20001)), "bodies")
    let root = FileManager.default.temporaryDirectory.appendingPathComponent("june-mail-fixture-\(getpid())")
    defer { try? FileManager.default.removeItem(at:root) }
    let version = root.appendingPathComponent("V10")
    try? FileManager.default.createDirectory(at:version.appendingPathComponent("MailData"), withIntermediateDirectories:true)
    var db:OpaquePointer?
    guard sqlite3_open(version.appendingPathComponent("MailData/Envelope Index").path, &db) == SQLITE_OK, let handle = db else { return ["fixture database"] }
    let schema = """
    CREATE TABLE mailboxes(ROWID INTEGER PRIMARY KEY, url TEXT);
    CREATE TABLE subjects(ROWID INTEGER PRIMARY KEY, subject TEXT);
    CREATE TABLE addresses(ROWID INTEGER PRIMARY KEY, address TEXT, comment TEXT);
    CREATE TABLE summaries(ROWID INTEGER PRIMARY KEY, summary TEXT);
    CREATE TABLE labels(message_id INTEGER, mailbox_id INTEGER);
    CREATE TABLE messages(ROWID INTEGER PRIMARY KEY, sender INTEGER, subject INTEGER, subject_prefix TEXT, date_received INTEGER, mailbox INTEGER, read INTEGER, deleted INTEGER, summary INTEGER);
    INSERT INTO mailboxes VALUES (1,'imap://G/INBOX'),(2,'imap://G/%5BGmail%5D/All%20Mail'),(3,'imap://G/%5BGmail%5D/Sent%20Mail'),(4,'imap://O/Sent%20Messages'),(5,'imap://G/SendLater');
    INSERT INTO subjects VALUES (1,'Hello'),(2,'Other');
    INSERT INTO addresses VALUES (1,'me@home.in','Me'),(2,'friend@x.com','Friend');
    INSERT INTO messages VALUES
      (10,1,1,'',500,2,1,0,NULL),   -- Gmail: sent, stored in All Mail, labelled Sent
      (11,1,1,'',400,4,1,0,NULL),   -- another account: sent, stored in its Sent mailbox
      (12,2,1,'',600,2,0,0,NULL),   -- received with the same subject, labelled Inbox: never a sent candidate
      (13,1,1,'Re: ',700,2,1,0,NULL), -- sent reply: Mail keeps "Re: " apart
      (14,1,1,'',800,2,1,1,NULL),   -- sent but deleted
      (15,1,2,'',900,2,1,0,NULL),   -- sent, different subject
      (16,1,1,'',950,5,1,0,NULL);   -- scheduled in SendLater: not sent yet
    INSERT INTO labels VALUES (10,3),(12,1),(13,3),(14,3),(15,3);
    """
    check(sqlite3_exec(handle, schema, nil, nil, nil) == SQLITE_OK, "fixture schema")
    sqlite3_close(handle)
    func write(_ folder:String, _ rowid:Int, _ message:String) {
        let dir = version.appendingPathComponent(folder)
        try? FileManager.default.createDirectory(at:dir, withIntermediateDirectories:true)
        let body = Data(message.utf8)
        try? (Data("\(body.count)\n".utf8) + body + Data("<?xml version=\"1.0\"?><plist/>".utf8)).write(to:dir.appendingPathComponent("\(rowid).emlx"))
    }
    write("G/[Gmail].mbox/All Mail.mbox/Data/1/Messages", 10, "To: friend@x.com\nSubject: Hello\n\nFirst body.")
    write("O/Sent Messages.mbox/Data/Messages", 11, "To: friend@x.com\nSubject: Hello\n\n" + String(repeating:"y", count:sentSourceLimit + 500))
    write("G/[Gmail].mbox/All Mail.mbox/Data/1/Messages", 12, "To: me@home.in\nSubject: Hello\n\nReceived.")
    write("G/[Gmail].mbox/All Mail.mbox/Data/1/Messages", 13, "To: friend@x.com\nSubject: Re: Hello\n\nReply.")
    let saved = mailRoot
    mailRoot = root
    defer { mailRoot = saved }
    let index = openIndex()
    let hello = sentCandidates(index, subject:"Hello", limit:30)
    check(hello.compactMap { $0["id"] as? String } == ["10", "11"], "sent: label and mailbox, newest first, no received/deleted/scheduled/other subject (got \(hello.compactMap { $0["id"] as? String }))")
    check((hello.first?["source"] as? String ?? "").hasSuffix("First body."), "sent: raw source without Mail's plist")
    check((hello.last?["source"] as? String ?? "").count == sentSourceLimit, "sent: each source bounded")
    check(sentCandidates(index, subject:"Re: Hello", limit:30).compactMap { $0["id"] as? String } == ["13"], "sent: split Re: prefix matched exactly")
    check(sentCandidates(index, subject:"hello", limit:30).isEmpty, "sent: subject is exact, case included")
    check(sentCandidates(index, subject:"Hello", limit:1).count == 1, "sent: limit")
    check(indexRows(index, where:"", [], limit:30).compactMap { $0["id"] as? String } == ["12"], "inbox: only the labelled inbox email")
    return failures
}

if CommandLine.arguments.count == 2 && CommandLine.arguments[1] == "--self-test" {
    let failures = fixtureTest()
    emit(failures.isEmpty ? ["ok":true] : ["ok":false, "failures":failures])
}
becomeResponsibleForSelf()

guard CommandLine.arguments.count == 1,
      let bytes = try? FileHandle.standardInput.read(upToCount:65537), bytes.count <= 65536,
      let input = (try? JSONSerialization.jsonObject(with:bytes)) as? [String:Any],
      let operation = input["operation"] as? String else { emit(["ok":false]) }
let keys = Set(input.keys)

switch operation {
case "status" where keys == ["operation"]:
    let r = call("mailStatus", [])
    var names:[String] = []
    if let l = r.atIndex(1), l.numberOfItems > 0 { for i in 1...min(l.numberOfItems, 20) { names.append(str(l.atIndex(i), 100)) } }
    emit(["ok":true, "accounts":names, "unread":Int(r.atIndex(2)?.int32Value ?? 0)])
case "inspect" where keys == ["operation"]:
    // Table and column names only, never content: to check the index layout this Mac's Mail uses.
    let db = openIndex()
    var tables:[String:[String]] = [:]
    for name in ["messages", "addresses", "subjects", "mailboxes", "summaries", "labels"] { tables[name] = columns(db, name).sorted() }
    // How many messages each mailbox holds, stored there or labelled: counts only, never content.
    var counts:[String:[Int]] = [:]
    let labelColumns = columns(db, "labels")
    let messageColumn = labelColumns.first { $0.lowercased().contains("message") }
    let boxColumn = labelColumns.first { $0.lowercased().contains("mailbox") }
    let hasLabels = messageColumn != nil && boxColumn != nil
    for row in query(db, "SELECT ROWID AS id, url FROM mailboxes") {
        guard let id = row["id"] as? Int, let url = row["url"] as? String else { continue }
        let stored = query(db, "SELECT count(*) AS n FROM messages WHERE mailbox = ?", [id]).first?["n"] as? Int ?? 0
        let labelled = hasLabels ? (query(db, "SELECT count(*) AS n FROM labels WHERE \(boxColumn!) = ?", [id]).first?["n"] as? Int ?? 0) : -1
        counts[String(url.split(separator:"/").last ?? "")] = [stored, labelled]
    }
    let boxes:[String] = query(db, "SELECT url FROM mailboxes").compactMap { row in (row["url"] as? String).map { String($0.split(separator:"/").last ?? "") } }
    emit(["ok":true, "tables":tables, "mailboxNames":Array(Array(Set(boxes)).sorted().prefix(40)), "counts":counts])
case "recent" where keys == ["operation","limit"]:
    guard let n = input["limit"] as? Int, (1...30).contains(n) else { emit(["ok":false]) }
    emit(["ok":true, "messages":indexRows(openIndex(), where:"", [], limit:n)])
case "search" where keys == ["operation","from","subject","limit"]:
    guard let f = input["from"] as? String, let s = input["subject"] as? String, let n = input["limit"] as? Int, (1...30).contains(n),
          validLine(f, 100), validLine(s, 100), !(f.isEmpty && s.isEmpty) else { emit(["ok":false]) }
    var extra = ""
    var binds:[Any] = []
    if !f.isEmpty { extra += " AND (a.address LIKE ? OR a.comment LIKE ?)"; binds += ["%\(f)%", "%\(f)%"] }
    if !s.isEmpty { extra += " AND s.subject LIKE ?"; binds.append("%\(s)%") }
    emit(["ok":true, "messages":indexRows(openIndex(), where:extra, binds, limit:n)])
case "read" where keys == ["operation","id","source"]:
    guard let id = input["id"] as? String, let rowid = Int(id), rowid > 0 else { emit(["ok":false]) }
    let db = openIndex()
    guard let row = indexRows(db, where:" AND m.ROWID = ?", [rowid], limit:1).first else { emit(["ok":false, "code":"not-found"]) }
    let raw:String = emlx(db, rowid) ?? ""
    emit(["ok":true, "from":row["from"] as? String ?? "", "subject":row["subject"] as? String ?? "", "date":row["date"] as? String ?? "", "to":"", "source":raw, "preview":row["preview"] as? String ?? ""])
case "compose" where keys == ["operation","to","subject","body","show"]:
    guard let to = input["to"] as? [String], (1...10).contains(to.count), to.allSatisfy(validAddress), let s = input["subject"] as? String, validLine(s, 200),
          let b = input["body"] as? String, validBody(b), let show = input["show"] as? Bool else { emit(["ok":false]) }
    let r = call("composeMail", [list(to), NSAppleEventDescriptor(string:s), NSAppleEventDescriptor(string:b), NSAppleEventDescriptor(boolean:show)])
    // -1 means Mail gave no id; 0 is a real id for the first email composed since Mail started.
    let composedId = (r.atIndex(1)?.descriptorType == typeSInt32 || r.atIndex(1)?.descriptorType == typeSInt16 || r.atIndex(1)?.descriptorType == typeSInt64) ? Int(r.atIndex(1)!.int32Value) : -1
    emit(["ok":true, "composedId":composedId, "subject":str(r.atIndex(2), 300), "body":str(r.atIndex(3), 21000), "to":str(r.atIndex(4), 3000)])
case "send" where keys == ["operation","composedId","to","subject","body"]:
    // The approved email travels with the send, and Mail's copy is re-checked against it in the same step.
    guard let id = input["composedId"] as? Int, id >= 0, let to = input["to"] as? [String], (1...10).contains(to.count), to.allSatisfy(validAddress),
          Set(to.map { $0.lowercased() }).count == to.count, let s = input["subject"] as? String, validLine(s, 200), !s.isEmpty,
          let b = input["body"] as? String, validBody(b), !b.isEmpty else { emit(["ok":false]) }
    let sent = str(call("sendChecked", [NSAppleEventDescriptor(int32:Int32(id)), list(to), NSAppleEventDescriptor(string:s), NSAppleEventDescriptor(string:b)]), 10)
    emit(["ok": sent == "sent", "sent": sent == "sent"])
case "discard" where keys == ["operation","composedId"]:
    guard let id = input["composedId"] as? Int, id >= 0 else { emit(["ok":false]) }
    _ = call("discardComposed", [NSAppleEventDescriptor(int32:Int32(id))])
    emit(["ok":true])
case "sent-candidates" where keys == ["operation","subject","limit"]:
    guard let subject = input["subject"] as? String, validLine(subject, 200), !subject.isEmpty, let n = input["limit"] as? Int, (1...30).contains(n) else { emit(["ok":false]) }
    emit(["ok":true, "messages":sentCandidates(openIndex(), subject:subject, limit:n)])
default:
    emit(["ok":false])
}
