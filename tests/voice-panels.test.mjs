import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import ts from 'typescript';
const modules = new Map();
async function componentUrl(url) {
  if (modules.has(url.href)) return modules.get(url.href);
  const source = await readFile(url, 'utf8');
  let { outputText } = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext, jsx: ts.JsxEmit.ReactJSX } });
  outputText = outputText.replace(/from ["'](react(?:\/[^"']+)?)["']/g, (_, name) => `from ${JSON.stringify(import.meta.resolve(name))}`);
  for (const match of [...outputText.matchAll(/from ["'](\.[^"']+)["']/g)]) {
    const dependency = await componentUrl(new URL(match[1] + '.tsx', url));
    outputText = outputText.replace(match[0], `from ${JSON.stringify(dependency)}`);
  }
  const result = 'data:text/javascript;base64,' + Buffer.from(outputText).toString('base64'); modules.set(url.href, result); return result;
}
const component = async path => (await import(await componentUrl(new URL(path, import.meta.url)))).default;
const VoicePanel = await component('../components/voice/VoicePanel.tsx');
const HandsFreePanel = await component('../components/voice/HandsFreePanel.tsx');
const ReplyStatus = await component('../components/voice/ReplyStatus.tsx');
const noop = () => {};
const voice = {
  engine: 'native', browserCapture: false, browserCaptureSupported: true, choices: { selected: 'ZYufQennDT5PFsid8v3E', options: [{ id: 'ZYufQennDT5PFsid8v3E', name: 'June', accent: 'English' }], state: 'ready', message: 'June ready' },
  recognition: { phase: 'idle', transcript: '', error: '' }, speech: { phase: 'idle', error: '' },
  support: { recognition: true, speech: true, checked: true }, speakReplies: true,
  engineStatus: { state: 'ready', message: 'Local transcription ready' }, audioStatus: { nativeReady: true, providerState: 'ready', message: 'Native audio ready' },
  level: { current: 0 }, setSpeakReplies: noop, refresh: noop, refreshSpeech: noop, finishTalk: noop, setTranscript: noop, clearTranscript: noop, setBrowserCapture: noop,
};
const controls = { state: { phase: 'off', vad: 0, transcriptionMs: 0 }, active: false, status: { state: 'ready', message: 'Ready' }, level: { current: 0 }, pause: 'short', setPause: noop };
const render = (Component, props) => renderToStaticMarkup(React.createElement(Component, props));
test('June panel has fixed identity and explicit capture-only controls with no voice or engine selector', () => {
  const html = render(VoicePanel, { voice, onUse: noop, onActivate: noop });
  assert.match(html, /<strong>June<\/strong> · ElevenLabs/);
  assert.doesNotMatch(html, /<select|Audio engine|Nicky|browser word events/);
  assert.match(html, /<button[^>]*disabled=""[^>]*>Hold to talk/);
  assert.doesNotMatch(html, /<button[^>]*disabled=""[^>]*>Preview voice/);
  const browser = render(VoicePanel, { voice: { ...voice, browserCapture: true }, onUse: noop, onActivate: noop });
  assert.doesNotMatch(browser, /<button[^>]*disabled=""[^>]*>Hold to talk/);
  assert.match(browser, /replies always use her ElevenLabs voice through native playback/);
});
test('provider outage retains June identity, disables preview, and permits refresh and saved speech preference changes', () => {
  for (const state of ['setup-required', 'quota-exhausted', 'error']) {
    const html = render(VoicePanel, { voice: { ...voice, support: { ...voice.support, speech: false }, choices: { ...voice.choices, selected: '', state }, recognition: { ...voice.recognition, transcript: 'Manual transcript remains available' }, audioStatus: { providerState: state, providerMessage: 'Add key or refresh' } }, onUse: noop, onActivate: noop });
    assert.match(html, /<strong>June<\/strong> · ElevenLabs/);
    assert.match(html, /Add key or refresh/);
    assert.match(html, /<button[^>]*disabled=""[^>]*>Preview voice/);
    assert.doesNotMatch(html, /<button[^>]*disabled=""[^>]*>Refresh audio/);
    assert.doesNotMatch(html, /<input[^>]*disabled=""[^>]*\/> Speak replies/);
    assert.doesNotMatch(html, /<select|Nicky/);
    assert.match(html, /Manual transcript remains available/);
    assert.doesNotMatch(html, /<textarea[^>]*disabled=|<button[^>]*disabled=""[^>]*>Use transcript/);
  }
});
test('cloud notice discloses personal text and credits while raw microphone remains local', () => {
  const html = render(VoicePanel, { voice: { ...voice, audioStatus: { ...voice.audioStatus, quota: { remaining: 0, limit: 1000, used: 1000, resetAt: '2026-12-01T12:00:00Z' } } }, onUse: noop, onActivate: noop });
  assert.match(html, /including personal replies, is sent online to ElevenLabs/);
  assert.match(html, /Raw microphone audio stays on this Mac/);
  assert.match(html, /account allowance may exceed the separately restricted API-key limit/);
  assert.match(html, /0 credits remaining · 1,000 credit limit · 1,000 credits used · resets Dec 1, 2026/);
  assert.match(render(VoicePanel, { voice, onUse: noop, onActivate: noop }), /credit balance is unavailable/);
});
test('native permission and preparation states never claim that the microphone is on', () => {
  for (const phase of ['requesting', 'preparing', 'connecting']) {
    const html = render(HandsFreePanel, { controls: { ...controls, active: true, state: { ...controls.state, phase, permission: 'requesting', audioSource: 'native' } }, enabled: true, onStart: noop });
    assert.doesNotMatch(html, /Microphone on · local only/);
    assert.match(html, /Microphone permission requested/);
  }
});
test('multiple voice panels have distinct IDs and keep all pause choices with short selected', () => {
  const html = renderToStaticMarkup(React.createElement(React.Fragment, null,
    React.createElement(VoicePanel, { voice, onUse: noop, onActivate: noop }), React.createElement(VoicePanel, { voice, onUse: noop, onActivate: noop }),
    React.createElement(HandsFreePanel, { controls, enabled: true, onStart: noop }), React.createElement(HandsFreePanel, { controls, enabled: true, onStart: noop })));
  const ids = [...html.matchAll(/ id="([^"]+)"/g)].map(match => match[1]);
  assert.equal(new Set(ids).size, ids.length);
  assert.match(html, /<option value="short" selected="">Short · 0.8 seconds/);
  assert.match(html, /Normal · 1.5 seconds/); assert.match(html, /Patient · 2.5 seconds/);
});
test('repetition status preserves readable recovery and exposes only an explicit manual retry', () => {
  const html = render(ReplyStatus, { repetitionStopped: true, busy: false, onRetry: noop });
  assert.match(html, /Repetition stopped · text preserved/);
  assert.match(html, /<button[^>]*>Retry reply/);
  assert.match(render(ReplyStatus, { repetitionStopped: true, busy: true, onRetry: noop }), /<button[^>]*disabled=""/);
});

