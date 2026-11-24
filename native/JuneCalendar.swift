// The Mac's Calendar through EventKit. Fixed operations only: ask permission, list events in a
// time window, or add one event the person approved. Nothing is ever changed or deleted.
import EventKit
import Foundation

func emit(_ value: [String:Any]) -> Never {
    if let data = try? JSONSerialization.data(withJSONObject:value) { FileHandle.standardOutput.write(data) }
    exit(value["ok"] as? Bool == true ? 0 : 1)
}
if CommandLine.arguments.count == 2 && CommandLine.arguments[1] == "--self-test" {
    // No calendar access and no permission request.
    emit(["ok": true, "calendarOpened": false])
}

// macOS attributes Calendar consent to the responsible process. Re-exec as our own
// responsible process so the prompt and the grant belong to "June Calendar".
func becomeResponsibleForSelf() {
    let marker = "JUNE_CALENDAR_SELF_RESPONSIBLE"
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
becomeResponsibleForSelf()

guard CommandLine.arguments.count == 1,
      let bytes = try? FileHandle.standardInput.read(upToCount:4097), bytes.count <= 4096,
      let input = (try? JSONSerialization.jsonObject(with:bytes)) as? [String:Any],
      let operation = input["operation"] as? String else { emit(["ok":false]) }

let store = EKEventStore()
func granted() -> Bool {
    if EKEventStore.authorizationStatus(for: .event) == .fullAccess { return true }
    var answer = false, done = false
    store.requestFullAccessToEvents { ok, _ in answer = ok; done = true }
    let deadline = Date().addingTimeInterval(120)
    while !done && Date() < deadline { RunLoop.current.run(mode: .default, before: Date().addingTimeInterval(0.1)) }
    return answer
}

if operation == "permission" && Set(input.keys) == ["operation"] {
    emit(granted() ? ["ok": true] : ["ok": false, "code": "calendar-permission"])
}
if operation == "create" {
    guard Set(input.keys) == ["operation", "title", "start", "end", "allDay"],
          let title = input["title"] as? String, let start = input["start"] as? Double, let end = input["end"] as? Double,
          let allDay = input["allDay"] as? Bool,
          !title.trimmingCharacters(in: .whitespaces).isEmpty, title.count <= 120,
          title.unicodeScalars.allSatisfy({ !CharacterSet.controlCharacters.contains($0) }),
          start > Date().timeIntervalSince1970 - 86400, end > start, end - start <= 7 * 86400,
          start < Date().timeIntervalSince1970 + 367 * 86400 else { emit(["ok":false]) }
    // Adding never prompts: permission is asked only by the explicit setup step.
    guard EKEventStore.authorizationStatus(for: .event) == .fullAccess else { emit(["ok": false, "code": "calendar-permission"]) }
    guard let calendar = store.defaultCalendarForNewEvents, calendar.allowsContentModifications else { emit(["ok": false, "code": "calendar-read-only"]) }
    let event = EKEvent(eventStore: store)
    event.calendar = calendar
    event.title = title
    event.isAllDay = allDay
    event.startDate = Date(timeIntervalSince1970: start)
    // An all-day event ends on its own day; a timed one at the reviewed end.
    event.endDate = allDay ? Date(timeIntervalSince1970: end - 1) : Date(timeIntervalSince1970: end)
    // All-day: 9 AM that day. Timed: 15 minutes before.
    event.addAlarm(EKAlarm(relativeOffset: allDay ? 9 * 3600 : -15 * 60))
    do { try store.save(event, span: .thisEvent, commit: true) } catch { emit(["ok": false, "code": "calendar-save"]) }
    // Read back what Calendar stored, not what was asked.
    guard let id = event.eventIdentifier, let stored = store.event(withIdentifier: id) else { emit(["ok": false, "code": "calendar-save"]) }
    emit(["ok": true, "title": String((stored.title ?? "").prefix(300)), "start": stored.startDate.timeIntervalSince1970,
          "end": allDay ? end : stored.endDate.timeIntervalSince1970, "allDay": stored.isAllDay, "calendar": String(stored.calendar.title.prefix(100))])
}
guard operation == "events", Set(input.keys) == ["operation", "start", "end"],
      let start = input["start"] as? Double, let end = input["end"] as? Double,
      start > 0, end > start, end - start <= 7 * 86400 else { emit(["ok":false]) }
// Reading never prompts: permission is asked only by the explicit setup step.
guard EKEventStore.authorizationStatus(for: .event) == .fullAccess else { emit(["ok": false, "code": "calendar-permission"]) }
let predicate = store.predicateForEvents(withStart: Date(timeIntervalSince1970: start), end: Date(timeIntervalSince1970: end), calendars: nil)
var events: [[String:Any]] = []
for event in store.events(matching: predicate).sorted(by: { $0.startDate < $1.startDate }).prefix(50) {
    if event.status == .canceled { continue }
    let title = String((event.title ?? "").prefix(300))
    events.append(["title": title.isEmpty ? "Untitled event" : title, "start": event.startDate.timeIntervalSince1970, "allDay": event.isAllDay])
}
emit(["ok": true, "events": events])
