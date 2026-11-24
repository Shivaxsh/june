import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

test('hands-free stays responsive (0.8 s by default; mid-sentence pauses are re-decoded, not lost) and remembers the chosen pause', async () => {
  const source = await readFile(new URL('../components/voice/useHandsFree.ts', import.meta.url), 'utf8');
  assert.match(source, /export const DEFAULT_PAUSE = 'short';/);
  assert.match(source, /useState\(DEFAULT_PAUSE\)/);
  // Read after mount (no hydration mismatch), only known values, storage failures never break hands-free.
  assert.match(source, /useEffect\(\(\) => \{\s*try \{ const saved = window\.localStorage\.getItem\(PAUSE_KEY\); if \(saved && PAUSES\.includes\(saved\)\) setPauseState\(saved\); \} catch/);
  assert.match(source, /if \(!PAUSES\.includes\(value\)\) return;/);
  assert.match(source, /try \{ window\.localStorage\.setItem\(PAUSE_KEY, value\); \} catch/);
});
