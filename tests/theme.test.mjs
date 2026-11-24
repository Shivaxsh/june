import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
const css = await readFile(new URL('../app/globals.css', import.meta.url), 'utf8');
const tokens = Object.fromEntries([...css.matchAll(/(--[\w-]+):\s*(#[\da-f]{6})\s*;/gi)].map(([,name,value]) => [name,value.toLowerCase()]));
const luminance = hex => {
  const rgb = [1,3,5].map(start => parseInt(hex.slice(start,start+2),16)/255).map(v => v <= .04045 ? v/12.92 : ((v+.055)/1.055)**2.4);
  return rgb[0]*.2126 + rgb[1]*.7152 + rgb[2]*.0722;
};
const contrast = (a,b) => { const x=luminance(a), y=luminance(b); return (Math.max(x,y)+.05)/(Math.min(x,y)+.05); };

test('normal text, captions and active-state text retain AA contrast on charcoal surfaces', () => {
  for (const background of ['--background','--panel','--raised']) {
    assert.ok(tokens[background], `Missing surface ${background}`);
    for (const foreground of ['--text','--muted','--accent','--listening','--thinking','--speaking']) {
      assert.ok(contrast(tokens[foreground],tokens[background]) >= 4.5, `${foreground} on ${background}`);
    }
  }
  assert.ok(contrast(tokens['--accent'],tokens['--background']) >= 3);
});

test('responsive HUD: drawer and tablet layout regressions stay fixed', async () => {
  // The composer's square send button must not shrink other send buttons (Enable hands-free in the drawer).
  assert.match(css, /\.hud \.composer \.send-button \{ width: 44px;/);
  assert.doesNotMatch(css, /\.hud \.send-button \{ width: 44px;/);
  // The open drawer locks the page behind it and does not chain scrolling into it.
  assert.match(css, /html:has\(\.hud-drawer\.is-open\) \{ overflow: hidden; \}/);
  assert.match(css, /\.hud-drawer-body \{[^}]*overscroll-behavior: contain/);
  // 761–1100px: the constellation drops below the conversation instead of pushing the composer down.
  const tablet = css.slice(css.indexOf('@media (min-width: 761px) and (max-width: 1100px)'));
  assert.match(tablet, /\.hud-dialogue \{ grid-column: 1 \/ -1; grid-row: 2;/);
  assert.match(tablet, /\.hud-constellation \{ grid-column: 1 \/ -1; grid-row: 3;/);
  // Phones: telemetry and constellation span the column; suggestion buttons are 44px touch targets.
  assert.match(css, /\.hud-grid > \.hud-telemetry \{ order: 3;[^}]*align-self: stretch/);
  assert.match(css, /@media \(pointer: coarse\) \{[^@]*\.hud \.suggestions button \{ align-items/);
  // The constellation tooltip never exceeds half the stage, so it cannot widen the page.
  assert.match(css, /\.hud-graph-tip \{[^}]*max-width: calc\(50% - 16px\)/);
  const constellation = await readFile(new URL('../components/hud/ConstellationClassic.tsx', import.meta.url), 'utf8');
  assert.match(constellation, /hover\.x > hover\.w \/ 2 \? \{ right:/);
});

test('Specimen is preview-only: every rule is scoped, cyan and white (no gold), readable, and classic is untouched', async () => {
  const start = css.indexOf('Specimen (preview design');
  const end = css.indexOf('@media (max-width: 1100px) {\n  .hud { --hud-orb-h: clamp(460px');
  assert.ok(start > 0 && end > start, 'the specimen block sits before the classic responsive rules');
  const block = css.slice(css.indexOf('*/', start) + 2, end).replace(/\/\*[\s\S]*?\*\//g, '').replace(/@media[^{]*\{/g, '}');  // check rules inside media queries too
  for (const rule of block.replace(/@keyframes[^{]+\{(?:[^{}]*\{[^}]*\})*[^}]*\}/g, '').matchAll(/(^|\})\s*([^@{}][^{}]*?)\s*\{/g)) {
    for (const selector of rule[2].split(',').map(x => x.trim()).filter(Boolean)) {
      if (/^(from|to|\d+%)/.test(selector)) continue;
      assert.match(selector, /design-specimen|^\.sp-|^\.june-/, `unscoped specimen selector: ${selector}`);
    }
  }
  assert.doesNotMatch(block, /255,\s*181,\s*71|#ffb547|#ff6a2b|#ffd08a/i, 'no gold');
  assert.match(block, /--sp-cyan: #5fc8d2;/);
  assert.match(css, /--panel: #07090A; --raised: #0C1012; --inset: #050607; --line-strong: #4B4E56; --text: #eef2fa; --muted: #acb8cf;/);
  const tokens = Object.fromEntries([...block.slice(0, block.indexOf('}')).matchAll(/(--[a-z-]+):\s*(#[0-9a-f]{6})/gi)].map(m => [m[1], m[2]]));
  for (const fg of ['--text', '--muted', '--accent', '--sp-cyan']) assert.ok(contrast(tokens[fg], tokens['--background']) >= 4.5, `${fg} on black`);
  assert.ok(contrast(tokens['--sp-ink'], tokens['--sp-cyan']) >= 4.5, 'tag text on cyan');
  assert.match(css, /@media \(prefers-reduced-motion: reduce\) \{\n  \.design-specimen \.june-history, \.june-subtitle \.june-word \{ transition: none; \}/);
});

test('Observatory (final design) is scoped, keeps classic responsive rules in charge, and respects reduced motion', async () => {
  const start = css.indexOf('Observatory (June’s final design)') >= 0 ? css.indexOf('Observatory (June’s final design)') : css.indexOf("Observatory (June's final design)");
  const end = css.indexOf('Specimen (preview design');
  assert.ok(start > 0 && end > start, 'the observatory block sits before the specimen block and the responsive rules');
  const block = css.slice(css.indexOf('*/', start) + 2, end).replace(/\/\*[\s\S]*?\*\//g, '').replace(/@media[^{]*\{/g, '}');
  for (const rule of block.replace(/@keyframes[^{]+\{(?:[^{}]*\{[^}]*\})*[^}]*\}/g, '').matchAll(/(^|\})\s*([^@{}][^{}]*?)\s*\{/g)) {
    for (const selector of rule[2].split(',').map(x => x.trim()).filter(Boolean)) {
      if (/^(from|to|\d+%)/.test(selector)) continue;
      assert.match(selector, /design-observatory|^\.hud-sky/, `unscoped observatory selector: ${selector}`);
    }
  }
  // The wide 3-column grid only applies on wide screens, so the tablet and phone layouts still win.
  assert.match(css, /@media \(min-width: 1101px\) \{ \.design-observatory \.hud-grid \{ grid-template-columns:/);
  assert.match(css, /\.hud-orb-layer, \.hud-sky \{ right: 396px; \}/);
  assert.match(css, /\.hud-orb-layer, \.hud-sky \{ right: 0; \}/);
  assert.match(css, /@media \(prefers-reduced-motion: reduce\) \{ \.design-observatory \.citation-sources button\.is-arrived \{ animation: none;/);
  const tokens = Object.fromEntries([...block.slice(0, block.indexOf('}')).matchAll(/(--[a-z-]+):\s*(#[0-9a-f]{6})/gi)].map(m => [m[1], m[2]]));
  for (const fg of ['--text', '--muted']) assert.ok(contrast(tokens[fg], '#000000') >= 4.5, `${fg} readable`);
});
