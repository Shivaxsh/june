// Only fixed AppleScript operations; the sole interpolated value is a validated hex id.
import AppKit
import Foundation

func emit(_ value: [String:Any]) -> Never {
    if let data = try? JSONSerialization.data(withJSONObject:value) { FileHandle.standardOutput.write(data) }
    exit(value["ok"] as? Bool == true ? 0 : 1)
}
func validID(_ id:String) -> Bool { id.range(of:"^[A-Fa-f0-9]{16}$",options:.regularExpression) != nil }
// A name to look up in the library. Letters, digits, spaces and a few marks only: no quote or
// backslash can reach the script text, so the value cannot end the AppleScript string.
func validQuery(_ q:String) -> Bool {
    !q.contains("\"") && !q.contains("\\") && q.range(of:"^[\\p{L}\\p{N} .,'&!+-]{1,80}$",options:.regularExpression) != nil
}
let controls:[String:String] = ["next":"next track", "previous":"previous track", "pause":"pause", "resume":"play", "status":"get player state"]
// Music can take several seconds to start playing after a cold launch: wait for it instead of reporting too early.
let untilPlaying = """
        repeat 20 times
            delay 0.5
            if player state is playing then exit repeat
        end repeat
"""
// "Previous" on the first song (or "next" on the last) stops Music. The person asked to hear a song,
// so start playback again and report what is really playing.
let skipThenPlay = """
        repeat 8 times
            delay 0.5
            if player state is playing then exit repeat
        end repeat
        if player state is not playing then
            play
            repeat 12 times
                delay 0.5
                if player state is playing then exit repeat
            end repeat
        end if
"""
let kinds:Set<String> = ["any","artist","album","song"]
if CommandLine.arguments.count == 2 && CommandLine.arguments[1] == "--self-test" {
    emit(["ok":validID("ABCDEF0123456789") && !validID("\"do shell script\"") && validQuery("Imagine Dragons") && validQuery("Beyoncé & JAY-Z") && !validQuery("x\" & do shell script \"y") && !validQuery("a\\b") && !validQuery("")])
}

// macOS attributes Automation consent to the responsible process. Re-exec as our own
// responsible process so the prompt and the remembered grant belong to "June Music",
// not to whichever terminal or editor started June. stdin is inherited unread.
func becomeResponsibleForSelf() {
    let marker = "JUNE_MUSIC_SELF_RESPONSIBLE"
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
    // Only reached if the exec failed.
    unsetenv(marker)
    arguments.forEach { free($0) }
}
becomeResponsibleForSelf()
guard CommandLine.arguments.count == 1,
      let bytes = try? FileHandle.standardInput.read(upToCount:4097), bytes.count <= 4096,
      let input = (try? JSONSerialization.jsonObject(with:bytes)) as? [String:Any],
      let operation = input["operation"] as? String else { emit(["ok":false]) }
