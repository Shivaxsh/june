// Compile/self-test the credential helper. Never reads or writes any credentials.
import {spawn} from 'node:child_process';
import {existsSync} from 'node:fs';
import {mkdir,chmod,rename} from 'node:fs/promises';
import {homedir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url));
if(existsSync(join(root,'.env.local')))process.loadEnvFile(join(root,'.env.local'));
if(process.platform!=='darwin')throw Error('Keychain support requires macOS.');
const directory=join(process.env.JUNE_DATA_HOME || join(homedir(),'Library/Application Support/June/data'),'tools');
await mkdir(directory,{recursive:true,mode:0o700});await chmod(directory,0o700);
const binary=join(directory,'JuneSecrets');
async function run(command,args){
 await new Promise((resolve,reject)=>{
  const child=spawn(command,args,{cwd:root,stdio:'inherit'});
  child.on('error',reject);child.on('exit',code=>code===0?resolve():reject(Error(`Credential helper check failed (${code}).`)));
 });
}
await run('/usr/bin/xcrun',['swiftc','-O',join(root,'native/JuneSecrets.swift'),'-framework','Security','-o',binary+'.next']);
await chmod(binary+'.next',0o700);
await run(binary+'.next',['--self-test']);
await rename(binary+'.next',binary);
console.log('\nJune Keychain helper ready. No credentials were accessed.');
