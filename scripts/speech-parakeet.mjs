// June's listening model: NVIDIA Parakeet TDT 0.6B v2 (English, int8 ONNX for sherpa-onnx), local and CPU-only.
// Downloaded from the pinned sherpa-onnx release, verified against its published SHA-256, then smoke-tested through
// the same resident worker June runs (backend/june/parakeet_worker.py). Nothing is installed globally.
import { spawn } from 'node:child_process';
import { access, mkdir, readFile, rename, rm } from 'node:fs/promises';
import { createReadStream, createWriteStream } from 'node:fs';
import { pipeline } from 'node:stream/promises';
import { Readable } from 'node:stream';
import { createHash } from 'node:crypto';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

// Must match backend/june/speech.py ENGINE / PARAKEET_ID / PARAKEET_DIR (kept in sync by a test).
export const ENGINE = 'parakeet';
export const PARAKEET_ID = 'parakeet-tdt-0.6b-v2-int8';
export const PARAKEET_DIR = 'parakeet/sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8';
const ARCHIVE = 'sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8.tar.bz2';
const ARCHIVE_URL = `https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/${ARCHIVE}`;
const ARCHIVE_SHA256 = '6fc4426b54aa549a0019b8a75b8dea59164e71790a37ac56a045ad57f915f714';  // the release's published digest
const FILES = ['encoder.int8.onnx', 'decoder.int8.onnx', 'joiner.int8.onnx', 'tokens.txt'];
const repository = fileURLToPath(new URL('..', import.meta.url));
const python = join(repository, 'backend', '.venv', 'bin', 'python');
const worker = join(repository, 'backend', 'june', 'parakeet_worker.py');

const exists = async path => { try { await access(path); return true; } catch { return false; } };
export async function hash(path) { const digest = createHash('sha256'); for await (const chunk of createReadStream(path)) digest.update(chunk); return digest.digest('hex'); }
function run(command, args, options = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { stdio: 'inherit', ...options });
    child.on('error', reject); child.on('close', code => code === 0 ? resolve() : reject(new Error(`${command} failed (${code})`)));
  });
}
export const parakeetModel = root => join(root, PARAKEET_DIR, 'encoder.int8.onnx');

export async function setupParakeet({ root }) {
  const folder = join(root, PARAKEET_DIR);
  if (!(await Promise.all(FILES.map(name => exists(join(folder, name))))).every(Boolean)) {
    await mkdir(join(root, 'parakeet'), { recursive: true, mode: 0o700 });
    const part = join(root, 'parakeet', ARCHIVE + '.part');
    try {
      const response = await fetch(ARCHIVE_URL);
      if (!response.ok || !response.body) throw new Error('The Parakeet model download failed. Retry setup.');
      await pipeline(Readable.fromWeb(response.body), createWriteStream(part, { mode: 0o600 }));
      if (await hash(part) !== ARCHIVE_SHA256) throw new Error('The downloaded Parakeet model checksum did not match. Retry setup.');
      await run('tar', ['-xjf', part, '-C', join(root, 'parakeet')]);
    } finally { await rm(part, { force: true }); }
  }
  await run(python, ['-c', 'import sherpa_onnx, numpy'], { stdio: 'ignore' }).catch(() => {
    throw new Error('sherpa-onnx is missing from June’s backend. Run npm run backend:setup, then npm run speech:setup.');
  });
}

/** Load the model through June's own worker and transcribe one bundled sample; resolves with the transcript. */
export function smokeParakeet({ root, sample, timeoutMs = 120000 }) {
  return new Promise(async (resolve, reject) => {
    const wav = await readFile(sample);
    const child = spawn(python, [worker, '--model', join(root, PARAKEET_DIR)], { stdio: ['pipe', 'pipe', 'ignore'] });
    let buffer = '', ready = false, done = false;
    const finish = (error, text) => { if (done) return; done = true; clearTimeout(timer); child.kill('SIGKILL'); error ? reject(error) : resolve(text); };
    const timer = setTimeout(() => finish(new Error('Parakeet readiness timed out.')), timeoutMs);
    child.on('error', error => finish(error));
    child.on('close', () => finish(new Error('Parakeet worker stopped. Run npm run speech:setup.')));
    child.stdout.on('data', chunk => {
      buffer += chunk;
      if (buffer.length > 65536) { finish(new Error('Oversized Parakeet reply.')); return; }
      let newline;
      while ((newline = buffer.indexOf('\n')) >= 0) {
        const message = JSON.parse(buffer.slice(0, newline)); buffer = buffer.slice(newline + 1);
        if (!ready) {
          if (message.type !== 'ready' || message.protocol !== 1 || message.model !== PARAKEET_ID) { finish(new Error('Invalid Parakeet readiness protocol.')); return; }
          ready = true;
          child.stdin.write(JSON.stringify({ type: 'transcribe', id: 'smoke', bytes: wav.length }) + '\n'); child.stdin.write(wav);
        } else if (message.type === 'result' && message.id === 'smoke') finish(null, message.text);
        else { finish(new Error('Parakeet smoke transcription failed.')); return; }
      }
    });
  });
}
