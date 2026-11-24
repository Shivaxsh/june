import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';
const source = await readFile(new URL('../lib/voice/audio-recovery.ts', import.meta.url), 'utf8');
const R = await import('data:text/javascript;base64,' + Buffer.from(ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText).toString('base64'));
const hook = await readFile(new URL('../components/voice/useVoice.ts', import.meta.url), 'utf8');
const panel = await readFile(new URL('../components/voice/VoicePanel.tsx', import.meta.url), 'utf8');

test('status phases: only fully ready native output counts as ready', () => {
  assert.equal(R.audioPhase({ state: 'ready', nativeReady: true, providerState: 'ready' }), 'ready');
  assert.equal(R.audioPhase({ state: 'ready', nativeReady: false, providerState: 'ready' }), 'unavailable');
  assert.equal(R.audioPhase({ state: 'ready', nativeReady: true, providerState: 'error' }), 'unavailable');
  assert.equal(R.audioPhase({ state: 'preparing' }), 'preparing');
  assert.equal(R.audioPhase({ state: 'checking' }), 'preparing');
  for (const state of ['error', 'offline', 'missing', 'setup-required']) assert.equal(R.audioPhase({ state }), 'unavailable');
});

test('polling is bounded: steady while preparing, backing off while unavailable, then it stops', () => {
  assert.equal(R.nextCheckDelay('ready', 0), R.HEALTHY_CHECK_MS, 'a ready page keeps a slow health check');
  assert.equal(R.nextCheckDelay('ready', 10_000), R.HEALTHY_CHECK_MS, 'healthy checks never speed up or stop');
  assert.equal(R.HEALTHY_CHECK_MS, 30_000);
  assert.equal(R.nextCheckDelay('preparing', 0), 2000);
  assert.equal(R.nextCheckDelay('preparing', 30), 5000);
  assert.equal(R.nextCheckDelay('preparing', R.MAX_PREPARING_CHECKS), null);
  assert.deepEqual([0, 1, 2, 3, 4, 5, 6, 11].map(n => R.nextCheckDelay('unavailable', n)), [2000, 4000, 8000, 16000, 32000, 60000, 60000, 60000]);
  assert.equal(R.nextCheckDelay('unavailable', R.MAX_UNAVAILABLE_CHECKS), null);
});

test('the voice list reloads only on a transition into ready', () => {
  assert.equal(R.shouldReloadVoices('unavailable', 'ready'), true);
  assert.equal(R.shouldReloadVoices('preparing', 'ready'), true);
  assert.equal(R.shouldReloadVoices('ready', 'ready'), false);
  assert.equal(R.shouldReloadVoices(undefined, 'ready'), false, 'the first mount already loads the list');
  assert.equal(R.shouldReloadVoices('ready', 'unavailable'), false);
});

test('recovery copy is truthful: no promise to fix the Mac audio service', () => {
  assert.equal(R.recoveryMessage({ phase: 'ready', gaveUp: false, delayMs: 0 }), '');
  assert.match(R.recoveryMessage({ phase: 'preparing', gaveUp: false, delayMs: 2000 }), /Preparing June’s voice/);
  assert.match(R.recoveryMessage({ phase: 'unavailable', gaveUp: false, delayMs: 8000 }), /Checking again in 8 s/);
  const gaveUp = R.recoveryMessage({ phase: 'unavailable', gaveUp: true, delayMs: 0 });
  assert.match(gaveUp, /Automatic audio checks have paused/);
  assert.match(gaveUp, /Refresh audio/);
  assert.doesNotMatch(gaveUp, /can’t repair|broken|audio service/i, 'no categorical blame on macOS');
  assert.doesNotMatch(gaveUp + R.recoveryMessage({ phase: 'unavailable', gaveUp: false, delayMs: 8000 }), /fixed|repaired|restarting your Mac/i);
});

