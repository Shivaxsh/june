// One fixed operation: switch the Mac between light and dark appearance, and read back the result.
// The only value taken from the request is one of three fixed words.
import AppKit
import Foundation

func emit(_ value: [String:Any]) -> Never {
    if let data = try? JSONSerialization.data(withJSONObject:value) { FileHandle.standardOutput.write(data) }
    exit(value["ok"] as? Bool == true ? 0 : 1)
}
let modes:[String:String] = ["dark":"true", "light":"false", "toggle":"not dark mode"]
if CommandLine.arguments.count == 2 && CommandLine.arguments[1] == "--self-test" {
    // Nothing is changed and no permission is requested.
    emit(["ok": modes.count == 3 && modes["sepia"] == nil, "changed": false])
}

// macOS attributes Automation consent to the responsible process. Re-exec as our own
// responsible process so the prompt and the grant belong to "June Quick".
func becomeResponsibleForSelf() {
    let marker = "JUNE_QUICK_SELF_RESPONSIBLE"
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
      let bytes = try? FileHandle.standardInput.read(upToCount:1025), bytes.count <= 1024,
      let input = (try? JSONSerialization.jsonObject(with:bytes)) as? [String:Any],
      Set(input.keys) == ["operation", "mode"], input["operation"] as? String == "appearance",
      let mode = input["mode"] as? String, let value = modes[mode] else { emit(["ok":false]) }
let source = """
tell application "System Events"
    tell appearance preferences
        set dark mode to \(value)
        return dark mode
    end tell
end tell
"""
var error:NSDictionary?
guard let script = NSAppleScript(source:source) else { emit(["ok":false]) }
let result = script.executeAndReturnError(&error)
if let error = error {
    let code = (error[NSAppleScript.errorNumber] as? NSNumber)?.intValue
    emit(["ok":false, "code": code == -1743 ? "automation-permission" : "quick-unavailable", "number": code ?? 0])
}
emit(["ok":true, "dark": result.booleanValue])
