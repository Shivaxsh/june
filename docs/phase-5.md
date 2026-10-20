# Phase 5 — Real-time conversation · June v0.4

## Start and use June

From the June project folder, run `npm run realtime:setup` once. It installs the locked Python packages, verifies the official Vosk archive checksum, installs its small English model outside Git and runs actual CPU wake/VAD checks. Python 3.12 and this Mac’s existing local Whisper setup are required. Downloads are needed for setup; runtime audio processing stays local.

Keep Ollama running with `npm run model:start`. In another terminal run `npm start`, then open <http://127.0.0.1:3001/>. Development uses `npm run dev`. After source changes run `npm run build` before production startup. Control+C stops June’s owned web/backend processes; it does not stop a separately running Ollama.

1. Confirm Local AI is ready, Speak replies is checked and a local female voice is selected. Nicky remains the saved American English choice on this browser; no Indian accent is promised when none is installed.
2. Select a pause: Short (0.8 s), Normal (1.5 s) or Patient (2.5 s).
3. Click **Enable hands-free** and grant microphone permission. Wait for **Waiting for “Hey June”**. This is a persistent microphone session, visibly indicated until disabled.
4. Say **“Hey June, what is the capital of Japan?”** in one utterance. June retains recent audio so the beginning is not discarded when the wake detector finishes.
5. Pause. At least 0.5 s of voiced question audio is required. After the chosen silence interval, June transcribes locally and automatically sends the question once. Your typed draft stays untouched.
6. After her voice finishes, ask another question within 30 seconds without the wake phrase. After expiry say “Hey June” again.
7. **Start speaking while she speaks or thinks**, for example “Wait, I meant five zero six zero.” No wake phrase is needed during a reply. During playback June checks recognised words while her voice continues; verified speech stops the old reply. The check adds local transcription latency. “Hey June” remains an explicit alternative. A confirmed interruption invalidates the old speech queue and model request. Short interjections and speaker echo need testing in your room.
8. **Stop conversation & microphone**, New chat, navigation or a hidden tab disarms hands-free. Enabling it again always needs a deliberate click. Reload never reactivates it.

Manual Hold to talk and Start listening still produce an editable transcript for review. Taking over with manual recording, voice preview/replay, voice changes, muting or sample playback disables hands-free. Stop voice cancels spoken playback while text can continue.

## Workbook order

The learning studio at `/learn/phase-5` follows:

1. Voice frameworks — Pipecat processors and ordered frames.
2. Wake phrases — existing Vosk recognizer with restricted grammar, including unknown words.
3. VAD — Silero speech confidence, minimum voiced duration and silence settings.
4. Interruption — monotonically increasing session/turn/request ownership and cancellation.
5. Turn-taking — playback completion starts the follow-up timer.
6. WebRTC — separately labelled two-peer **text data-channel** loopback. It requests no microphone and uses no external ICE servers. June’s working voice transport is WebSocket PCM.
7. Modular voice versus speech-to-speech — current replaceable stages and different future architectures.

## Audio and event flow

```text
Microphone → AudioWorklet → continuous low-pass resampling → PCM16 mono 16 kHz
    → local /ws/voice → Pipecat detector → Silero VAD + Vosk wake detector
    → numbered VoiceTurn → existing Whisper service → accepted transcript
    → existing /api/chat → local Qwen NDJSON → sentence buffer → system voice
    → actual synthesis start/end callbacks → 30-second follow-up window
```

The browser owns conversation history. The voice socket has no second chat store. If a separate wake utterance is being transcribed, a bounded pending question is retained so speaking during that delay does not lose it. The first-question deadline applies to speech onset, not transcription completion. Each session has a random identifier and monotonically increasing turns; the client rejects duplicate or obsolete transcripts. Chat requests and synthesis retain their own cancellation identifiers. Only successful message/reply pairs enter model context.

The detector continues during transcription, generation and playback. During a reply, VAD or a wake-detector match is only a candidate. Sound detection does **not** pause the browser voice. A bounded candidate capture starts after 120 ms of voiced detection during playback or 240 ms during generation; after 800 ms of actual additional audio, local Whisper checks its words while June keeps speaking. CPU stalls do not count as additional audio.

June compares recognised words with up to six recent spoken captions (8,000 characters maximum), including captions arriving during a check. Echo matching uses local contiguous/fuzzy phrases rather than general shared vocabulary. A newly phrased contextual question or a corrected number must not be discarded because it concerns the preceding answer. Non-control phrases during playback also require continued detected speech after the candidate's initial 250 ms. Noise, empty results, decoder hallucinations without that speech evidence, and matching echo leave the original reply playing. This avoids the old audible pause/check/resume loop.

Only verified new speech stops the old model request and native speech queue. A verified wake phrase alone opens a question window; if the question arrived during decoding its audio is retained. A continuing question keeps its beginning in an owned capture capped at 30 seconds rather than sending a partial prefix. A rejected prefix followed by new speech is rechecked before abandoning that capture (at most three checks per candidate, eight seconds per decoder check). Newer turns, Stop and disconnects cancel owned jobs. Playback-state updates remain visible during checking. Follow-up echo is excluded without excluding unrelated one-word answers.

