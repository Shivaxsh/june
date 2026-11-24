import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';

const dataUrl = source => 'data:text/javascript;base64,' + Buffer.from(source).toString('base64');
const read = path => readFile(new URL(path, import.meta.url), 'utf8');
const compile = source => ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText;
const libUrl = dataUrl(compile(await read('../lib/integrations.ts')));
const lib = await import(libUrl);
const commands = await import(dataUrl(compile(await read('../lib/commands.ts')).replaceAll('"./integrations"', JSON.stringify(libUrl))));

const id = n => String(n).padStart(32, 'a');
const saved = (o = {}) => ({ id: id(1), projectId: id(2), project: 'June', name: 'dev server', command: 'npm run dev', safe: false, kind: 'server', running: false, ...o });
const state = (o = {}) => ({ version: 1, serverNow: 9, githubAllowed: false, projects: [{ id: id(2), name: 'June' }], commands: [saved()], ...o });
function http(replies) {
  const calls = [];
  const fn = async (url, init = {}) => { calls.push({ url, method: init.method ?? 'GET', body: init.body ? JSON.parse(init.body) : undefined }); const next = replies.shift(); return { ok: (next.status ?? 200) < 400, status: next.status ?? 200, json: async () => next.body }; };
  return { fn, calls };
}

test('saved commands are read strictly and written with exactly the typed text', async () => {
  const a = http([{ body: state() }, { body: state() }, { body: state({ commands: [] }) }, { body: state({ githubAllowed: true }) }]);
  assert.equal((await commands.getCommands(a.fn)).commands[0].command, 'npm run dev');
  await commands.addCommand({ projectId: id(2), name: ' Lint ', command: ' npm run lint -- --fix ', safe: true, kind: 'run' }, a.fn);
  await commands.removeCommand(id(1), a.fn);
  assert.equal((await commands.setGithub(true, a.fn)).githubAllowed, true);
  assert.deepEqual(a.calls.slice(1).map(c => [c.url, c.body]), [
    ['/api/commands', { projectId: id(2), name: 'Lint', command: 'npm run lint -- --fix', safe: true, kind: 'run' }],
    [`/api/commands/${id(1)}/remove`, {}], ['/api/commands/github', { allowed: true }]]);
  for (const bad of [state({ githubAllowed: 'yes' }), state({ commands: [saved({ kind: 'daemon' })] }), state({ commands: [saved({ id: '../x' })] }), state({ commands: [saved({ command: '' })] }), state({ projects: 'x' })])
    await assert.rejects(commands.getCommands(http([{ body: bad }]).fn));
  await assert.rejects(commands.addCommand({ projectId: id(2), name: 'x', command: 'a\nb', safe: false, kind: 'run' }, http([]).fn), e => e.code === 'invalid-input');
  await assert.rejects(commands.removeCommand('../etc', http([]).fn), e => e.code === 'invalid-input');
});

test('project plans send only a saved project name, a one-line message, a fixed recipe or a command id', async () => {
  const plan = { id: 'plan-0001', revision: 1, fingerprint: 'fp-0000001', status: 'proposed', title: 'x', createdAt: 1, expiresAt: 2, rememberable: false,
    steps: [{ id: 'step-1', capability: 'project.push', label: 'Commit and push June', preview: 'p', status: 'pending' }] };
  const reply = () => ({ body: { version: 1, serverNow: 5, plan } });
  const a = http([reply(), reply(), reply(), reply()]);
  await lib.proposePlan('project-push', a.fn, () => 'req-00000050', { name: 'June', message: ' Fix the bug ' });
  await lib.proposePlan('project-recipe', a.fn, () => 'req-00000051', { name: 'June', recipe: 'test' });
  await lib.proposePlan('project-pull', a.fn, () => 'req-00000052', { name: 'June' });
  await lib.proposePlan('project-command', a.fn, () => 'req-00000053', { id: id(1) });
  await lib.proposePlan('site-publish', http([reply()]).fn, () => 'req-00000054', { id: id(1) });
  await lib.proposePlan('site-unpublish', http([reply()]).fn, () => 'req-00000055', { id: id(1) });
  await lib.proposePlan('site-rollback', http([reply()]).fn, () => 'req-00000056', { id: id(1) });
  assert.deepEqual(a.calls.map(c => c.body.input), [{ name: 'June', message: 'Fix the bug' }, { name: 'June', recipe: 'test' }, { name: 'June' }, { id: id(1) }]);
  for (const [intent, input] of [['project-push', { name: 'June', message: '' }], ['project-push', { name: 'June', message: 'a\nb' }], ['project-push', { name: '../x', message: 'm' }],
    ['project-recipe', { name: 'June', recipe: 'deploy' }], ['project-command', { id: 'rm -rf' }], ['site-publish', { id: '../x' }], ['site-publish', { id: id(1), url: 'x' }], ['site-unpublish', { id: '../x' }], ['site-rollback', { id: id(1), digest: 'x' }], ['project-pull', { name: 'June', force: true }], ['project-push', { name: 'June', message: 'm', force: true }]])
    await assert.rejects(lib.proposePlan(intent, http([]).fn, () => 'r', input), e => e.code === 'invalid-input', JSON.stringify([intent, input]));
});

test('the panel and bridge: consent first, push only with a message, and only known endpoints', async () => {
  const panel = await read('../components/integrations/CommandsPanel.tsx');
  assert.match(panel, /disabled=\{busy \|\| !state\?\.githubAllowed \|\| !message\.trim\(\)\}/, 'no push without consent and a message');
  assert.match(panel, /"Allow GitHub"/); assert.match(panel, /never force-pushes/); assert.match(panel, /she never writes or changes it/);
  assert.match(panel, /className="quick-result" role="status"/);
  const bridge = await read('../app/api/commands/[[...path]]/route.ts');
  assert.match(bridge, /route === "github"/); assert.match(bridge, /\[a-f0-9\]\{32\}\\\/remove/);
  assert.match(await read('../components/Chat.tsx'), /<CommandsPanel plans=\{integrations\.plans\} onPlan=\{integrations\.upsert\}/);
});
