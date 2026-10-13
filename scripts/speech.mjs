// Private, pinned CPU-only speech runtime. Nothing is installed globally.
import { spawn } from 'node:child_process';
import { access, mkdir, readFile, writeFile, rename, rm } from 'node:fs/promises';
import { existsSync, createReadStream, createWriteStream } from 'node:fs';
import { pipeline } from 'node:stream/promises';
import { Readable } from 'node:stream';
import { createHash } from 'node:crypto';
import { homedir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
if (existsSync('.env.local')) process.loadEnvFile('.env.local');
export const root = process.env.JUNE_SPEECH_HOME || join(homedir(), 'Library', 'Application Support', 'June', 'speech');
const source = join(root, 'whisper.cpp');
const model = join(root, 'ggml-base.en.bin');
const binary = join(source, 'build', 'bin', 'whisper-cli');
const exists = async path => { try { await access(path); return true; } catch { return false; } };
function run(command, args, options = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { stdio: 'inherit', ...options });
    child.on('error', reject); child.on('close', code => code === 0 ? resolve() : reject(new Error(`${command} failed (${code})`)));
  });
}
async function hash(path) { const digest = createHash('sha256'); for await (const chunk of createReadStream(path)) digest.update(chunk); return digest.digest('hex'); }
export async function check() {
  if (!await exists(binary) || !await exists(model)) throw new Error('Local speech is not installed. Run npm run speech:setup.');
  const manifest = JSON.parse(await readFile(join(root, 'ready.json'), 'utf8'));
  if (manifest.version !== 'v1.9.5' || manifest.model !== 'base.en' || await hash(model) !== manifest.sha256) throw new Error('Speech installation failed its integrity check. Run npm run speech:setup.');
  await run(binary, ['--help']);
  console.log('Whisper base.en is installed and verified. Audio stays on this Mac.');
}
async function setup() {
  await mkdir(root, { recursive: true, mode: 0o700 });
  const env = join(root, 'tools');
  if (!await exists(join(env, 'bin', 'python'))) await run('python3', ['-m', 'venv', env]);
  await run(join(env, 'bin', 'python'), ['-m', 'pip', 'install', 'cmake==3.31.6']);
  if (!await exists(join(source, '.git'))) await run('git', ['clone', '--depth', '1', '--branch', 'v1.9.5', 'https://github.com/ggml-org/whisper.cpp.git', source]);
  await run('git', ['checkout', '--detach', 'v1.9.5'], { cwd: source });
  const cmake = join(env, 'bin', 'cmake');
  await run(cmake, ['-S', source, '-B', join(source, 'build'), '-DCMAKE_BUILD_TYPE=Release', '-DGGML_METAL=OFF', '-DGGML_CUDA=OFF', '-DGGML_OPENMP=OFF', '-DWHISPER_COREML=OFF', '-DWHISPER_BUILD_TESTS=OFF', '-DBUILD_SHARED_LIBS=OFF']);
  await run(cmake, ['--build', join(source, 'build'), '--target', 'whisper-cli', '-j', '2']);
  // Hugging Face publishes the LFS SHA-256. Verify it, not just the filename.
  const metadataResponse = await fetch('https://huggingface.co/api/models/ggerganov/whisper.cpp/tree/main?recursive=false&expand=true');
  if (!metadataResponse.ok) throw new Error('Could not obtain the model checksum. Retry setup.');
  const metadata = await metadataResponse.json();
  const entry = metadata.find(item => item.path === 'ggml-base.en.bin');
  const expected = entry?.lfs?.oid;
  if (!/^[a-f0-9]{64}$/.test(expected || '')) throw new Error('The official model checksum was unavailable. Retry setup.');
  if (!await exists(model) || await hash(model) !== expected) {
    const part = model + '.part';
    try {
      const response = await fetch('https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin');
      if (!response.ok || !response.body) throw new Error('The model download failed. Retry setup.');
      await pipeline(Readable.fromWeb(response.body), createWriteStream(part, { mode: 0o600 }));
      if (await hash(part) !== expected) throw new Error('The downloaded model checksum did not match. Retry setup.');
      await rename(part, model);
    } finally { await rm(part, { force: true }); }
  }
  const output = join(root, 'smoke');
  await run(binary, ['-m', model, '-f', join(source, 'samples', 'jfk.wav'), '-t', '2', '-ng', '-l', 'en', '-oj', '-of', output, '-np']);
  const result = JSON.parse(await readFile(output + '.json', 'utf8'));
  if (!result.transcription?.map(item => item.text).join(' ').toLowerCase().includes('country')) throw new Error('Speech smoke transcription failed. No readiness marker was saved.');
  await rm(output + '.json', { force: true });
  await writeFile(join(root, 'ready.json'), JSON.stringify({ version: 'v1.9.5', model: 'base.en', sha256: expected, verifiedAt: new Date().toISOString() }, null, 2), { mode: 0o600 });
  await check();
}
if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const action = process.argv[2];
  try { if (action === 'setup') await setup(); else if (action === 'check') await check(); else throw new Error('Use speech:setup or speech:check.'); }
  catch (error) { console.error(error.message); process.exitCode = 1; }
}
