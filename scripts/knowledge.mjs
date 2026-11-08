// Download only the small retrieval model; never change June's reply model.
import { existsSync } from 'node:fs';
if (existsSync('.env.local')) process.loadEnvFile('.env.local');
const origin = new URL(process.env.OLLAMA_BASE_URL || 'http://127.0.0.1:11434');
if (origin.protocol !== 'http:' || !['127.0.0.1','localhost','[::1]'].includes(origin.hostname)
  || origin.username || origin.password || origin.pathname !== '/' || origin.search || origin.hash) throw Error('Use a local Ollama origin.');
const model = 'all-minilm:22m';
const pull = await fetch(new URL('/api/pull',origin), {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({model,stream:false}),signal:AbortSignal.timeout(600000)});
const result = await pull.json();
if (!pull.ok || result.error) throw Error(result.error || 'Start Ollama, then retry knowledge setup.');
const probe = await fetch(new URL('/api/embed',origin),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({model,input:'June searches private notes.',truncate:false}),signal:AbortSignal.timeout(60000)});
const value = await probe.json();
if (!probe.ok || !Array.isArray(value.embeddings?.[0]) || !value.embeddings[0].every(Number.isFinite)) throw Error('The embedding model failed its readiness check.');
console.log(`Knowledge ready: ${model}, ${value.embeddings[0].length} dimensions. June’s reply model selection is unchanged.`);
