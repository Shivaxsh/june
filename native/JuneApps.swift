// Opens or brings forward one app from a fixed allowlist, then reports what macOS shows.
// No shell, no scripting, no arguments passed to the app.
import AppKit
import Foundation

let allowed: Set<String> = [
    "com.microsoft.VSCode", "com.anthropic.claudefordesktop", "com.openai.codex",
    "com.microsoft.Powerpoint", "com.microsoft.Excel", "com.microsoft.Word",
    "com.apple.Notes", "com.google.Chrome", "com.apple.iCal", "com.apple.Music",
    "com.figma.Desktop", "com.apple.mail", "com.canva.affinity", "com.apple.AppStore",
    "com.apple.Terminal", "com.apple.screenshot.launcher", "com.apple.DigitalColorMeter"
]
let workspace = NSWorkspace.shared
func emit(_ bundle: String, _ state: String, installed: Bool) -> Never {
    let value: [String: Any] = ["protocol": 1, "bundleId": bundle, "installed": installed, "state": state]
    FileHandle.standardOutput.write(try! JSONSerialization.data(withJSONObject: value)); exit(0)
}
if CommandLine.arguments.count == 2 && CommandLine.arguments[1] == "--self-test" {
    // Opens nothing.
    FileHandle.standardOutput.write(try! JSONSerialization.data(withJSONObject: ["ok": allowed.count == 17 && !allowed.contains("com.apple.Safari"), "opened": false])); exit(0)
}
guard CommandLine.arguments.count == 3, CommandLine.arguments[1] == "--open", allowed.contains(CommandLine.arguments[2]) else { exit(2) }
let bundle = CommandLine.arguments[2]
// The Screenshot launcher starts the system toolbar (screencaptureui) and exits at once, so the
// toolbar is what shows that it opened.
let shown: Set<String> = bundle == "com.apple.screenshot.launcher" ? [bundle, "com.apple.screencaptureui"] : [bundle]
func observed() -> String {
    let running = workspace.runningApplications.filter { shown.contains($0.bundleIdentifier ?? "") && !$0.isTerminated }
    if running.contains(where: { $0.isActive }) { return "active" }
    return running.isEmpty ? "not-running" : "running"
}
guard let url = workspace.urlForApplication(withBundleIdentifier: bundle) else { emit(bundle, "failed", installed: false) }
let config = NSWorkspace.OpenConfiguration(); config.activates = true
// Large apps (Word, Figma, Affinity) can take many seconds to appear, more so when several
// launch together. Keep checking until the app is seen running, then report what is observed.
func waitUntilRunning(_ remaining: Int) {
    let state = observed()
    if state != "not-running" || remaining <= 0 { emit(bundle, state == "not-running" ? "unverified" : state, installed: true) }
    DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { waitUntilRunning(remaining - 1) }
}
workspace.openApplication(at: url, configuration: config) { app, error in
    DispatchQueue.main.async {
        guard shown.count > 1 || (error == nil && app?.bundleIdentifier == bundle) else { emit(bundle, "failed", installed: true) }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.7) { waitUntilRunning(36) }
    }
}
// Final deadline: report whatever macOS shows, never a guess.
DispatchQueue.main.asyncAfter(deadline: .now() + 24) { let state = observed(); emit(bundle, state == "not-running" ? "unverified" : state, installed: true) }
RunLoop.main.run()
