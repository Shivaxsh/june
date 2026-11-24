# Daily assistant (Phase 8.1)

Systems → Daily contains an on-request briefing, local goals, opt-in city weather,
Google primary-calendar reading and a selected Apple Music playlist. Qwen 4B and
Heart voice are unchanged. No paid service, cloud inference, automatic permission
grant, location lookup or background microphone capture was introduced.

## Setup

### Weather

Click Enable weather after reviewing the two listed Open-Meteo hosts. Search for
a city, review its region/country, and choose Use city. Choose Celsius/Fahrenheit.
No browser location permission is used. The free API is for personal/non-commercial
use; attribution is shown in the interface. Turn off weather stops future fetches
and clears in-memory city-search/forecast caches.

### Google Calendar

1. In your Google Cloud project, enable Google Calendar API and configure the OAuth
   consent screen for your own use. Add your Google account as a test user when
   using Testing mode. This can require reconnecting after seven days.
2. Create OAuth credentials of type **Desktop app** and download their JSON.
3. In June, choose the file under Google OAuth client JSON. The browser reads it in
   memory and sends the client id/secret only to June's loopback backend. Credentials
   are stored in macOS Keychain, never browser storage, logs or project files.
4. Click Connect Google Calendar. Review Google's permission screen yourself.
   June requests only `calendar.events.readonly`, not Gmail or event editing.
5. After the callback says Calendar connected, return to June. Connection becomes
   verified only after token exchange and a successful primary-calendar probe.

The callback uses the configured loopback backend origin. OAuth uses PKCE S256,
random state, constant-time state comparison and a ten-minute attempt lifetime.
No account is connected by startup or by opening Systems. Calendar reads use the
chosen city's timezone, otherwise Asia/Kolkata for this installation. Expired or
refused grants require reconnect; temporary outages do not invalidate approval.
Disconnect disables local access even if Keychain is locked. Its message states
whether saved-credential removal and remote token revocation were verified.

### Apple Music

Click Allow June to control Music, then answer the macOS Automation prompt yourself.
Choose a playlist from your Music library. Playback uses your existing Music access;
June does not subscribe, buy content or substitute a different music service.
Play playlist or Start focus session proposes an exact plan; focus opens VS Code
then plays the named playlist. Remembered approval is bound to that exact payload.
Music success requires readback of both playing state and the playlist's persistent
identifier. A missing grant is an explicit error, never an empty library success.

The helper's self-test does not send Apple Events, open Music or ask for permission.
Rebuilding may cause macOS to ask again; grant is always a human setup step.

## Data and behaviour

- Goals are saved locally: up to twenty active and one hundred stored. Editing,
  completing, reopening and deleting use the displayed goal revision. Deleted
  records are hidden with a local tombstone, not purged by the UI.
- Briefing sections report independent `ok`, `not-configured` or `unavailable`
  states. Facts come from structured records, not generated model text.
- Forecasts cache in memory for ten minutes; fetched calendar events and briefing
  responses are not persisted or included in diagnostic reports.
- A typed/spoken Good morning or Brief me uses the same briefing builder. Live
  speech/text receives the facts; saved chat keeps only a private-briefing marker.
  Reopening/exporting that chat does not restore fetched calendar details.
- Button-generated briefings offer Hear briefing through the existing local voice
  path. Nothing speaks automatically merely because the panel loads.
- Scheduled briefings and page-closed delivery are not implemented in this slice.

## Verification ledger

Backend tests cover real ASGI routes, request receipts, stale revisions, capacity,
weather consent and source validation, private chat persistence, PKCE/state/scope,
callback replay/expiry, outages versus expired grants, revocation under Keychain
failure, Music permissions and playlist playback readback. New regressions were
observed failing before fixes; private-chat delivery was additionally checked after
implementation. Native Keychain/Music compilation and non-invasive self-tests pass.

Claude independently reviewed the backend and fixed frontend recovery, Unicode
length checks and enabled-versus-verified state handling. Mocked UI checks at 375
and 1440 pixels passed with no overflow, undersized controls or console errors.
Final full checks and real user account/Music/audible acceptance are recorded in the
handoff. Mocks and helper self-tests do not establish those live gates.

Final automated checks (15 November): typecheck exit0; JavaScript331/331;
backend598/598; production build exit0; diff check exit0. Actual restarted HTTP
endpoints and a temporary Good morning chat returned the default factual setup
notices without inference or speech. A real VS Code plan reused remembered
approval and completed with native verification. Google, weather and Music remain
disabled/unconfigured. Actual account/playback/hands-free acceptance is pending.
Direct final VS Code UI automation timed out; mocked responsive UI checks passed.