test('the hook keeps one timer, resets the budget on manual refresh, and never touches the mic or replays speech', () => {
  const effect = hook.slice(hook.indexOf('// Audio recovery:'), hook.indexOf('}, [audioStatus]);'));
  assert.match(effect, /const delay = nextCheckDelay\(phase, recoveryAttempt\.current\);/);
  assert.match(effect, /if \(shouldReloadVoices\(before, phase\) && !voicesReady\.current\) void registry\.current\?\.refresh\(\);/);
  assert.match(effect, /return \(\) => clearTimeout\(timer\);/);
  assert.doesNotMatch(effect, /handsFree|start\(|replay\(|preview\(|getUserMedia|recognition\.current\?\.start/);
  assert.match(hook, /refresh: \(\) => \{ recoveryAttempt\.current = 0;/);
  assert.doesNotMatch(hook, /if \(audioStatus\.state !== 'preparing'\) return;/, 'the old preparing-only loop is gone');
  assert.match(panel, /voice\.audioRecovery\?\.message/);
});

test('a reported output failure is unavailable even when the provider and native helper say ready; voiceWarm alone never is', () => {
  assert.equal(R.audioPhase({ state: 'ready', nativeReady: true, providerState: 'ready', outputError: 'Audio output was interrupted.' }), 'unavailable');
  assert.equal(R.audioPhase({ state: 'preparing', nativeReady: true, providerState: 'ready', outputError: 'x' }), 'unavailable');
  // JUNE_PREWARM defaults off, so voiceWarm can stay false forever on a healthy Mac: it must not gate output.
  assert.equal(R.audioPhase({ state: 'ready', nativeReady: true, providerState: 'ready', voiceWarm: false }), 'ready');
  assert.equal(R.outputUsable({ nativeReady: true, providerState: 'ready', voiceWarm: false }), true);
  assert.equal(R.outputUsable({ nativeReady: true, providerState: 'ready', outputError: 'x' }), false);
  assert.equal(R.outputUsable({ nativeReady: true, providerState: 'ready', outputError: null }), true);
  assert.equal(R.outputUsable({ nativeReady: false, providerState: 'ready' }), false);
  assert.match(R.recoveryMessage({ phase: 'unavailable', gaveUp: false, delayMs: 4000, outputError: true }), /output stopped working/);
});

test('a timer alert needs warm output: voiceWarm true, or a ready status when prewarm is off; a cold model does not matter', () => {
  assert.equal(R.alertOutputWarm({ state: 'ready', voiceWarm: false }), true, 'prewarm off: the backend says ready');
  assert.equal(R.alertOutputWarm({ state: 'preparing', voiceWarm: true, modelWarm: false }), true, 'only the model is cold');
  assert.equal(R.alertOutputWarm({ state: 'preparing', voiceWarm: false }), false, 'prewarm on, output not prepared yet');
  assert.equal(R.alertOutputWarm({ state: 'ready', voiceWarm: true, outputError: 'x' }), false);
});

test('the page notices helper death without a reload: health checks while visible, plus focus, visibility, device and speech-error checks', () => {
  assert.match(hook, /if \(delay === null \|\| \(phase === "ready" && document\.hidden\)\) return;/, 'no health checks while hidden');
  assert.match(hook, /window\.addEventListener\("focus", check\)/);
  assert.match(hook, /document\.addEventListener\("visibilitychange", whenVisible\)/);
  assert.match(hook, /navigator\.mediaDevices\?\.addEventListener\?\.\("devicechange", check\)/);
  assert.match(hook, /if \(now - lastCheck\.current < 2000\) return;/, 'event checks are debounced');
  assert.match(hook, /useEffect\(\(\) => \{ if \(speechState\.error\) void refreshAudio\(false\); \}, \[speechState\.error\]\);/);
  const triggers = hook.slice(hook.indexOf('// Event-driven checks'), hook.indexOf('}, [speechState.error]);'));
  assert.doesNotMatch(triggers, /replay\(|preview\(|recognition\.current\?\.start|getUserMedia|handsFree/);
});
