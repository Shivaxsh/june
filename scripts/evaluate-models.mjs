// A small reproducible local comparison. Expectations are test data only;
// they never substitute answers in June's production chat.
import { readFile, writeFile } from 'node:fs/promises';
import { performance } from 'node:perf_hooks';
const source = await readFile(new URL('../lib/server/model.ts',import.meta.url),'utf8');
const prompt = process.env.JUNE_EVAL_PROMPT_FILE ? (await readFile(process.env.JUNE_EVAL_PROMPT_FILE,'utf8')).trim() : source.match(/export const JUNE_PROMPT = `([^`]+)`/)[1];
const models = process.argv.slice(2); if(!models.length) models.push('qwen3:0.6b','qwen2.5:1.5b');
const user = content => ({role:'user',content}); const assistant = content => ({role:'assistant',content});
const country = /\b(?:India|Iran|Iraq|Ireland|Iceland|Italy|Israel|Indonesia)\b/i;
const cases = [
 ['country-I',[user('Tell me a country whose name starts with the letter I.')],country],
 ['capital',[user('What is the capital of Japan?')],/\bTokyo\b/i],
 ['arithmetic',[user('What is 17 plus 28?')],/\b45\b/],
 ['follow-up',[user('Name a country in Europe.'),assistant('France.'),user('What is its capital?')],/\bParis\b/i],
 ['after-refusal',[user('Name a country starting with I.'),assistant('I do not know. Please provide more information.'),user('What is the capital of Japan?')],/\bTokyo\b/i],
 ['other-letter',[user('Name a country whose name starts with Z.')],/\b(?:Zambia|Zimbabwe)\b/i],
 ['unknown-personal',[user("What is my mother's first name?")],/do(?:n't| not) know|not (?:know|have)|haven.t|don.t have|not provided|no (?:information|access)|cannot (?:know|determine)|can't (?:know|determine)|don't possess/i],
 ['unknown-food',[user('What is my favourite food?')],/do(?:n't| not) know|not (?:know|have)|haven.t|don.t have|not provided|no (?:information|access)|cannot (?:know|determine)|can't (?:know|determine)/i],
 ['known-personal',[user('My favourite colour is teal.'),assistant('Understood.'),user('What is my favourite colour?')],/\bteal\b/i],
 ['country-I-repeat',[user('Tell me a country whose name starts with the letter I.')],country],
];
const results=[];
for(const model of models) {
 // Download is handled separately; wait without modifying any configuration.
 const deadline=Date.now()+360000;
 while(!(await (await fetch('http://127.0.0.1:11434/api/tags')).json()).models.some(item=>item.name===model)) {
  if(Date.now()>deadline) throw Error('Candidate download was not ready.');
  await new Promise(resolve=>setTimeout(resolve,10000));
 }
 for(const [name,messages,expected] of cases) {
  const start=performance.now(); let first=null,text='',done=false;
  const response=await fetch('http://127.0.0.1:11434/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},signal:AbortSignal.timeout(90000),body:JSON.stringify({model,messages:[{role:'system',content:prompt},...messages],stream:true,think:false,keep_alive:'5m',options:{num_ctx:4096,num_predict:160,temperature:.1}})});
  if(!response.ok) throw Error('Model request failed: '+response.status);
  const reader=response.body.getReader(),decoder=new TextDecoder();let pending='';
  while(true) {
   const part=await reader.read();pending+=decoder.decode(part.value,{stream:!part.done});
   const lines=pending.split('\n');pending=lines.pop();
   for(const line of lines.filter(Boolean)) {const event=JSON.parse(line);if(event.error)throw Error(event.error);if(event.message?.content){first??=performance.now()-start;text+=event.message.content;}if(event.done)done=true;}
   if(part.done)break;
  }
  const result={model,case:name,answer:text,pass:done&&expected.test(text)&&(!name.startsWith('unknown-')||!/fictional character|(?:don't|do not) have personal preferences|(?:don't|do not) have a favou?rite food/i.test(text)),firstSeconds:+((first||0)/1000).toFixed(2),seconds:+((performance.now()-start)/1000).toFixed(2)};
  results.push(result);console.log(JSON.stringify(result));
 }
 const ps=await (await fetch('http://127.0.0.1:11434/api/ps')).json();console.log(JSON.stringify({model,loaded:ps.models.map(item=>({name:item.name,bytes:item.size,gpuBytes:item.size_vram}))}));
}
await writeFile(new URL('../.june-work/model-comparison.json',import.meta.url),JSON.stringify(results,null,2));
if(results.some(item=>!item.pass&&item.model===models.at(-1)))process.exitCode=1;
