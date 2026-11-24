import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';
async function load(url) {
  const source = await readFile(url, 'utf8');
  let { outputText } = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } });
  for (const match of [...outputText.matchAll(/from ["'](\.[^"']+)["']/g)]) outputText = outputText.replace(match[0], `from ${JSON.stringify(await load(new URL(match[1] + '.ts', url)))}`);
  return 'data:text/javascript;base64,' + Buffer.from(outputText).toString('base64');
}
const C = await import(await load(new URL('../lib/continuation.ts', import.meta.url)));
const { prepareContext } = await import(await load(new URL('../lib/context.ts', import.meta.url)));
const chat = await readFile(new URL('../components/Chat.tsx', import.meta.url), 'utf8');
const status = await readFile(new URL('../components/voice/ReplyStatus.tsx', import.meta.url), 'utf8');
const turn = (id, assistant, extra = {}) => ({ id, user: `question ${id}`, assistant, status: 'complete', memories: '[]', ...extra });

test('typed and spoken continue intents are recognised; ordinary sentences are not', () => {
  for (const text of ['continue', 'Continue.', 'please continue', 'Hey June, continue', 'keep going', 'go on', 'carry on!', 'finish the code', 'okay continue please', 'Continue from where you stopped'])
    assert.equal(C.isContinueIntent(text), true, text);
  for (const text of ['continue the story about dragons in space', 'how do I continue a loop in python?', 'should I go on holiday', 'continued fractions', '', 'Continue reading my resume and summarise it'])
    assert.equal(C.isContinueIntent(text), false, text);
});

test('an unclosed fence is flagged as possibly unfinished; balance is not treated as validity', () => {
  assert.equal(C.unclosedFence('Here:\n```python\nprint(1)\n'), true);
  assert.equal(C.unclosedFence('```js\nx()\n```\nand\n~~~\nraw'), true);
  assert.equal(C.unclosedFence('```py\nprint(\n```'), false, 'balanced fences only mean "not detectably cut", never "valid"');
  assert.equal(C.unclosedFence('inline ``` mention'), false);
  // Matches the server: an info string or a shorter run does not close the block.
  assert.equal(C.unclosedFence('```\ncode\n```python\nmore\n```'), false);
  assert.equal(C.unclosedFence('````\ncode\n```\n'), true);
  assert.equal(C.unclosedFence('````\ncode\n````'), false);
  assert.doesNotMatch(status + chat, /code (?:is )?(?:complete|valid|runnable)/i);
});

test('saved continuation segments join into one bubble; the latest segment drives id and warning', () => {
  const joined = C.joinTurns([
    turn('a', 'First answer.'),
    turn('b', 'Code:\n```py\nfor i in range(3):\n', { limited: 1 }),
    turn('c', '    print(i)\n', { limited: true, continuedFrom: 'b', user: 'Continue.' }),
    turn('d', '```\nDone.', { limited: false, incomplete: false, continuedFrom: 'c', user: 'Continue.' }),
    turn('e', 'Next.', { continuedFrom: null }),
  ]);
  assert.equal(joined.length, 3);
  assert.deepEqual(joined[1], { id: 'b', latestId: 'd', user: 'question b', parts: ['Code:\n```py\nfor i in range(3):\n', '    print(i)\n', '```\nDone.'], status: 'complete', limited: false, incomplete: false, memories: '[]', citations: undefined });
  assert.equal(joined[0].limited, false, 'legacy rows default to false');
});

test('a continuation joins its own bubble even behind a completeness notice; order is preserved', () => {
  const notice = 'The previous reply was cut off or has an unfinished code block.';
  const joined = C.joinTurns([turn('a', 'one', { limited: true }), turn('n', notice), turn('c', ' two', { continuedFrom: 'a', user: 'Continue.' })]);
  assert.deepEqual(joined.map(j => [j.id, j.latestId, j.parts]), [['a', 'c', ['one', ' two']], ['n', 'n', [notice]]]);
  // A later continuation follows the chain's new latest segment, still behind the notice.
  const longer = C.joinTurns([turn('a', 'one', { limited: true }), turn('n', notice), turn('c', ' two', { continuedFrom: 'a', limited: true }), turn('d', ' three', { continuedFrom: 'c' })]);
  assert.deepEqual(longer[0].parts, ['one', ' two', ' three']);
  assert.equal(longer[0].latestId, 'd');
  assert.equal(longer[1].id, 'n');
});

