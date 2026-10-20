// Supervise only the processes created here. Ollama stays in its own terminal.
import { spawn } from 'node:child_process';
import { join } from 'node:path';
import { root, health, startBackend, stopChild } from './backend.mjs';

let backend, web, stopping = false;
async function shutdown(code = 0) {
  if (stopping) return;
  stopping = true;
  await Promise.all([stopChild(web), stopChild(backend)]);
  process.exitCode = code;
}
for (const signal of ['SIGINT', 'SIGTERM']) process.once(signal, () => { void shutdown(); });

try {
  const existing = await health();
  if (stopping) throw Error('Startup cancelled.');
  if (existing.available && !existing.valid) throw Error('The Python port is occupied by an incompatible service. Stop that service or choose another JUNE_BACKEND_URL.');
  if (!existing.valid) {
    backend = startBackend();
    let launchError;
    backend.on('error', error => { launchError = error; });
    const deadline = Date.now() + 20000;
    while (!(await health()).valid) {
      if (stopping || launchError || backend.exitCode !== null || backend.signalCode !== null || Date.now() > deadline) {
        throw Error('Python backend could not start. Check its error above, or run npm run backend:setup.');
      }
      await new Promise(resolve => setTimeout(resolve, 200));
    }
  }
  if (stopping) throw Error('Startup cancelled.');
  console.log('June v0.5 · Python backend ready · http://127.0.0.1:3001');
  web = spawn(process.execPath, [join(root, 'node_modules/next/dist/bin/next'), process.argv[2] === 'dev' ? 'dev' : 'start',
    '--hostname', '127.0.0.1', '--port', '3001'], { cwd: root, stdio: 'inherit', env: process.env });
  web.on('error', error => { console.error(error.message); void shutdown(1); });
  web.on('exit', code => { if (!stopping) void shutdown(code || 0); });
  backend?.on('exit', () => { if (!stopping) { console.error('June’s Python backend stopped. Restart June.'); void shutdown(1); } });
} catch (error) {
  if (!stopping) console.error(error.message);
  await shutdown(stopping ? 0 : 1);
}
