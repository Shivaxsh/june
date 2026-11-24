# Local audio recovery

June detects native audio graph changes, failed output and a stopped helper. A reported output failure clears playback readiness and withdraws the speaking voice until recovery succeeds. Failed speech is never automatically replayed, and recovery never enables hands-free or opens the microphone.

An open, visible page checks healthy audio every 30 seconds. Returning to the page, a device change or a speech error also checks status. Failures use one slowing retry loop: preparation checks run every 2 then 5 seconds for up to roughly six minutes; unavailable checks back off from 2 to 60 seconds for roughly eight minutes. Refresh audio starts a fresh checking budget.

The backend prepares output only when June is idle. Each attempt has a 20-second timeout; status-triggered preparation is single flight and at least 30 seconds apart. A failed graph is replaced by retiring its idle native helper. Already loaded detectors, Whisper and Qwen remain loaded. Even when model prewarming is disabled, a known output failure can recover through an output-only check. No speech or microphone capture is used for that check.

Timer alerts wait for prepared output before spending their one persisted announcement claim. A failed or interrupted announcement is not automatically replayed; its finished card offers Hear again.

June can recover her own helper and reinitialize output after macOS restores a device. She cannot guarantee that a broken macOS audio service or disconnected hardware will recover. If other apps are also silent, check Mac Sound settings or restart system audio, then use Refresh audio. No administrator password belongs in a June chat.

Exact checks and live recovery evidence are recorded in `docs/handoff.md`.