test('an unknown or already-continued source is shown on its own; a stopped continuation is skipped', () => {
  assert.equal(C.joinTurns([turn('a', 'one', { limited: true }), turn('c', 'x', { continuedFrom: 'missing' })]).length, 2);
  const fork = C.joinTurns([turn('a', 'one', { limited: true }), turn('b', ' two', { continuedFrom: 'a' }), turn('c', ' again', { continuedFrom: 'a' })]);
  assert.equal(fork.length, 2, 'a second continuation of an already-continued segment is not merged');
  const stopped = C.joinTurns([turn('a', 'one', { limited: true }), turn('c', 'partial', { continuedFrom: 'a', status: 'stopped', user: 'Continue.' })]);
  assert.equal(stopped.length, 1, 'a stopped continuation is not part of the saved chain');
  assert.equal(stopped[0].latestId, 'a');
  assert.deepEqual(stopped[0].parts, ['one']);
});

test('a partial reply keeps its tail in context; the request that started it stays with it', () => {
  const longCode = 'HEAD ' + 'x'.repeat(4000) + ' TAIL';
  const history = [{ role: 'user', content: 'Write the program' }, { role: 'assistant', content: longCode, partial: true }];
  const { messages } = prepareContext(history, { role: 'user', content: 'continue' });
  assert.equal(messages[0].content, 'Write the program');
  assert.match(messages[1].content, /TAIL$/);
  assert.doesNotMatch(messages[1].content, /HEAD/);
  assert.match(messages[1].content, /^\[Earlier part omitted\]/);
  assert.ok(messages[1].content.length <= 2000);
  assert.ok(messages.every(m => !('partial' in m)), 'the server contract has role and content only');
  const ordinary = prepareContext([{ role: 'user', content: 'q' }, { role: 'assistant', content: 'HEAD ' + 'y'.repeat(4000) }], { role: 'user', content: 'next' });
  assert.match(ordinary.messages[1].content, /^HEAD/, 'complete replies keep their opening');
});

test('fixed spoken notices: limit once, code-only, never the code text itself', () => {
  assert.equal(C.spokenNotice({ limited: true, incomplete: false, spokeSomething: true, hasCode: false }), C.LIMIT_NOTICE);
  assert.equal(C.spokenNotice({ limited: false, incomplete: true, spokeSomething: true, hasCode: true }), C.INCOMPLETE_NOTICE);
  assert.equal(C.spokenNotice({ limited: false, incomplete: false, spokeSomething: false, hasCode: true }), C.CODE_NOTICE);
  assert.equal(C.spokenNotice({ limited: true, incomplete: true, spokeSomething: false, hasCode: true }), `${C.CODE_NOTICE} ${C.LIMIT_NOTICE}`);
  assert.equal(C.spokenNotice({ limited: false, incomplete: false, spokeSomething: true, hasCode: true }), '');
  assert.match(C.LIMIT_NOTICE, /length limit.*continue/i);
});

