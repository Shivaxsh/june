// Fixed VS Code actions. Folder inputs come only from the user-maintained registry. No shell.
import AppKit
import Foundation
let bundle = "com.microsoft.VSCode"
let workspace = NSWorkspace.shared
func emit(_ state: String, installed: Bool, folderAccepted: Bool = false) -> Never {
    let value: [String: Any] = ["protocol": 1, "bundleId": bundle, "installed": installed, "state": state, "folderAccepted": folderAccepted]
    let data = try! JSONSerialization.data(withJSONObject: value)
    FileHandle.standardOutput.write(data); FileHandle.standardOutput.write(Data([10])); exit(0)
}
func observed() -> String {
    let running = workspace.runningApplications.filter { $0.bundleIdentifier == bundle && !$0.isTerminated }
    if running.contains(where: { $0.isActive }) { return "active" }
    return running.isEmpty ? "not-running" : "running"
}
let url = workspace.urlForApplication(withBundleIdentifier: bundle)
guard CommandLine.arguments.count >= 2 else { exit(2) }
if CommandLine.arguments.count == 2 && CommandLine.arguments[1] == "--inspect" { emit(observed(), installed: url != nil) }
let project = CommandLine.arguments[1] == "--open-project"
guard (project && CommandLine.arguments.count == 5) || (!project && CommandLine.arguments[1] == "--open-vscode" && CommandLine.arguments.count == 2) else { exit(2) }
var folder: URL?
if project {
    let path = CommandLine.arguments[2]
    let candidate = URL(fileURLWithPath: path, isDirectory: true).resolvingSymlinksInPath()
    var directory: ObjCBool = false
    guard path.hasPrefix("/"), candidate.path == path,
          FileManager.default.fileExists(atPath: path, isDirectory: &directory), directory.boolValue,
          let attributes = try? FileManager.default.attributesOfItem(atPath: path),
          let device = attributes[.systemNumber] as? NSNumber,
          let inode = attributes[.systemFileNumber] as? NSNumber,
          device.stringValue == CommandLine.arguments[3], inode.stringValue == CommandLine.arguments[4]
    else { emit("failed", installed: url != nil) }
    folder = candidate
}
guard let application = url else { emit("failed", installed: false) }
let config = NSWorkspace.OpenConfiguration(); config.activates = true
let finished: (NSRunningApplication?, Error?) -> Void = { app, error in
    // Serialize every result with the timeout on main; exit happens before another result can write.
    DispatchQueue.main.async {
        guard error == nil, app?.bundleIdentifier == bundle else { emit("failed", installed: true) }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { emit(observed(), installed: true, folderAccepted: project) }
    }
}
if let folder = folder { workspace.open([folder], withApplicationAt: application, configuration: config, completionHandler: finished) }
else { workspace.openApplication(at: application, configuration: config, completionHandler: finished) }
DispatchQueue.main.asyncAfter(deadline: .now() + 8) { emit("unverified", installed: true) }
RunLoop.main.run()
