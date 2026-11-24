// Re-sign June's installed helper apps with the private signing certificate, without rebuilding them.
// macOS asks once more for each helper's permissions after this; later rebuilds then keep them.
import {execFileSync} from 'node:child_process';
import {existsSync} from 'node:fs';
import {homedir} from 'node:os';
import {join} from 'node:path';
import {signingIdentity} from './signing.mjs';
const identity = signingIdentity();
if (identity === '-') throw Error('Create the "June Local Code Signing" certificate first.');
const base = join(homedir(), 'Library/Application Support/June');
const tools = join(process.env.JUNE_DATA_HOME || join(base, 'data'), 'tools');
const helpers = [[join(base, 'audio/JuneAudio.app'), 'local.june.audio'], ...[['JuneMail', 'mail'], ['JuneBrowser', 'browser'], ['JuneScreen', 'screen'],
  ['JuneMusic', 'music'], ['JuneCalendar', 'calendar'], ['JuneQuick', 'quick']].map(([name, id]) => [join(tools, name + '.app'), 'local.june.' + id])];
for (const [bundle, id] of helpers) {
  if (!existsSync(bundle)) { console.log(`skip ${id}: not installed`); continue; }
  execFileSync('/usr/bin/codesign', ['--force', '--sign', identity, '--identifier', id, bundle], {stdio: 'inherit'});
  execFileSync('/usr/bin/codesign', ['--verify', '--strict', bundle]);
  console.log(`signed ${id}`);
}
