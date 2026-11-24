import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';
const load = async path => {
  const { outputText } = ts.transpileModule(await readFile(new URL(path, import.meta.url), 'utf8'), { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext, jsx: ts.JsxEmit.ReactJSX } });
  return import('data:text/javascript;base64,' + Buffer.from(outputText.replace('process.env.NEXT_PUBLIC_JUNE_DESIGN', 'undefined')).toString('base64'));
};
const design = await load('../lib/hud/design.ts');
const chat = await readFile(new URL('../components/Chat.tsx', import.meta.url), 'utf8');

test('Observatory is the final default design; classic and specimen remain build-time options', () => {
  assert.equal(design.DESIGN, 'observatory');
  assert.equal(design.designFrom(undefined), 'observatory');
  assert.equal(design.designFrom('cinema'), 'observatory', 'the retired gold preview is gone');
  assert.equal(design.designFrom('classic'), 'classic');
  assert.equal(design.designFrom('specimen'), 'specimen');
});

test('Observatory: the sky sits behind the orb with the unframed legend; classic keeps its boxed constellation', () => {
  assert.match(chat, /\{observatory && <Sky graph=\{graph\}[\s\S]{0,600}hitArea=\{orbLayer\} onOpenChat=\{openSavedChat\} onCometArrive=\{cometArrived\} \/>\}/);
  assert.match(chat, /\{observatory && <Constellation graph=\{graph\} state=\{constellationState\}/);
  assert.match(chat, /\{DESIGN === "classic" && <ConstellationClassic /);
  assert.match(chat, /specimen \? " design-specimen" : observatory \? " design-observatory" : ""/);
});

test('subtitle words follow the voice: spoken, current, still to come', async () => {
  const src = await readFile(new URL('../components/hud/Subtitles.tsx', import.meta.url), 'utf8');
  const fn = src.slice(src.indexOf('export function subtitleWords'), src.indexOf('\n}\n', src.indexOf('export function subtitleWords')) + 2)
    .replace('export function subtitleWords(text: string, start: number, end: number): SubtitleWord[]', 'function subtitleWords(text, start, end)').replace('const words: SubtitleWord[] = [];', 'const words = [];');
  const subtitleWords = new Function(fn + '; return subtitleWords;')();
  const words = subtitleWords('The time is 20:29.', 9, 11);
  assert.deepEqual(words.map(w => w.text), ['The ', 'time ', 'is ', '20:29.']);
  assert.deepEqual(words.map(w => w.state), ['done', 'done', 'now', 'todo']);
  assert.deepEqual(subtitleWords('Hello there', 0, 0).map(w => w.state), ['now', 'todo']);
});

test('specimen-only pieces render only in the specimen design; classic keeps its constellation and telemetry', () => {
  const fragment = chat.slice(chat.indexOf('{specimen && <>'), chat.indexOf('</>}', chat.indexOf('{specimen && <>')));
  assert.match(fragment, /<Atlas graph=\{graph\}/); assert.match(fragment, /<SpecimenRail ref=\{rail\}/);
  assert.doesNotMatch(chat, /june-giant|Neural<\/span>/, 'the outlined NEURAL NETWORK backdrop is removed');
  for (const piece of ['className="june-history-toggle"', '<Subtitles caption=', '<span className="sp-tag june-state"'])
    assert.match(chat, new RegExp('specimen (?:&&|\\?) (?:<>)?[\\s\\S]{0,160}' + piece.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')), `${piece} is specimen-only`);
  assert.match(chat, /\{!specimen && <section className="hud-telemetry"/);
  assert.match(chat, /data-mood=\{specimen \? orb\.mood : undefined\}/);
  assert.doesNotMatch(chat, /cinema|eclipse|ECLIPSE/i, 'the gold preview is fully removed');
});

test('the history drawer is reachable, closes with Escape and returns focus, and opens itself for cards or failures', () => {
  assert.match(chat, /aria-expanded=\{historyOpen\} aria-controls="june-history"/);
  assert.match(chat, /<aside id="june-history" className=\{`june-history\$\{historyOpen \? " is-open" : ""\}`\} aria-label="Conversation history" inert=\{!historyOpen\}>/);
  assert.match(chat, /event\.key === "Escape" && !systemsOpen\) \{ setHistoryOpen\(false\); historyToggle\.current\?\.focus\(\); \}/);
  assert.match(chat, /lastReply_\.planId \|\| lastReply_\.transactionId \|\| lastReply_\.reminderId \|\| lastReply_\.timerId \|\| lastReply_\.actionId \|\| lastReply_\.citations\?\.length \|\| lastReply_\.state === "failed"/);
});