This is a local recognition heuristic, not reference-audio acoustic echo cancellation. Native system speech does not provide a reference waveform here. Verification adds CPU work and delays a genuine interruption by the local decoder's latency; June may continue speaking briefly after you start. Headphones and moving the microphone away from airflow improve separation. Use manual transcript review if overlapping speech is repeatedly misunderstood. Written answers remain intact; spoken occurrences of “Hey June” are replaced with “my wake phrase” to reduce self-activation.

## Files to inspect

| File | Responsibility |
| --- | --- |
| `public/audio/pcm-stream.js` | Low-pass filter and fractional resampling across blocks; shared with tests |
| `public/audio/realtime-worklet.js` | Mono mixing, silent output, bounded transferred packets |
| `lib/voice/realtime-capture.ts` | Microphone permission ownership, worklet graph, real RMS meter |
| `lib/voice/realtime-client.ts` | Socket/session lifecycle, duplicate/stale guards and playback feedback |
| `components/voice/useHandsFree.ts` | React ownership and hidden-page cleanup |
| `components/Chat.tsx` | Existing chat submission, context, draft preservation and interruption |
| `backend/june/realtime_engine.py` | Actual Pipecat processors, Vosk and CPU Silero inference |
| `backend/june/realtime_state.py` | Turn boundaries, bounded pre-roll, Whisper jobs and follow-up timer |
| `backend/june/realtime_socket.py` | Single-session lock, packet validation and disconnect cleanup |
| `backend/june/realtime_assets.py` | Exact dependency versions and model checksum readiness |
| `scripts/realtime-setup.py` | Official download, hash check, safe extraction and CPU smoke checks |

## Limits and privacy

- One hands-free session across tabs. A competing tab receives an actionable error.
- PCM packets are normally 640 bytes / 20 ms; the server accepts at most 4096 bytes per packet and 32 KB controls. Pending processing and browser transport queues are capped at about two seconds.
- The worklet bounds unacknowledged packets. A congested path stops visibly instead of silently discarding part of a question.
- At most 30 seconds per utterance, 10 seconds to start a question after waking, and 30 seconds for follow-up. Transcription uses the existing one-job limit and 120-second timeout.
- Requests are restricted to local hosts and June’s local browser origins. One local backend worker owns the session lock.
- Raw audio is temporary. The last two seconds exist in RAM for pre-roll; utterance audio goes only to this Mac’s backend. Whisper temporary files are removed on completion/cancellation. Runtime logs do not include audio or transcript contents. Written conversation remains temporary in the page.
- The RMS meter measures microphone samples; Silero confidence measures speech likelihood. Neither is an amplitude measurement of system speech synthesis. Speech animation remains explicitly approximate.
- No paid service or account keys. The locked Pipecat distribution has optional client libraries among its dependencies; June instantiates only these local detectors and the existing local model adapter.
- This is CPU operation on an Intel Mac with 8 GB RAM. A one-second total response is an aspiration, not a guarantee. Latency depends on question length, model warmth and system load.

## Readiness and recovery

`GET /api/voice/status` reports local package/model readiness and whether a voice session is occupied. Engine/model assets live in `~/Library/Application Support/June/realtime` (or `JUNE_REALTIME_HOME`). Do not add these assets or Python environments to Git.

If setup is missing/corrupt, rerun `npm run realtime:setup` and restart June. If microphone permission is denied, allow this localhost page in browser settings, then enable again. A delayed grant after cancellation immediately releases tracks. Lost connections stop the microphone and old work; there is no automatic reconnection.

For accidental wake-ups use headphones, reduce speaker volume, or disable hands-free. Restricted vocabulary recognition can still miss accents or produce false detections; it is not a purpose-trained wake-word model.

## Verification gate

Automated tests and synthetic speech fixtures are useful evidence but cannot establish a human hands-free conversation. See `docs/phase-5-verification.md` for observed results and remaining checks. The roadmap’s Phase 5 build checkbox must stay unchecked until a real microphone conversation includes a spoken reply, follow-up and interruption. Preserve all learning boxes and personality answers. Only then export a fresh progress backup.

Official references: [Pipecat pipelines](https://docs.pipecat.ai/pipecat/learn/pipeline), [Vosk](https://alphacephei.com/vosk/install), [Silero VAD](https://github.com/snakers4/silero-vad), [MDN WebRTC](https://developer.mozilla.org/en-US/docs/Web/API/RTCPeerConnection).

## Number and non-speech safeguards

Whisper stays on the existing base.en decoder. Twenty clean synthetic fixtures correctly distinguished 5060, 3060, 4060 and an unrelated code, including Indian English synthesis; this does not prove human accuracy. The reported conversation also showed a correct 5070 Ti transcript being changed to 3070 Ti by Qwen.

- Recognised noise annotations such as `*cough*` are removed. Ordinary text mentioning a cough stays intact.
- Three or more consecutive spoken digit words are joined (`five zero six zero` → `5060`); valid numbers are never remapped to another number. Ambiguous repetitions such as `506060` remain unchanged.
- The prompt prioritises corrections and admits missing current product knowledge.
- In a GPU discussion, when the latest question identifies a card, sentences are buffered and checked before speech. An obvious substitution of another named GPU becomes an honest clarification. Comparisons in the same sentence as the requested model remain allowed. Model suffixes such as Ti are part of the checked identity. This narrow identity check does not verify specifications, prices or every possible wording.
- Manual Hold to talk still provides editable review. No new model, paid service, recording storage or external lookup was added.

For the later false-interruption repair, human check and correction-context regression results, see [voice-false-interruptions.md](voice-false-interruptions.md).
