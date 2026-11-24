// Build June's fixed Mac action helper. This script does not launch an app.
import {spawn} from 'node:child_process';
import {existsSync} from 'node:fs';
import {mkdir,chmod,rename} from 'node:fs/promises';
import {homedir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url));
if(existsSync(join(root,'.env.local')))process.loadEnvFile(join(root,'.env.local'));
if(process.platform!=='darwin')throw Error('Mac actions require macOS.');
const directory=join(process.env.JUNE_DATA_HOME || join(homedir(),'Library/Application Support/June/data'),'actions');
await mkdir(directory,{recursive:true,mode:0o700});await chmod(directory,0o700);
const binary=join(directory,'JuneActions');
await new Promise((resolve,reject)=>{
 const child=spawn('/usr/bin/xcrun',['swiftc','-O',join(root,'native/JuneActions.swift'),'-framework','AppKit','-o',binary+'.next'],{cwd:root,stdio:'inherit'});
 child.on('error',reject);child.on('exit',code=>code===0?resolve():reject(Error(`Action helper compilation failed (${code}).`)));
});
await chmod(binary+'.next',0o700);await rename(binary+'.next',binary);
console.log('June Mac action helper ready. Apps open only after approval in June.');