var source:String
if operation == "permission" && Set(input.keys) == ["operation"] {
    // A real protected request: macOS asks (or refuses) here, so success means consent.
    source = "tell application \"Music\" to count user playlists"
} else if operation == "playlists" && Set(input.keys) == ["operation"] {
    source = """
    tell application "Music"
        set output to {}
        repeat with p in (get user playlists)
            if (count of output) is greater than or equal to 200 then exit repeat
            -- Only the person's own playlists: not Music's built-in lists ("Music",
            -- "Music Videos", folders, Genius), which are not something they chose.
            if special kind of p is none and name of p is not "June Queue" then set end of output to {persistent ID of p, name of p}
        end repeat
        return output
    end tell
    """
} else if operation == "play", Set(input.keys) == ["operation","playlistId"],
          let id = input["playlistId"] as? String, validID(id) {
    source = """
    tell application "Music"
        set choices to (user playlists whose persistent ID is "\(id.uppercased())")
        if (count of choices) is not 1 then error number -1728
        play item 1 of choices
    \(untilPlaying)
        set stateText to "not-playing"
        if player state is playing then set stateText to "playing"
        return {stateText, persistent ID of current playlist}
    end tell
    """
} else if let verb = controls[operation], Set(input.keys) == ["operation"] {
    source = """
    tell application "Music"
        \(verb)
    \(operation == "resume" ? untilPlaying : operation == "status" ? "" : operation == "pause" ? "        delay 0.6" : skipThenPlay)
        set stateText to "stopped"
        if player state is playing then set stateText to "playing"
        if player state is paused then set stateText to "paused"
        set trackName to ""
        set trackArtist to ""
        try
            set trackName to name of current track
            set trackArtist to artist of current track
        end try
        return {stateText, trackName, trackArtist}
    end tell
    """
} else if (operation == "find" || operation == "play-library"), Set(input.keys) == ["operation","query","what"],
          let query = input["query"] as? String, validQuery(query), let what = input["what"] as? String, kinds.contains(what) {
    let play = operation == "play-library"
    source = """
    tell application "Music"
        set q to "\(query)"
        set w to "\(what)"
        -- Search the library and the person's own playlists (playlist songs are not always in the library).
        set own to (get user playlists)
        set kindsToTry to {w}
        if w is "any" then set kindsToTry to {"artist", "album", "song"}
        set found to {}
        set kindText to "none"
        set labelText to ""
        repeat with k in kindsToTry
            set kk to (k as text)
            set found to {}
            if kk is "artist" then set found to (every track of library playlist 1 whose artist contains q)
            if kk is "album" then set found to (every track of library playlist 1 whose album contains q)
            if kk is "song" then set found to (every track of library playlist 1 whose name contains q)
            repeat with n from 1 to (count of own)
                set p to item n of own
                if special kind of p is none and name of p is not "June Queue" then
                    if kk is "artist" then set found to found & (every track of p whose artist contains q)
                    if kk is "album" then set found to found & (every track of p whose album contains q)
                    if kk is "song" then set found to found & (every track of p whose name contains q)
                end if
            end repeat
            if (count of found) > 0 then
                set kindText to kk
                set firstTrack to item 1 of found
                if kk is "artist" then set labelText to artist of firstTrack
                if kk is "album" then set labelText to album of firstTrack
                if kk is "song" then set labelText to name of firstTrack
                exit repeat
            end if
        end repeat
        -- The same song can sit in several playlists: keep each once, at most 100.
        set uniq to {}
        set seen to {}
        repeat with n from 1 to (count of found)
            if (count of uniq) is greater than or equal to 100 then exit repeat
            set t to item n of found
            set pid to persistent ID of t
            if seen does not contain pid then
                set end of seen to pid
                set end of uniq to t
            end if
        end repeat
        set total to count of uniq
        if kindText is "none" or \(play ? "false" : "true") then return {kindText, total, labelText, "", "", "", ""}
        -- Play through June's own queue playlist so the songs continue in order.
        if not (exists user playlist "June Queue") then make new user playlist with properties {name:"June Queue"}
        set queue to user playlist "June Queue"
        delete every track of queue
        set added to 0
        repeat with n from 1 to (count of uniq)
            duplicate (item n of uniq) to queue
            set added to added + 1
        end repeat
        play queue
    \(untilPlaying)
        set stateText to "not-playing"
        if player state is playing then set stateText to "playing"
        set trackName to ""
        set trackArtist to ""
        set listName to ""
        try
            set trackName to name of current track
            set trackArtist to artist of current track
            set listName to name of current playlist
        end try
        return {kindText, added, labelText, stateText, trackName, trackArtist, listName}
    end tell
    """
} else { emit(["ok":false]) }
var error:NSDictionary?
guard let script = NSAppleScript(source:source) else { emit(["ok":false]) }
let result = script.executeAndReturnError(&error)
if let error = error {
    let code = (error[NSAppleScript.errorNumber] as? NSNumber)?.intValue
    // The detail helps diagnose a script fault; the backend never shows or stores it.
    emit(["ok":false,"code":code == -1743 ? "automation-permission" : "music-unavailable","number":code ?? 0,"detail":String(((error[NSAppleScript.errorMessage] as? String) ?? "").prefix(200))])
}
if operation == "permission" { emit(["ok":true]) }
func text(_ i:Int) -> String { String((result.atIndex(i)?.stringValue ?? "").prefix(200)) }
if controls[operation] != nil { emit(["ok":true, "state":text(1), "track":text(2), "artist":text(3)]) }
if operation == "find" || operation == "play-library" {
    emit(["ok":true, "kind":text(1), "count":Int(result.atIndex(2)?.int32Value ?? 0), "label":text(3), "state":text(4), "track":text(5), "artist":text(6), "playlist":text(7)])
}
if operation == "play" {
    emit(["ok":true,"state":result.atIndex(1)?.stringValue ?? "unknown", "playlistId":result.atIndex(2)?.stringValue ?? ""])
}
var items:[[String:String]]=[]
if result.numberOfItems > 0 {
    for i in 1...min(result.numberOfItems,200) {
        guard let item = result.atIndex(i), let id = item.atIndex(1)?.stringValue,
              validID(id), let name = item.atIndex(2)?.stringValue, !name.isEmpty, name.count <= 200 else { emit(["ok":false]) }
        items.append(["id":id.uppercased(),"name":name])
    }
}
emit(["ok":true,"playlists":items])
