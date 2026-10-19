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
