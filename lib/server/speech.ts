import { createReadStream } from 'node:fs';
import { createHash } from 'node:crypto';
import { spawn } from 'node:child_process';
import { access, mkdtemp, readFile, writeFile, rm, stat } from 'node:fs/promises';
import { homedir, tmpdir } from 'node:os';
import { join } from 'node:path';
import { MAX_AUDIO_BYTES, validateWav } from '../voice/pcm';
export class SpeechError extends Error {
  constructor(public code: string, message: string, public status = 503) { super(message); }
}
const settings = () => {
  const root = process.env.JUNE_SPEECH_HOME || join(homedir(), 'Library', 'Application Support', 'June', 'speech');
  return { root, binary: join(root, 'whisper.cpp', 'build', 'bin', 'whisper-cli'), model: join(root, 'ggml-base.en.bin') };
};
export function localRequest(request: Request): boolean {
  try {
    const url = new URL(`http://${request.headers.get('host')}`); const origin = request.headers.get('origin');
    return ['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname) && (!origin || origin === url.origin);
  } catch { return false; }
}
let verifiedModel = "";
export async function speechStatus() {
  const config = settings();
  try { await access(config.binary); } catch { return { state: 'runtime-missing', engine: 'whisper.cpp', model: 'base.en', message: 'Local speech needs setup. Run npm run speech:setup, then refresh speech.' }; }
  try { await access(config.model); } catch { return { state: 'model-missing', engine: 'whisper.cpp', model: 'base.en', message: 'Whisper base.en is missing. Run npm run speech:setup, then refresh speech.' }; }
  try {
    const ready = JSON.parse(await readFile(join(config.root, 'ready.json'), 'utf8'));
    const model = await stat(config.model);
    if (ready.version !== 'v1.9.5' || ready.model !== 'base.en' || !/^[a-f0-9]{64}$/.test(ready.sha256) || model.size < 100000000) throw new Error();
    const identity = `${config.model}:${model.size}:${model.mtimeMs}:${ready.sha256}`;
    if (verifiedModel !== identity) {
      const digest = createHash('sha256'); for await (const chunk of createReadStream(config.model)) digest.update(chunk);
      if (digest.digest('hex') !== ready.sha256) throw new Error();
      verifiedModel = identity;
    }
    return { state: 'ready', engine: 'whisper.cpp', model: 'base.en', message: 'Local English transcription · Whisper base.en · ready on this Mac' };
  } catch { return { state: 'error', engine: 'whisper.cpp', model: 'base.en', message: 'Speech installation has not passed its transcription check. Run npm run speech:setup.' }; }
}
export async function readAudio(request: Request): Promise<Uint8Array> {
  if (Number(request.headers.get('content-length')) > MAX_AUDIO_BYTES) throw new SpeechError('too-large', 'Audio is too large. Record at most 30 seconds.', 413);
  if (!request.body) throw new SpeechError('invalid-audio', 'No WAV audio was received.', 400);
  const reader = request.body.getReader(); const chunks: Uint8Array[] = []; let bytes = 0;
  try {
    while (true) {
      request.signal.throwIfAborted(); const { value, done } = await reader.read(); if (done) break;
      bytes += value.byteLength; if (bytes > MAX_AUDIO_BYTES) { await reader.cancel(); throw new SpeechError('too-large', 'Audio is too large. Record at most 30 seconds.', 413); } chunks.push(value);
    }
  } finally { reader.releaseLock(); }
  const result = new Uint8Array(bytes); let offset = 0; for (const chunk of chunks) { result.set(chunk, offset); offset += chunk.byteLength; } return result;
}
// Store the lock on the process global so development hot reload cannot spawn a
// second CPU-heavy transcription while the first route instance is still busy.
const shared = globalThis as typeof globalThis & { juneSpeechBusy?: boolean };
export async function transcribe(data: Uint8Array, signal: AbortSignal) {
  try { validateWav(data); } catch (error) { throw new SpeechError('invalid-audio', (error as Error).message, 400); }
  if (shared.juneSpeechBusy) throw new SpeechError('busy', 'June is already transcribing another recording. Wait, then try again.', 409);
  shared.juneSpeechBusy = true;
  let directory = '';
  const started = performance.now();
  try {
    signal.throwIfAborted();
    const status = await speechStatus(); if (status.state !== 'ready') throw new SpeechError(status.state, status.message);
    directory = await mkdtemp(join(tmpdir(), 'june-speech-'));
    const input = join(directory, 'input.wav'), output = join(directory, 'result');
    await writeFile(input, data, { mode: 0o600 }); signal.throwIfAborted();
    const config = settings();
    await new Promise<void>((resolve, reject) => {
      const child = spawn(config.binary, ['-m', config.model, '-f', input, '-t', '2', '-ng', '-l', 'en', '-oj', '-of', output, '-np', '-nt'], { stdio: ['ignore', 'ignore', 'pipe'] });
      let failure: Error | undefined;
      let escalation: ReturnType<typeof setTimeout> | undefined;
      const terminate = (error: Error) => { if (failure) return; failure = error; child.kill('SIGTERM'); escalation = setTimeout(() => child.kill('SIGKILL'), 1000); };
      const abort = () => terminate(new SpeechError('cancelled', 'Transcription cancelled.', 499));
      const timer = setTimeout(() => terminate(new SpeechError('timeout', 'Transcription took too long. Try a shorter recording.', 504)), 120000);
      // Drain engine diagnostics without logging private text or keeping it in memory.
      child.stderr?.on('data', () => {});
      signal.addEventListener('abort', abort, { once: true }); if (signal.aborted) abort();
      const cleanup = () => { clearTimeout(timer); clearTimeout(escalation); signal.removeEventListener('abort', abort); };
      child.on('error', () => { cleanup(); reject(new SpeechError('engine-failed', 'The local speech engine could not start. Run npm run speech:check, then retry.')); });
      child.on('close', code => { cleanup(); if (failure) reject(failure); else if (code !== 0) reject(new SpeechError('engine-failed', 'The local speech engine failed. Run npm run speech:check, then retry.')); else resolve(); });
    });
    signal.throwIfAborted();
    if ((await stat(output + '.json')).size > 262144) throw new SpeechError('invalid-result', 'The speech engine returned an invalid transcript. Try again.');
    const result = JSON.parse(await readFile(output + '.json', 'utf8'));
    if (!Array.isArray(result.transcription)) throw new SpeechError('invalid-result', 'The speech engine returned an invalid transcript. Try again.');
    const text = result.transcription.map((item: { text?: unknown }) => typeof item.text === 'string' ? item.text : '').join(' ').replace(/\s+/g, ' ').trim();
    if (!text || /^\s*[\[(].*[\])]\s*$/.test(text)) throw new SpeechError('no-speech', 'No words were recognised. Try a clear, short sentence.', 422);
    return { text, engine: 'whisper.cpp', model: 'base.en', durationMs: Math.round(performance.now() - started) };
  } finally {
    try { if (directory) await rm(directory, { recursive: true, force: true }); } finally { shared.juneSpeechBusy = false; }
  }
}
