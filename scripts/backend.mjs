// A private Python environment, one local worker, and no global pip installs.
import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { resolve, join } from 'node:path';

export const root = fileURLToPath(new URL('../', import.meta.url));
if (existsSync(join(root, '.env.local'))) process.loadEnvFile(join(root, '.env.local'));
export const python = join(root, 'backend/.venv/bin/python');
export const version = '0.4.0';

export function address() {
  const url = new URL(process.env.JUNE_BACKEND_URL || 'http://127.0.0.1:8001');
  if (url.protocol !== 'http:' || !['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname)
    || url.username || url.password || url.pathname !== '/' || url.search || url.hash) {
    throw Error('JUNE_BACKEND_URL must be a local HTTP origin.');
  }
  return url;
}

function run(binary, args) {
  return new Promise((resolve, reject) => {
    const child = spawn(binary, args, { cwd: root, stdio: 'inherit' });
    child.on('error', reject);
    child.on('exit', code => code === 0 ? resolve() : reject(Error('Setup command failed. Check the output above.')));
  });
}

export function startBackend() {
  if (!existsSync(python)) throw Error('Python setup is missing. Run npm run backend:setup first.');
  const url = address();
  return spawn(python, ['-m', 'uvicorn', 'june.app:app', '--app-dir', 'backend', '--host', url.hostname.replace(/[\[\]]/g, ''),
    '--port', url.port || '80', '--workers', '1', '--ws-max-size', '32768', '--timeout-graceful-shutdown', '5', '--no-access-log'],
  { cwd: root, stdio: 'inherit', env: { ...process.env, PYTHONUNBUFFERED: '1', PYTHONDONTWRITEBYTECODE: '1', LOGURU_LEVEL: 'WARNING' } });
}

export async function health() {
  try {
    const response = await fetch(address().origin + '/health', { signal: AbortSignal.timeout(1500), redirect: 'error' });
    const value = await response.json();
    return { available: true, valid: response.ok && value.service === 'june-python' && value.version === version && value.state === 'ready', value };
  } catch (error) {
    if (error?.cause?.code === 'ECONNREFUSED') return { available: false, valid: false };
    // An occupied but unhealthy port must not be treated as free.
    return { available: true, valid: false };
  }
}

export async function stopChild(child) {
  if (!child || child.exitCode !== null || child.signalCode !== null) return;
  await new Promise(resolve => {
    const timer = setTimeout(() => child.kill('SIGKILL'), 8000);
    child.once('close', () => { clearTimeout(timer); resolve(); });
    child.kill('SIGTERM');
  });
}

async function main() {
  const action = process.argv[2];
  if (action === 'setup') {
    if (!existsSync(python)) await run('python3', ['-m', 'venv', 'backend/.venv']);
    await run(python, ['-m', 'pip', 'install', '-r', 'backend/requirements.lock']);
    console.log('June’s isolated Python backend is ready. Start June with npm start.');
  } else if (action === 'check') {
    const status = await health();
    if (!status.valid) throw Error('June’s Python backend is unavailable or incompatible. Restart June with npm start.');
    const results = await Promise.all(['/api/status', '/api/speech/status', '/api/voice/status'].map(async path => {
      const response = await fetch(address().origin + path, { signal: AbortSignal.timeout(10000), redirect: 'error' });
      return { path, ...await response.json() };
    }));
    console.log(JSON.stringify({ backend: status.value, services: results }, null, 2));
    if (results.some(result => result.state !== 'ready')) process.exitCode = 1;
  } else if (action === 'start') {
    const child = startBackend();
    child.on('error', error => { console.error(error.message); process.exitCode = 1; });
    child.on('exit', code => { process.exitCode = code || 0; });
    for (const signal of ['SIGTERM', 'SIGINT']) process.once(signal, () => { void stopChild(child); });
  } else throw Error('Use backend:setup, backend:start or backend:check.');
}

if (process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === import.meta.url) {
  main().catch(error => { console.error(error.message); process.exitCode = 1; });
}