test('Chat sends the structured contract only for a saved partial chain', () => {
  assert.match(chat, /continueTurn: continuing\.latestId/);
  assert.match(chat, /messages: continuing \? \[\{ role: "user", content: CONTINUE_PROMPT \}\] : context/);
  assert.match(chat, /!library\.temporary && conversationIdRef\.current && isContinueIntent\(content\)/);
  // The server names the resumable segment; it may sit behind a later completeness notice.
  assert.match(chat, /"resumable" in event \? \(typeof event\.resumable === "string" \? event\.resumable : null\)/);
  assert.match(chat, /m\.latestId === resumableRef\.current/);
  assert.match(chat, /setResumable\(chat\.resumable !== undefined \? chat\.resumable :/);
  assert.match(chat, /interrupt\('library-changed'\);[^\n]*\n[^\n]*\n    setResumable\(null\);/, 'a saved-store revision change ends the resumable chain');
  assert.match(chat, /incomplete = event\.incomplete === true \|\| unclosedFence\(/);
  assert.match(chat, /joinTurns\(chat\.turns\)/, 'reopened chats join their chain');
  assert.match(chat, /spokenNotice\(\{/);
  // A failed or stopped continuation returns the bubble to the last saved segment.
  assert.match(chat, /if \(continuing\) \{ restoreChain\(\);/);
});

test('the warning offers Continue only where a structured continuation is possible', () => {
  assert.match(status, /onContinue/);
  assert.match(status, /Cut off at the length limit/);
  assert.match(status, /may be unfinished/);
  assert.match(status, /temporary/i);
  assert.match(chat, /message\.latestId === resumable \? \(\) => void send/, 'Continue sits on the segment the server would resume');
  assert.match(chat, /&& !event\.citations\?\.length \? savedTurnId : null/, 'without the server field, cited replies are not offered a general continuation');
});

test('the chain is byte-exact: the seam is an empty zero-width element, never text inside code', async () => {
  const css = await readFile(new URL('../app/globals.css', import.meta.url), 'utf8');
  assert.match(chat, /<span className="continued-mark" aria-hidden="true" title="Continued" \/>/);
  assert.match(css, /\.continued-mark \{[^}]*width: 0;/);
  assert.match(chat, /content: base \+ reply, parts: \[\.\.\.continuing\.parts, reply\]/);
  const parts = ['```py\nfor i in range(3):\n    pri', 'nt(i)\n```'];
  assert.equal(C.joinTurns(parts.map((assistant, i) => ({ id: `s${i}`, user: 'q', assistant, status: 'complete', memories: '[]', continuedFrom: i ? `s${i - 1}` : null })))[0].parts.join(''), parts.join(''));
});

const { SentenceBuffer } = await import(await load(new URL('../lib/voice/sentences.ts', import.meta.url)));
const speak = (base, chunks) => { const b = new SentenceBuffer(); const out = []; const lead = C.speechLead(base); out.push(...b.push(lead)); for (const c of chunks) out.push(...b.push(c)); out.push(...b.finish()); return out; };

test('a continuation inside an open code fence is never read aloud; prose after the closing fence is', () => {
  const base = 'Here is the code:\n```python\ndef add(a, b):\n';
  assert.deepEqual(speak(base, ['    return a', ' + b\n', '```\nThis adds two numbers.']), ['This adds two numbers.']);
  assert.deepEqual(speak(base, ['    return a + b\n', '    # still code\n']), [], 'still inside the fence: nothing spoken');
  assert.deepEqual(speak('Intro.\n~~~\nraw\n', ['more raw\n~~~\nDone.']), ['Done.'], 'tilde fences too');
  assert.deepEqual(speak('````\ncode\n```\n', ['still code\n````\nShort note.']), ['Short note.'], 'a longer opening run is matched');
});

test('a prose continuation speaks only the new words, never the earlier prose again', () => {
  assert.equal(C.speechLead('First part. Then'), '');
  assert.deepEqual(speak('First part. Then', [' more prose follows.']), ['more prose follows.']);
  assert.deepEqual(speak('```js\nx()\n```\nAnd', [' that is all.']), ['that is all.'], 'a closed earlier block opens nothing');
});

test('Chat feeds the base-aware lead into speech only, never into displayed text', () => {
  assert.match(chat, /const lead = continuing \? speechLead\(base\) : "";/);
  assert.match(chat, /const target = spokenChatReply\(lead \+ reply\);/);
  assert.match(chat, /hasCode: !!lead \|\| /, 'code continued inside an open fence still gets the code notice');
  assert.match(chat, /content: base \+ reply, parts: \[\.\.\.continuing\.parts, reply\]/);
});
