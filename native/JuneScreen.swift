// June Screen: read the text on the screen once, on request, entirely on this Mac.
// One capture of the main display is held in memory only, read with Apple's on-device Vision text
// recognition, and released. No image is ever written to disk or returned; only the text leaves.
import AppKit
import Foundation
import ScreenCaptureKit
import Vision

let TEXT_LIMIT = 12000

func emit(_ value: [String:Any]) -> Never {
    if let data = try? JSONSerialization.data(withJSONObject:value) { FileHandle.standardOutput.write(data) }
    exit(value["ok"] as? Bool == true ? 0 : 1)
}

// macOS attributes Screen Recording consent to the responsible process: become our own, so the grant belongs to "June Screen".
func becomeResponsibleForSelf() {
    let marker = "JUNE_SCREEN_SELF_RESPONSIBLE"
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

/// Reading order for Vision boxes (normalised, origin bottom left): rows from the top, left to right within a row.
/// Rows are formed in one pass over a total order, so the result never depends on the input order
/// (a pairwise "same row" comparison is not transitive and cannot be used as a sort rule).
func readingOrder(_ boxes: [(CGRect, String)]) -> [String] {
    let byTop = boxes.sorted { a, b in
        if a.0.midY != b.0.midY { return a.0.midY > b.0.midY }
        if a.0.minX != b.0.minX { return a.0.minX < b.0.minX }
        return a.1 < b.1
    }
    var rows: [[(CGRect, String)]] = []
    for box in byTop {
        if let anchor = rows.last?.first, abs(anchor.0.midY - box.0.midY) < min(anchor.0.height, box.0.height) * 0.5 {
            rows[rows.count - 1].append(box)
        } else {
            rows.append([box])
        }
    }
    return rows.flatMap { row in row.sorted { a, b in a.0.minX != b.0.minX ? a.0.minX < b.0.minX : a.1 < b.1 }.map { $0.1 } }
}

/// Text lines in reading order: top to bottom, then left to right within a row.
func recognise(_ image: CGImage) throws -> [String] {
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = true
    try VNImageRequestHandler(cgImage: image, options: [:]).perform([request])
    let found = (request.results ?? []).compactMap { o -> (CGRect, String)? in
        guard let best = o.topCandidates(1).first, best.confidence >= 0.3 else { return nil }
        return (o.boundingBox, best.string)
    }
    var lines: [String] = []
    var total = 0
    for text in readingOrder(found) {
        let clean = text.replacingOccurrences(of: "[\\x00-\\x1f\\x7f]", with: " ", options: .regularExpression).trimmingCharacters(in: .whitespaces)
        if clean.isEmpty { continue }
        if total + clean.count + 1 > TEXT_LIMIT { break }
        lines.append(clean); total += clean.count + 1
    }
    return lines
}

func captureMainDisplay() throws -> CGImage {
    var result: Result<CGImage, Error>? = nil
    let done = DispatchSemaphore(value: 0)
    Task {
        do {
            let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: true)
            let main = CGMainDisplayID()
            guard let display = content.displays.first(where: { $0.displayID == main }) ?? content.displays.first else {
                throw NSError(domain: "JuneScreen", code: 2)
            }
            let filter = SCContentFilter(display: display, excludingWindows: [])
            let configuration = SCStreamConfiguration()
            let scale = Int(NSScreen.main?.backingScaleFactor ?? 2)
            configuration.width = display.width * scale
            configuration.height = display.height * scale
            configuration.showsCursor = false
            result = .success(try await SCScreenshotManager.captureImage(contentFilter: filter, configuration: configuration))
        } catch {
            result = .failure(error)
        }
        done.signal()
    }
    if done.wait(timeout: .now() + 20) == .timedOut { throw NSError(domain: "JuneScreen", code: 3) }
    return try result!.get()
}

func frontApp() -> String {
    String((NSWorkspace.shared.frontmostApplication?.localizedName ?? "").prefix(80))
}

