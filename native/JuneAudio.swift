// June Audio: a bounded local IPC helper. No audio or speech text is logged.
import AppKit
import AVFoundation
import Foundation
import Darwin

let writer = DispatchQueue(label: "local.june.audio.stdout")
func emit(_ value: [String: Any]) {
    guard let bytes = try? JSONSerialization.data(withJSONObject: value), bytes.count < 1_048_576 else { return }
    writer.async { FileHandle.standardOutput.write(bytes + Data([10])) }
}
func permission() -> String {
    switch AVCaptureDevice.authorizationStatus(for: .audio) {
    case .authorized: return "granted"
    case .denied, .restricted: return "denied"
    case .notDetermined: return "not-determined"
    @unknown default: return "unknown"
    }
}
let knownFemale = ["Nicky", "Samantha", "Karen", "Moira", "Tessa", "Kathy", "Flo", "Shelley", "Sandy", "Veena", "Ava", "Allison"]
func voices() -> [[String: Any]] {
    AVSpeechSynthesisVoice.speechVoices().filter {
        $0.language.lowercased().hasPrefix("en") && ($0.gender == .female || knownFemale.contains($0.name))
    }.map { ["id": $0.identifier, "name": $0.name, "lang": $0.language, "gender": "female", "localService": true] }
}
func copyPCM(_ buffer: AVAudioPCMBuffer) -> AVAudioPCMBuffer? {
    guard let copy = AVAudioPCMBuffer(pcmFormat: buffer.format, frameCapacity: max(1,buffer.frameLength)) else { return nil }
    copy.frameLength = buffer.frameLength
    let src = UnsafeMutableAudioBufferListPointer(buffer.mutableAudioBufferList)
    let dst = UnsafeMutableAudioBufferListPointer(copy.mutableAudioBufferList)
    for i in 0..<min(src.count,dst.count) {
        if let a = src[i].mData, let b = dst[i].mData { memcpy(b,a,min(Int(src[i].mDataByteSize),Int(dst[i].mDataByteSize))) }
    }
    return copy
}
func makeCaptureConverter(from input: AVAudioFormat,to output: AVAudioFormat) -> AVAudioConverter? {
    guard let converter=AVAudioConverter(from:input,to:output) else { return nil }
    // VPIO may expose a multi-channel aggregate without a standard layout.
    // Its processed microphone is channel zero. Implicit layout remapping can
    // select silence; never average reference/raw channels into transcription.
    converter.channelMap = [0]
    return converter
}
final class SpeechJob {
    let id: String, owner: String, request: String, text: String, voice: String
    let rate: Float
    let silent: Bool
    var buffers: [AVAudioPCMBuffer] = []
    var envelope: [(AVAudioFramePosition, AVAudioFramePosition, Double)] = []
    var converter: AVAudioConverter?
    var bytes = 0, pending = 0, rendered = 0, lastPosition = 0
    var total: AVAudioFramePosition = 0
    var complete = false, cancelled = false, started = false
    var prepareStart = Date()
    var playbackStart: Date?
    init(_ v: [String: Any], silent: Bool = false) {
        id = v["id"] as? String ?? UUID().uuidString
        owner = v["ownerId"] as? String ?? "warm"
        request = v["requestId"] as? String ?? "warm"
        text = v["text"] as? String ?? "June is ready."
        voice = v["voiceId"] as? String ?? "com.apple.ttsbundle.siri_nicky_en-US_compact"
        rate = Float(v["rate"] as? Double ?? 0.98)
        self.silent = silent
    }
}
// The render callback never shares mutable capture state with the main queue.
final class CaptureToken {
    private let lock = NSLock()
    private var cancelled = false
    private var queued = 0
    var pending = Data() // accessed only by captureQueue
    let diagnostic: Bool
    init(diagnostic: Bool = false) { self.diagnostic = diagnostic }
    func active() -> Bool { lock.lock(); defer { lock.unlock() }; return !cancelled }
    func cancel() { lock.lock(); cancelled = true; lock.unlock() }
    func claim() -> Bool { lock.lock(); defer { lock.unlock() }; if cancelled || queued >= 32 { return false }; queued += 1; return true }
    func consumed() { lock.lock(); queued -= 1; lock.unlock() }
}
final class JuneAudio {
    var engine = AVAudioEngine()
    var player = AVAudioPlayerNode()
    let playFormat = AVAudioFormat(standardFormatWithSampleRate: 48000, channels: 1)!
    var synth = AVSpeechSynthesizer()
    var jobs: [String: SpeechJob] = [:], outputOrder: [String] = [], synthOrder: [String] = []
    var synthesizing: SpeechJob?, playing: SpeechJob?
    var requestedSession: String?, captureSession: String?
    var captureToken: CaptureToken?
    var lastHeartbeat = Date(), configuring = false, graphReady = false
    var captureConverter: AVAudioConverter?
    var tapInstalled = false
    let captureQueue = DispatchQueue(label: "local.june.audio.capture", qos: .userInitiated)
    var ticker: Timer?
    var configurationObserver: NSObjectProtocol?
    init() {
        ticker = Timer.scheduledTimer(withTimeInterval: 0.05, repeats: true) { [weak self] _ in self?.tick() }

    }
    func result(_ id: String, _ fields: [String: Any] = [:]) { emit(fields.merging(["type": "result", "id": id]) { _, new in new }) }
    func event(_ job: SpeechJob, _ phase: String, _ extra: [String: Any] = [:]) {
        guard !job.silent else { return }
        emit(extra.merging(["type": "playback", "id": job.id, "phase": phase]) { _, new in new })
    }
    func setupGraph(capture: Bool) throws {
        configuring = true; defer { configuring = false }
        if graphReady && (captureSession != nil) == capture { return }
        if engine.isRunning { engine.stop() }
        if tapInstalled { engine.inputNode.removeTap(onBus: 0); tapInstalled = false }
        if let observer=configurationObserver { NotificationCenter.default.removeObserver(observer); configurationObserver=nil }
        engine = AVAudioEngine(); player = AVAudioPlayerNode()
        if capture {
            try engine.inputNode.setVoiceProcessingEnabled(true)
            if #available(macOS 14.0, *) {
                var ducking = engine.inputNode.voiceProcessingOtherAudioDuckingConfiguration
                ducking.enableAdvancedDucking = false
                ducking.duckingLevel = .min
                engine.inputNode.voiceProcessingOtherAudioDuckingConfiguration = ducking
            }
        }
        engine.attach(player)
        engine.connect(player, to: engine.mainMixerNode, format: playFormat)
        if capture {
            // AVAudioIONode requires equal client formats on both voice I/O
            // sides. The mixer converts Nicky's 48 kHz mono playback to this
            // route format; the microphone tap stays outside the output path.
            let ioFormat = engine.inputNode.outputFormat(forBus:0)
            engine.connect(engine.mainMixerNode,to:engine.outputNode,format:ioFormat)
        }
        engine.prepare(); graphReady = true
        let configuredEngine = engine
        configurationObserver = NotificationCenter.default.addObserver(forName:.AVAudioEngineConfigurationChange,object:configuredEngine,queue:.main) { [weak self, weak configuredEngine] _ in
            // Hardware changes stop the engine before notification. Observe
            // only this graph, not replaced graphs or the synthesizer's graph.
            guard let self, let configuredEngine, self.engine === configuredEngine, self.graphReady, !self.configuring else { return }
            self.failDevice()
        }
    }
    func startCapture(_ command: [String: Any]) {
        let id = command["id"] as? String ?? "", session = command["session"] as? String ?? ""
        guard !session.isEmpty, captureSession == nil, requestedSession == nil else { result(id, ["error": "The microphone is already owned by another session."]); return }
        requestedSession = session
        let finish: (Bool) -> Void = { [weak self] granted in
            DispatchQueue.main.async {
                guard let self else { return }
                guard self.requestedSession == session else { self.result(id, ["error": "Microphone request cancelled.", "permission": permission()]); return }
                guard granted else { self.requestedSession = nil; self.result(id, ["error": "Allow June Audio microphone access in macOS Privacy & Security, then enable hands-free again.", "permission": permission()]); return }
                var captureStage = "graph"
                do {
                    self.cancelAll()
                    try self.setupGraph(capture: true)
                    captureStage = "format"
                    let token = CaptureToken(diagnostic:command["diagnostic"] as? Bool ?? false)
                    self.captureToken = token
                    let input = self.engine.inputNode
                    let format = input.outputFormat(forBus: 0)
                    guard format.sampleRate > 0, format.channelCount > 0,
                          let output = AVAudioFormat(commonFormat: .pcmFormatInt16, sampleRate: 16000, channels: 1, interleaved: false),
                          let converter = makeCaptureConverter(from: format, to: output) else { throw NSError(domain: "JuneAudio", code: 1) }
                    self.captureConverter = converter
                    self.captureSession = session
                    captureStage = "tap"
                    input.installTap(onBus: 0, bufferSize: 1024, format: format) { [weak self] buffer, _ in
                        guard let self, token.active() else { return }
                        guard token.claim() else {
                            token.cancel()
                            DispatchQueue.main.async { self.releaseCapture(session); emit(["type":"capture-error","session":session]) }
                            return
                        }
                        guard let copy = copyPCM(buffer) else { token.consumed(); return }
                        self.captureQueue.async { [weak self] in defer { token.consumed() }
                            self?.captured(copy, converter, output, session, token) }
                    }
                    self.tapInstalled = true
                    captureStage = "start"
                    try self.engine.start()
                    self.result(id, ["permission": permission(), "capturing": true])
                } catch {
                    self.releaseCapture(session)
                    self.result(id, ["error": "The Mac audio device could not start voice processing (\(captureStage), code \((error as NSError).code)). Check the selected input/output device, then retry.", "permission": permission()])
                }
            }
        }
        switch AVCaptureDevice.authorizationStatus(for: .audio) {
        case .authorized: finish(true)
        case .notDetermined: AVCaptureDevice.requestAccess(for: .audio, completionHandler: finish)
        default: finish(false)
        }
    }
    func captured(_ buffer: AVAudioPCMBuffer, _ converter: AVAudioConverter, _ output: AVAudioFormat, _ session: String, _ token: CaptureToken) {
        guard token.active() else { return }
        let capacity = AVAudioFrameCount(ceil(Double(buffer.frameLength) * 16000 / buffer.format.sampleRate)) + 64
        guard let converted = AVAudioPCMBuffer(pcmFormat: output, frameCapacity: capacity) else { return }
        var sent = false, error: NSError?
        converter.convert(to: converted, error: &error) { _, status in
            if sent { status.pointee = .noDataNow; return nil }
            sent = true; status.pointee = .haveData; return buffer
        }
        guard error == nil, let samples = converted.int16ChannelData?[0], token.active() else { return }
        var levels: [Double] = []
        if token.diagnostic, let channels = buffer.floatChannelData {
            for channel in 0..<min(8,Int(buffer.format.channelCount)) {
                var sum = 0.0
                for i in 0..<Int(buffer.frameLength) { let lane=buffer.format.isInterleaved ? 0 : channel; let index=buffer.format.isInterleaved ? i*Int(buffer.format.channelCount)+channel : i; let v=Double(channels[lane][index]); sum += v*v }
                levels.append(buffer.frameLength > 0 ? sqrt(sum/Double(buffer.frameLength)) : 0)
            }
        }
        token.pending.append(Data(bytes: samples, count: Int(converted.frameLength) * 2))
        guard token.pending.count <= 64000 else { emit(["type": "capture-error", "session": session]); return }
        while token.pending.count >= 640 {
            let packet = Data(token.pending.prefix(640)); token.pending.removeFirst(640)
            var sum = 0.0
            packet.withUnsafeBytes { raw in
                for n in raw.bindMemory(to: Int16.self) { let value = Double(Int16(littleEndian: n)) / 32768; sum += value * value }
            }
            var event: [String:Any] = ["type":"audio","session":session,"pcm":packet.base64EncodedString(),"rms":min(1,sqrt(sum/320))]
            if token.diagnostic { event["inputLevels"]=levels;event["inputChannels"]=buffer.format.channelCount;event["inputRate"]=buffer.format.sampleRate }
            emit(event)
        }
    }
    func releaseCapture(_ session: String) {
        guard session == requestedSession || session == captureSession else { return }
        requestedSession = nil; captureToken?.cancel(); captureToken = nil
        if tapInstalled { engine.inputNode.removeTap(onBus: 0); tapInstalled = false }
        if engine.isRunning { engine.stop() }
        captureSession = nil; captureConverter = nil; graphReady = false
    }
    func speak(_ command: [String: Any], silent: Bool = false) {
        let job = SpeechJob(command, silent: silent)
        guard jobs[job.id] == nil, jobs.count < 3, !job.text.isEmpty, job.text.utf16.count <= 2000,
              voices().contains(where: { $0["id"] as? String == job.voice }) else {
            if silent { result(job.id, ["error": "Choose an installed female voice."]) } else { event(job, "error") }; return
        }
        jobs[job.id] = job; synthOrder.append(job.id)
        if !silent { outputOrder.append(job.id) }
        pumpSynthesis()
    }
    func pumpSynthesis() {
        guard synthesizing == nil else { return }
        while let id = synthOrder.first {
            synthOrder.removeFirst()
            guard let job = jobs[id], !job.cancelled else { continue }
            synthesizing = job
            let utterance = AVSpeechUtterance(string: job.text)
            utterance.voice = AVSpeechSynthesisVoice(identifier: job.voice)
            utterance.rate = AVSpeechUtteranceDefaultSpeechRate * job.rate
            utterance.pitchMultiplier = 1
            synth.write(utterance) { [weak self, weak job] buffer in
                guard let raw = buffer as? AVAudioPCMBuffer, let pcm = copyPCM(raw) else { return }
                DispatchQueue.main.async {
                    guard let self, let job, self.jobs[job.id] === job, !job.cancelled else { return }
                    if pcm.frameLength == 0 {
                        self.flush(job)
                        job.complete = true
                        if self.synthesizing === job { self.synthesizing = nil }
                        if job.silent { self.jobs.removeValue(forKey: job.id); self.result(job.id, ["prepared": true]) }
                        else { self.pumpOutput(); self.finishIfPlayed(job) }
                        self.pumpSynthesis()
                    } else if !job.silent { self.prepared(pcm, job) }
                }
            }
            return
        }
    }
    func prepared(_ buffer: AVAudioPCMBuffer, _ job: SpeechJob) {
        if job.converter == nil { job.converter = AVAudioConverter(from: buffer.format, to: playFormat) }
        guard let converter = job.converter, let pcm = AVAudioPCMBuffer(pcmFormat: playFormat,
            frameCapacity: AVAudioFrameCount(ceil(Double(buffer.frameLength) * 48000 / buffer.format.sampleRate)) + 64) else { cancel(job); return }
        var supplied = false, error: NSError?
        converter.convert(to: pcm, error: &error) { _, status in
            if supplied { status.pointee = .noDataNow; return nil }
            supplied = true; status.pointee = .haveData; return buffer
        }
        guard error == nil else { event(job,"error"); cancel(job); return }
        accept(pcm,job)
    }
    func flush(_ job: SpeechJob) {
        guard !job.silent, let converter = job.converter else { return }
        for _ in 0..<8 {
            guard let pcm = AVAudioPCMBuffer(pcmFormat:playFormat,frameCapacity:512) else { return }
            var error: NSError?
            let status = converter.convert(to:pcm,error:&error) { _, input in input.pointee = .endOfStream; return nil }
            if error != nil { return }
            if pcm.frameLength > 0 { accept(pcm,job) }
            if status == .endOfStream || pcm.frameLength == 0 { return }
        }
    }
    func accept(_ pcm: AVAudioPCMBuffer, _ job: SpeechJob) {
        guard jobs[job.id] === job, !job.cancelled else { return }
        job.bytes += Int(pcm.frameLength) * 4
        guard job.bytes <= 16 * 1024 * 1024 else { event(job,"error"); cancel(job); return }
        var energy = 0.0
        if let samples = pcm.floatChannelData?[0] {
            for i in 0..<Int(pcm.frameLength) { energy += Double(samples[i] * samples[i]) }
        }
        let level = pcm.frameLength > 0 ? min(1, sqrt(energy / Double(pcm.frameLength)) * 5) : 0
        job.envelope.append((job.total,job.total + AVAudioFramePosition(pcm.frameLength),level))
        job.total += AVAudioFramePosition(pcm.frameLength)
        if playing === job { schedule(pcm,job) } else { job.buffers.append(pcm); pumpOutput() }
    }
    func pumpOutput() {
        guard playing == nil else { return }
        while let id = outputOrder.first {
            guard let job = jobs[id], !job.cancelled else { outputOrder.removeFirst(); continue }
            guard !job.buffers.isEmpty else {
                if job.complete { event(job,"error"); jobs.removeValue(forKey:id); outputOrder.removeFirst(); continue }
                return
            }
            do {
                if !graphReady { try setupGraph(capture: captureSession != nil) }
                if !engine.isRunning { try engine.start() }
                player.stop(); playing = job
                for buffer in job.buffers { schedule(buffer,job) }; job.buffers = []
                player.play(); return
            } catch { event(job,"error"); cancel(job) }
        }
    }
    func schedule(_ buffer: AVAudioPCMBuffer, _ job: SpeechJob) {
        job.pending += 1
        player.scheduleBuffer(buffer, completionCallbackType: .dataPlayedBack) { [weak self, weak job] _ in
            DispatchQueue.main.async {
                guard let self, let job, self.jobs[job.id] === job, !job.cancelled else { return }
                job.pending -= 1; job.rendered += Int(buffer.frameLength); self.finishIfPlayed(job)
            }
        }
    }
    func finishIfPlayed(_ job: SpeechJob) {
        guard playing === job, job.complete, job.pending == 0 else { return }
        if !job.started { job.started = true; job.playbackStart = Date(); event(job,"start",["firstAudioMs":Date().timeIntervalSince(job.prepareStart) * 1000]) }
        event(job,"boundary",["charIndex":job.text.utf16.count,"charLength":0,"level":0])
        event(job,"end",["playbackMs":Date().timeIntervalSince(job.playbackStart ?? job.prepareStart) * 1000])
        player.stop(); playing = nil; jobs.removeValue(forKey:job.id); outputOrder.removeAll { $0 == job.id }
        pumpOutput()
    }
    func cancel(_ job: SpeechJob) {
        guard !job.cancelled else { return }
        job.cancelled = true; event(job,"cancelled")
        if playing === job { player.stop(); playing = nil }
        if synthesizing === job { synth.stopSpeaking(at:.immediate); synth = AVSpeechSynthesizer(); synthesizing = nil }
        jobs.removeValue(forKey:job.id); outputOrder.removeAll { $0 == job.id }; synthOrder.removeAll { $0 == job.id }
        pumpSynthesis(); pumpOutput()
    }
    func cancelAll() {
        // Mark before individual cancellation so pumping cannot start a queued job.
        let all = Array(jobs.values); outputOrder = []; synthOrder = []
        for job in all { cancel(job) }
    }
    func failDevice() {
        if let session = captureSession { emit(["type":"capture-error","session":session]); releaseCapture(session) }
        cancelAll(); graphReady = false
    }
    func tick() {
        if Date().timeIntervalSince(lastHeartbeat)>3 {
            if let session = requestedSession { emit(["type":"capture-error","session":session]); releaseCapture(session) }
            cancelAll()
        }
        guard let job = playing, !job.cancelled, let render = player.lastRenderTime,
              let time = player.playerTime(forNodeTime:render), time.sampleTime > 0 else { return }
        if !job.started { job.started = true; job.playbackStart = Date(); event(job,"start",["firstAudioMs":Date().timeIntervalSince(job.prepareStart) * 1000]) }
        let elapsed = Double(time.sampleTime) / time.sampleRate
        let duration = job.complete ? max(0.01,Double(job.total) / 48000) : max(elapsed + 0.25,Double(job.text.count) / 15)
        let position = min(job.text.utf16.count, max(job.lastPosition,Int(elapsed / duration * Double(job.text.utf16.count))))
        job.lastPosition = position
        let frame = AVAudioFramePosition(elapsed * 48000)
        let level = job.envelope.first { frame >= $0.0 && frame < $0.1 }?.2 ?? 0
        let ranges = (try? NSRegularExpression(pattern: "\\S+").matches(in:job.text,range:NSRange(location:0,length:job.text.utf16.count))) ?? []
        let word = ranges.last { $0.range.location <= position }?.range ?? NSRange(location:0,length:0)
        event(job,"boundary",["charIndex":word.location,"charLength":word.length,"level":level])
    }
    func command(_ value: [String: Any]) {
        lastHeartbeat = Date()
        let id = value["id"] as? String ?? ""
        switch value["type"] as? String {
        case "heartbeat": break
        case "status": result(id,["permission":permission(),"capturing":captureSession != nil])
        case "capture": startCapture(value)
        case "release": if let session = value["session"] as? String { releaseCapture(session) }
        case "prepare": speak(value,silent:true)
        case "speak": speak(value)
        case "cancel": if let job = jobs[id] { cancel(job) }
        case "stop":
            let target = jobs.values.filter { $0.owner == value["ownerId"] as? String && $0.request == value["requestId"] as? String }
            let ids = Set(target.map { $0.id })
            synthOrder.removeAll { ids.contains($0) }; outputOrder.removeAll { ids.contains($0) }
            for job in target { cancel(job) }
        case "shutdown": if let session = requestedSession { releaseCapture(session) }; cancelAll(); exit(0)
        default: result(id,["error":"Invalid audio command."])
        }
    }
}
if CommandLine.arguments.contains("--self-test") {
    func fail(_ stage:String) -> Never { print("{\"passed\":false,\"stage\":\""+stage+"\"}");exit(1) }
    guard let layout=AVAudioChannelLayout(layoutTag:kAudioChannelLayoutTag_DiscreteInOrder | 7) else {fail("input-layout")}
    let input=AVAudioFormat(standardFormatWithSampleRate:48000,channelLayout:layout)
    guard let output=AVAudioFormat(commonFormat:.pcmFormatInt16,sampleRate:16000,channels:1,interleaved:false) else {fail("output-format")}
    guard let source=AVAudioPCMBuffer(pcmFormat:input,frameCapacity:4800),let sourceChannels=source.floatChannelData else {fail("source-buffer")}
    source.frameLength=4800
    for channel in 0..<7 {
        for i in 0..<4800 { sourceChannels[channel][i]=channel == 0 ? Float(sin(Double(i)*0.1)*0.25) : 0 }
    }
    guard let target=AVAudioPCMBuffer(pcmFormat:output,frameCapacity:1700) else {fail("target-buffer")}
    guard let converter=makeCaptureConverter(from:input,to:output) else {fail("converter")}
    var sent=false,error:NSError?
    converter.convert(to:target,error:&error) { _,status in
        if sent {status.pointee = .noDataNow;return nil};sent=true;status.pointee = .haveData;return source
    }
    var energy=0.0
    if let samples=target.int16ChannelData?[0] {for i in 0..<Int(target.frameLength) {let value=Double(samples[i])/32768;energy+=value*value}}
    let rms=target.frameLength>0 ? sqrt(energy/Double(target.frameLength)) : 0
    // A single streaming block retains the resampler priming tail; the
    // following block normally supplies it. Test signal preservation here.
    let passed=error==nil && target.frameLength>=1200 && target.frameLength<=1600 && rms>0.1
    let result:[String:Any]=["passed":passed,"frames":target.frameLength,"rms":rms,"channels":7,"microphoneOpened":false]
    let data=try! JSONSerialization.data(withJSONObject:result)
    FileHandle.standardOutput.write(data+Data([10]));exit(passed ? 0 : 1)
}
let app = NSApplication.shared
app.setActivationPolicy(.accessory)
let audio = JuneAudio()
emit(["type":"ready","permission":permission(),"voices":voices()])
DispatchQueue.global(qos:.userInitiated).async {
    var pending = Data()
    var bytes = [UInt8](repeating:0,count:4096)
    while true {
        let count = Darwin.read(STDIN_FILENO,&bytes,bytes.count)
        if count < 0 && errno == EINTR { continue }
        if count <= 0 { break }
        pending.append(contentsOf:bytes.prefix(count))
        if pending.count > 32000 { DispatchQueue.main.async { audio.failDevice(); exit(2) }; return }
        while let newline = pending.firstIndex(of:10) {
            let line = Data(pending[..<newline]); pending.removeSubrange(...newline)
            guard let object = try? JSONSerialization.jsonObject(with:line) as? [String:Any] else { continue }
            DispatchQueue.main.async { audio.command(object) }
        }
    }
    DispatchQueue.main.async { audio.failDevice(); exit(0) }
}
app.run()
