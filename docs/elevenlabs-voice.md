# June’s saved voice

June speaks only with saved ElevenLabs voice `ZYufQennDT5PFsid8v3E`, using `eleven_v4`. This is synthesis of new sentences, not training. Qwen training cannot change this voice. Voice consistency, pronunciation and emotional interpretation are not guaranteed.

## Setup and recovery

1. Save `ELEVENLABS_API_KEY=...` privately in ignored `.env.local`. Restrict the key to synthesis and read access to voices, models and account usage. Never use a public/browser environment variable or commit the key.
2. Run `npm run audio:setup` to rebuild the native helper; then `npm run build` and `npm start`. The app remains at http://127.0.0.1:3001/.
3. Check the voice panel. Readiness checks only read metadata and prepare the output graph: they do not generate speech or request microphone access.
4. Preview Steady, Calm and Bright. These keep the same voice ID; Calm and Bright add restrained delivery cues only to synthesis input. Captions and written replies exclude those cues. Existing voice settings remain provider defaults; June does not edit the saved voice.
5. Enable hands-free deliberately for microphone use. Browser recording remains an explicitly selected manual-input fallback; it does not supply an alternate speaking voice.

The server verifies Free tier, disabled usage extension, the exact saved voice, model access and remaining allowance before synthesis. Requests are serialized and reserve a conservative usage amount in the private `voice-usage.json` ledger before sending text. Do not discard this ledger during recovery: delayed provider usage must not permit local re-spending. Restore it along with the private database/configuration. Cancellation can still use provider credits. There is no subscription change, top-up or paid fallback.

Quota in the UI is account-level. A separately configured key limit can be smaller. Invalid/missing credentials, access failures, exhausted account/key quota, network errors or helper failures leave June text-only with an actionable error; they never select Nicky or a browser voice. Update a restricted key privately and restart June after correcting credentials. Never include `.env.local`, recordings, binaries, private reports or the usage ledger in Git.

For bounded validation only, launch with `JUNE_VOICE_VALIDATION_CHAR_LIMIT=1500 npm start`. This checks the private ledger’s cumulative input characters, including delivery cues, before generation. A normal `npm start` removes this test-only cap but retains account Free checks and any provider key limit. Do not change provider spending settings to recover from exhausted quota.

## Data and playback

Spoken text goes to ElevenLabs and is governed by its retention rules; this integration does not promise zero retention. Microphone audio, Whisper, Qwen, approved memory and chats stay local. Generated audio is temporary, streamed as mono 24 kHz PCM through the existing AVAudioEngine graph so echo processing receives the playback reference. No output is persisted to Git or disk.

Stop, mute, replacement requests, New chat, navigation, hidden tabs and disconnect cancel owned synthesis/playback. Segment/request ownership prevents old work from resuming. Captions use approximate sentence highlighting; orb intensity uses measured PCM. Cloud/network latency is additional to local model and transcription time.

## Verification record — 2026-11-04

Four real local HTTP speech requests used the fixed voice and native playback: Steady, Calm, Bright and names/GPU identifiers. Each delivered accepted/start/end events successfully. Total synthesis input was 226 characters including cues, below the 1,500-character validation budget. The user confirmed: “Voice matches and the presets sound distinct.” Emotional delivery has audible user approval; this does not mark learning topics mastered or the entire phase complete.

Request-to-first-playback event timings: Steady 4.810 s, Calm 4.215 s, Bright 6.603 s, pronunciation 1.849 s. These are four cloud synthesis samples, not a voice-conversation latency benchmark or microphone acoustic measurements. Names and identifiers were included; no pronunciation alias is added without a demonstrated error.

Automated checks cover missing/invalid credentials, non-Free/access rejection, quota reservations and exhaustion, fixed identity, expression cues, concurrent requests, stream cancellation, native PCM ownership, stale callbacks and no fallback. Real human hands-free echo/interruption acceptance with the new cloud voice is still pending. Readiness and synthetic output tests cannot prove speaker-room reliability.

Official references: [subscription metadata](https://elevenlabs.io/docs/api-reference/user/subscription/get), [streaming synthesis](https://elevenlabs.io/docs/api-reference/text-to-speech/stream), [API pricing](https://elevenlabs.io/pricing/api).

Final checks: 340 Python regressions and 140 JavaScript regressions passed; TypeScript and the production build passed. After the final quota-display adjustment, all 12 provider tests passed again. The rebuilt helper passed its no-microphone conversion/PCM checks. Browser verification confirmed the fixed voice, free allowance notice, available preview while Qwen warms and microphone remaining off. A browser preview produced a first-playback event at 2.25 s; its voice control returned to stopped.