test('hands-free displays only observed timing stages and explains native sustained speech and explicit manual fallback', () => {
  const html = render(HandsFreePanel, { controls: { ...controls, audioSource: 'native', state: { ...controls.state, timings: { endDetection: 800, transcription: 230, invalid: -1 } } }, enabled: true, onStart: noop });
  assert.match(html, /End detection: 800 ms/); assert.match(html, /Transcription: 230 ms/);
  assert.doesNotMatch(html, /invalid|checks for words|Verified speech stops|Local verification/);
  assert.match(html, /sustained speech/); assert.match(html, /Choose browser audio/);
});
test('speech timing readout remains visible after playback ends and never invents missing measurements', () => {
  const html = render(VoicePanel, { voice: { ...voice, speech: { ...voice.speech, timings: { firstAudioMs: 1200, playbackMs: 2500, totalMs: 3700, nativeFirstAudioMs: 25, nativePlaybackMs: 2300 } } }, onUse: noop, onActivate: noop });
  assert.match(html, /Request → first audio: 1.20 s/); assert.match(html, /Playback elapsed: 2.50 s/);
  assert.match(html, /Request → last audio end: 3.70 s/);
  assert.match(html, /Native first segment preparation: 25 ms/); assert.match(html, /Last native segment playback: 2.30 s/);
  const missing = render(VoicePanel, { voice, onUse: noop, onActivate: noop });
  assert.doesNotMatch(missing, /Request → first audio|Playback elapsed/);
});


test('manual browser recording remains available regardless of cloud readiness', () => {
  for (const state of ['setup-required', 'quota-exhausted', 'error']) {
    const html = render(VoicePanel, { voice: {
      ...voice, browserCapture: true, support: { ...voice.support, recognition: false, speech: false },
      audioStatus: { state, providerState: state, message: 'Cloud unavailable' },
    }, onUse: noop, onActivate: noop });
    assert.match(html, /<button[^>]*disabled=""[^>]*>Preview voice/);
    assert.doesNotMatch(html, /<button[^>]*disabled=""[^>]*>Hold to talk|<button[^>]*disabled=""[^>]*>Start listening/);
    assert.doesNotMatch(html, /<input[^>]*disabled=""[^>]*\/> Use browser microphone/);
  }
});
