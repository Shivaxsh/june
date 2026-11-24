// Compile/self-test only. No calendar access or permission request.
import {spawn} from 'node:child_process';
import {existsSync} from 'node:fs';
import {mkdir,chmod,rename,copyFile} from 'node:fs/promises';
import {homedir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {signingIdentity} from './signing.mjs';
const root=fileURLToPath(new URL('../',import.meta.url));
if(existsSync(join(root,'.env.local')))process.loadEnvFile(join(root,'.env.local'));
if(process.platform!=='darwin')throw Error('Calendar reading requires macOS.');
const directory=join(process.env.JUNE_DATA_HOME || join(homedir(),'Library/Application Support/June/data'),'tools');
await mkdir(directory,{recursive:true,mode:0o700});await chmod(directory,0o700);
// A signed app bundle gives macOS a stable "June Calendar" identity for Calendar consent.
const bundle=join(directory,'JuneCalendar.app'),contents=join(bundle,'Contents'),mac=join(contents,'MacOS');
await mkdir(mac,{recursive:true,mode:0o700});
const binary=join(mac,'JuneCalendar');
async function run(command,args){await new Promise((resolve,reject)=>{
 const child=spawn(command,args,{cwd:root,stdio:'inherit'});
 child.on('error',reject);child.on('exit',code=>code===0?resolve():reject(Error(`Calendar helper check failed (${code}).`)));
});}
await run('/usr/bin/xcrun',['swiftc','-O',join(root,'native/JuneCalendar.swift'),'-framework','EventKit',
 '-Xlinker','-sectcreate','-Xlinker','__TEXT','-Xlinker','__info_plist','-Xlinker',join(root,'native/JuneCalendar-Info.plist'),'-o',binary+'.next']);
await chmod(binary+'.next',0o700);await run(binary+'.next',['--self-test']);await rename(binary+'.next',binary);
await copyFile(join(root,'native/JuneCalendar-Info.plist'),join(contents,'Info.plist'));
await run('/usr/bin/codesign',['--force','--sign',signingIdentity(),'--identifier','local.june.calendar',bundle]);
await run(binary,['--self-test']);
console.log('\nJune Calendar helper ready. Calendar was not read; permission is requested only from Daily setup.');
