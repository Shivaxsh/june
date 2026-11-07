// Prepare the isolated local voice without modifying June's Python backend.
import {existsSync} from 'node:fs';
import {mkdir, writeFile, rename, unlink} from 'node:fs/promises';
import {join} from 'node:path';
import {homedir} from 'node:os';
import {spawn} from 'node:child_process';
import {Readable} from 'node:stream';
import {pipeline} from 'node:stream/promises';
import {createWriteStream} from 'node:fs';
if (existsSync('.env.local')) process.loadEnvFile('.env.local');
const home=process.env.JUNE_VOICE_HOME || join(homedir(),'Library/Application Support/June/voice-lab');
await mkdir(home,{recursive:true,mode:0o700});
const run=(binary,args)=>new Promise((resolve,reject)=>{
  const child=spawn(binary,args,{stdio:'inherit'});
  child.on('error',reject);child.on('exit',code=>code===0?resolve():reject(Error('Local voice setup failed. Check the message above.')));
});
const python=join(home,'.venv/bin/python');
if (!existsSync(python)) await run(join(process.cwd(),'backend/.venv/bin/python'),['-m','venv',join(home,'.venv')]);
await run(python,['-m','pip','install','kokoro-onnx==0.6.1','soundfile==0.14.0','onnxruntime==1.23.2','numpy==2.2.6']);
for (const name of ['kokoro-v1.0.onnx','voices-v1.0.bin']) {
  const path=join(home,name);
  if (existsSync(path)) continue;
  const response=await fetch(`https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/${name}`,{signal:AbortSignal.timeout(600000)});
  if (!response.ok || !response.body) throw Error('Could not download official Heart voice files. Retry setup.');
  try {await pipeline(Readable.fromWeb(response.body),createWriteStream(path+'.download'));await rename(path+'.download',path);}
  catch (error) {await unlink(path+'.download').catch(()=>{});throw error;}
}
await writeFile(join(home,'SOURCE.txt'),'Kokoro v1.0: https://huggingface.co/hexgrad/Kokoro-82M (Apache-2.0). kokoro-onnx: https://github.com/thewh1teagle/kokoro-onnx (MIT). Voice: af_heart.\n');
console.log('Heart voice files ready. Restart June, then Refresh audio. No speech API key is required.');
