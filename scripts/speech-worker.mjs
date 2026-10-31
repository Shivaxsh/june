// Build June's source against the already installed, pinned Whisper libraries.
// All binaries/build output remain in the private speech home, outside Git.
import { spawn } from 'node:child_process';
import { access, mkdir, realpath } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { homedir } from 'node:os';
import { join, relative, resolve, isAbsolute } from 'node:path';
import { fileURLToPath } from 'node:url';
if (existsSync('.env.local')) process.loadEnvFile('.env.local');
const repository = fileURLToPath(new URL('..', import.meta.url));
const speechHome = () => process.env.JUNE_SPEECH_HOME || join(homedir(), 'Library', 'Application Support', 'June', 'speech');
const workerPath = root => join(root, 'worker', 'build', 'bin', 'june-whisper-worker');
function run(command, args, { capture = false, ...options } = {}) {
  return new Promise((resolvePromise, reject) => {
    const child = spawn(command, args, { stdio: capture ? ['ignore', 'pipe', 'ignore'] : 'inherit', ...options });
    let output = '';
    child.stdout?.on('data', chunk => { output += chunk; if (output.length > 4096) child.kill('SIGKILL'); });
    child.on('error', reject);
    child.on('close', code => code === 0 ? resolvePromise(output.trim()) : reject(new Error(`Speech worker build command failed (${code}). Run npm run speech:setup.`)));
  });
}
async function outsideRepository(root) {
  // Resolve existing parents as well, so a symlink cannot put build output in Git.
  let candidate = resolve(root);
  while (!existsSync(candidate)) {
    const parent = resolve(candidate, '..');
    if (parent === candidate) break;
    candidate = parent;
  }
  candidate = await realpath(candidate);
  const rel = relative(await realpath(repository), candidate);
  if (!rel || (!rel.startsWith('..' + '/') && rel !== '..' && !isAbsolute(rel))) {
    throw new Error('Speech worker runtime must be outside the repository. Set JUNE_SPEECH_HOME to a private application-data folder.');
  }
}
export async function setupWorker({ root = speechHome() } = {}) {
  root = resolve(root);
  await outsideRepository(root);
  const source = join(root, 'whisper.cpp');
  const cmake = join(root, 'tools', 'bin', 'cmake');
  try { await access(cmake); await access(join(source, 'build', 'src', 'libwhisper.a')); }
  catch { throw new Error('Pinned Whisper libraries/private CMake are missing. Run npm run speech:setup first.'); }
  if (await run('git', ['describe', '--tags', '--exact-match', 'HEAD'], { cwd: source, capture: true }) !== 'v1.9.5') {
    throw new Error('Speech worker requires the pinned official whisper.cpp v1.9.5 installation. Run npm run speech:setup.');
  }
  if (!(await run(cmake, ['--version'], { capture: true })).startsWith('cmake version 3.31.6\n')) {
    throw new Error('Speech worker requires private CMake 3.31.6. Run npm run speech:setup.');
  }
  const build = join(root, 'worker', 'build');
  await mkdir(join(root, 'worker'), { recursive: true, mode: 0o700 });
  await run(cmake, ['-S', join(repository, 'native', 'whisper'), '-B', build,
    '-DCMAKE_BUILD_TYPE=Release', `-DJUNE_WHISPER_SOURCE=${source}`]);
  await run(cmake, ['--build', build, '--target', 'june-whisper-worker', '-j', '2']);
  return workerPath(root);
}
export async function checkWorker({ root = speechHome(), timeoutMs = 120000 } = {}) {
  await access(workerPath(root));
  await access(join(root, 'ggml-base.en.bin'));
  // Only load readiness, no inference. stdout is bounded and never printed.
  await new Promise((resolvePromise, reject) => {
    const child = spawn(workerPath(root), ['--model', join(root, 'ggml-base.en.bin')], { stdio: ['pipe', 'pipe', 'ignore'] });
    let buffer = Buffer.alloc(0), ready = false, error;
    const stop = reason => { error ||= reason; child.kill('SIGKILL'); };
    const timer = setTimeout(() => stop(new Error('Speech worker readiness timed out.')), timeoutMs);
    child.stdin.on('error', () => {});
    child.stdout.on('data', chunk => {
      if (ready) { stop(new Error('Unexpected speech worker protocol output.')); return; }
      if (buffer.length + chunk.length > 65536) { stop(new Error('Oversized speech worker protocol reply.')); return; }
      buffer = Buffer.concat([buffer, chunk]);
      if (!buffer.includes(10)) return;
      try {
        const message = JSON.parse(buffer.toString('utf8'));
        if (message.type !== 'ready' || message.protocol !== 1 || message.model !== 'base.en') throw Error();
        ready = true;
        child.stdin.end();
      } catch { stop(new Error('Invalid speech worker readiness protocol.')); }
    });
    child.on('error', reason => { error = reason; });
    child.on('close', code => {
      clearTimeout(timer);
      if (error) reject(error);
      else if (code !== 0 || !ready) reject(new Error('Speech worker did not become ready. Run npm run speech:setup.'));
      else resolvePromise();
    });
  });
}
if (process.argv[1] === fileURLToPath(import.meta.url)) {
  try {
    if (process.argv[2] === 'check') await checkWorker();
    else if (!process.argv[2] || process.argv[2] === 'setup') { await setupWorker(); await checkWorker(); }
    else throw new Error('Use speech-worker.mjs setup or check.');
    console.log('Resident Whisper base.en worker is ready.');
  } catch (error) { console.error(error.message); process.exitCode = 1; }
}
