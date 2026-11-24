// Build June Mail and June Browser. Compile and self-test only: Mail and Chrome are not opened and
// no permission is requested here; macOS asks when you first allow them in Systems → Email & jobs.
import {spawn} from 'node:child_process';
import {existsSync} from 'node:fs';
import {mkdir,chmod,rename,copyFile} from 'node:fs/promises';
import {homedir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {signingIdentity} from './signing.mjs';
const root=fileURLToPath(new URL('../',import.meta.url));
if(existsSync(join(root,'.env.local')))process.loadEnvFile(join(root,'.env.local'));
if(process.platform!=='darwin')throw Error('Mail and browser helpers require macOS.');
const directory=join(process.env.JUNE_DATA_HOME || join(homedir(),'Library/Application Support/June/data'),'tools');
await mkdir(directory,{recursive:true,mode:0o700});await chmod(directory,0o700);
async function run(command,args){await new Promise((resolve,reject)=>{
 const child=spawn(command,args,{cwd:root,stdio:'inherit'});
 child.on('error',reject);child.on('exit',code=>code===0?resolve():reject(Error(`${args[0] ?? command} failed (${code}).`)));
});}
// Rebuilding a helper resets its macOS permissions (Full Disk Access, Automation, Screen Recording), so `node scripts/mail.mjs JuneBrowser` rebuilds only that one.
const only=process.argv.slice(2);
for(const [name,id] of [['JuneMail','local.june.mail'],['JuneBrowser','local.june.browser'],['JuneScreen','local.june.screen']].filter(([name])=>!only.length||only.includes(name))){
 const bundle=join(directory,name+'.app'),contents=join(bundle,'Contents'),mac=join(contents,'MacOS');
 await mkdir(mac,{recursive:true,mode:0o700});
 const binary=join(mac,name);
 await run('/usr/bin/xcrun',['swiftc','-O',join(root,`native/${name}.swift`),'-framework','AppKit',...(name==='JuneMail'?['-lsqlite3']:[]),...(name==='JuneScreen'?['-framework','ScreenCaptureKit','-framework','Vision']:[]),
  '-Xlinker','-sectcreate','-Xlinker','__TEXT','-Xlinker','__info_plist','-Xlinker',join(root,`native/${name}-Info.plist`),'-o',binary+'.next']);
 await chmod(binary+'.next',0o700);await run(binary+'.next',['--self-test']);await rename(binary+'.next',binary);
 await copyFile(join(root,`native/${name}-Info.plist`),join(contents,'Info.plist'));
 await run('/usr/bin/codesign',['--force','--sign',signingIdentity(),'--identifier',id,bundle]);
 await run(binary,['--self-test']);
}
console.log('\nJune helpers are ready. Mail and Chrome were not opened and the screen was not read.');