func selfTest() -> Never {
    func fail(_ why: String) -> Never { FileHandle.standardError.write("JuneScreen self-test failed: \(why)\n".data(using: .utf8)!); exit(1) }
    // Ordering: same answer for every input order, slight baseline jitter stays one row, rows go top to bottom.
    let box = { (x: CGFloat, y: CGFloat, t: String) in (CGRect(x: x, y: y, width: 0.1, height: 0.02), t) }
    let page = [box(0.6, 0.801, "Right"), box(0.1, 0.80, "Left"), box(0.35, 0.795, "Middle"), box(0.1, 0.70, "Second"), box(0.1, 0.10, "Last")]
    let expected = ["Left", "Middle", "Right", "Second", "Last"]
    for order in [page, page.reversed(), [page[3], page[0], page[4], page[2], page[1]]] where readingOrder(Array(order)) != expected {
        fail("reading order \(readingOrder(Array(order)))")
    }
    if readingOrder([]) != [] { fail("empty") }
    // Input is bounded: a request larger than the limit is refused without reading it all.
    if boundedRead(from: Pipe.withData(Data(repeating: 0x20, count: 10_000)), limit: 4096) != nil { fail("oversized input accepted") }
    if boundedRead(from: Pipe.withData(Data("{}".utf8)), limit: 4096) != Data("{}".utf8) { fail("small input") }
    // Draw known words into an in-memory image and read them back: checks Vision without any capture or permission.
    let size = NSSize(width: 900, height: 220)
    let picture = NSImage(size: size)
    picture.lockFocus()
    NSColor.white.setFill(); NSRect(origin: .zero, size: size).fill()
    ("June screen self test" as NSString).draw(at: NSPoint(x: 40, y: 130), withAttributes: [.font: NSFont.systemFont(ofSize: 44), .foregroundColor: NSColor.black])
    ("Error 404 page not found" as NSString).draw(at: NSPoint(x: 40, y: 50), withAttributes: [.font: NSFont.systemFont(ofSize: 44), .foregroundColor: NSColor.black])
    picture.unlockFocus()
    guard let image = picture.cgImage(forProposedRect: nil, context: nil, hints: nil), let lines = try? recognise(image),
          lines.count == 2, lines[0].lowercased().contains("self test"), lines[1].contains("404") else { fail("recognition") }
    print("JuneScreen self-test ok"); exit(0)
}

/// At most `limit` bytes of a request, or nil when there is more: never reads an unbounded stream into memory.
func boundedRead(from handle: FileHandle, limit: Int) -> Data? {
    var data = Data()
    while true {
        guard let chunk = try? handle.read(upToCount: 1024), !chunk.isEmpty else { return data }
        data.append(chunk)
        if data.count > limit { return nil }
    }
}

extension Pipe {
    static func withData(_ data: Data) -> FileHandle {
        let pipe = Pipe()
        DispatchQueue.global().async { pipe.fileHandleForWriting.write(data); try? pipe.fileHandleForWriting.close() }
        return pipe.fileHandleForReading
    }
}

if CommandLine.arguments.contains("--self-test") { selfTest() }
becomeResponsibleForSelf()

guard let input = boundedRead(from: FileHandle.standardInput, limit: 4096), let request = try? JSONSerialization.jsonObject(with: input) as? [String:Any],
      let operation = request["operation"] as? String, request.count == 1 else {
    emit(["ok": false, "code": "invalid"])
}
switch operation {
case "status":
    emit(["ok": true, "permission": CGPreflightScreenCaptureAccess()])
case "request":
    // Shows macOS's own prompt the first time; the grant takes effect for the next June Screen run.
    let granted = CGPreflightScreenCaptureAccess() || CGRequestScreenCaptureAccess()
    emit(["ok": true, "permission": granted])
case "read":
    guard CGPreflightScreenCaptureAccess() else { emit(["ok": false, "code": "screen-permission"]) }
    do {
        let lines = try autoreleasepool { try recognise(try captureMainDisplay()) }
        emit(["ok": true, "app": frontApp(), "lines": lines])
    } catch {
        let denied = (error as NSError).domain == SCStreamErrorDomain && (error as NSError).code == SCStreamError.userDeclined.rawValue
        emit(["ok": false, "code": denied ? "screen-permission" : "unavailable"])
    }
default:
    emit(["ok": false, "code": "invalid"])
}
