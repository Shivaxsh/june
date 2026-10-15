import { spawn } from 'node:child_process';
import { join } from 'node:path';
import { python, root } from './backend.mjs';
async function run(args) {
  await new Promise((resolve, reject) => {
    const child = spawn(python, args, { cwd: root, stdio: 'inherit', env: { ...process.env, LOGURU_LEVEL: 'WARNING' } });
    child.on('error', reject);
    child.on('exit', code => code === 0 ? resolve() : reject(Error('Hands-free setup did not finish. See the message above.')));
  });
}
try {
  await run(['-m', 'pip', 'install', '-r', 'backend/requirements.lock']);
  await run([join(root, 'scripts/realtime-setup.py')]);
} catch (error) { console.error(error.message); process.exitCode = 1; }
