"""Local document extraction, owned indexing jobs and bounded hybrid retrieval."""
import asyncio
from bisect import bisect_left
from contextlib import suppress
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import uuid
import httpx
from .chat import MODEL_KEEP_ALIVE
from .knowledge_store import KnowledgeStore, MODEL, MAX_PASSAGES, error
from .errors import JuneError

MAX_UPLOAD = 10*1024*1024
MAX_OUTPUT = 12*1024*1024
EXTRACT_TIMEOUT = 60


def passages(pages):
    result=[]
    for page in pages:
        value=page['text']
        if len(value)>MAX_PASSAGES*500:raise error('The document exceeds the passage limit.',413)
        newlines=[m.start() for m in re.finditer('\n',value)]
        for start in range(0,len(value),500):
            end=min(start+600,len(value))
            piece=value[start:end]
            if piece.strip():
                result.append({'id':str(uuid.uuid4()),'text':piece,'page':page['page'],
                               'lineStart':bisect_left(newlines,start)+1,'lineEnd':bisect_left(newlines,end)+1})
                if len(result)>MAX_PASSAGES:
                    raise error('The document exceeds the 5000 passage limit.',413)
            if end==len(value):
                break
    return result


def split_piece(piece):
    text=piece['text']; middle=len(text)//2
    if middle<16:
        raise error('Embedding input cannot be subdivided further.',422)
    return [dict(piece,id=str(uuid.uuid4()),text=text[:middle],lineEnd=(piece['lineStart']+text[:middle].count('\n'))),
            dict(piece,id=str(uuid.uuid4()),text=text[middle:],lineStart=piece['lineStart']+text[:middle].count('\n'))]


def vector(value):
    if (not isinstance(value,list) or not 1<=len(value)<=4096 or
            any(isinstance(x,bool) or not isinstance(x,(float,int)) or abs(x)>1e100 or not math.isfinite(x) for x in value)):
        raise error('The embedding model returned invalid vectors.',502)
    norm=math.sqrt(sum(x*x for x in value))
    if not norm or not math.isfinite(norm):
        raise error('The embedding model returned empty vectors.',502)
    return [x/norm for x in value]


async def bounded_json(client, url, payload, limit, timeout):
    async with asyncio.timeout(timeout):
        async with client.stream('POST',url,json=payload,timeout=timeout) as response:
            data=bytearray()
            async for part in response.aiter_bytes():
                if len(data)+len(part)>limit:
                    raise error('Local model output exceeded the safe limit.',502)
                data.extend(part)
            if response.status_code!=200:
                # Context-limit retries are distinct from offline/missing model errors.
                if response.status_code in (400,413) and re.search(r'context|length|token|too long',data.decode(errors='replace'),re.I):
                    raise error('Embedding context length exceeded.',422)
                raise error('Local model request failed. Check installed models and retry.',503)
            try:
                result=json.loads(data)
                if not isinstance(result,dict):raise ValueError()
                return result
            except (ValueError,UnicodeError):
                raise error('Local model returned invalid JSON.',502)


class Knowledge:
    def __init__(self, store, client, settings, coordinator, busy=None):
        self.db=KnowledgeStore(store)
        self.client,self.settings,self.coordinator=client,settings,coordinator
        self.busy=busy or (lambda:False)
        self.jobs={};self.chat_tasks={};self.index_lock=asyncio.Lock();self.closed=False

    async def status(self):
        try:
            r=await self.client.get(self.settings.ollama+'/api/tags',timeout=5)
            r.raise_for_status()
            installed=any(m.get('name')==MODEL for m in r.json()['models'])
            return {'state':'ready' if installed else 'missing','message':'Local documents ready.' if installed else 'Install the local document embedding model before indexing.','model':MODEL}
        except (httpx.HTTPError,KeyError,ValueError,TypeError,AttributeError):
            return {'state':'offline','message':'Ollama is offline. Documents stay saved.','model':MODEL}

    def upload(self, name, data):
        if self.closed:raise error('Document service is shutting down.',503)
        if not isinstance(name,str) or not name or len(name)>240 or any(ord(c)<32 for c in name) or '/' in name or '\\' in name:
            raise error('Choose a valid document filename.')
        suffix=Path(name).suffix.lower()
        if suffix not in ('.txt','.md','.markdown','.pdf'):
            raise error('Import UTF-8 text, Markdown or a text PDF.',415)
        if not data or len(data)>MAX_UPLOAD:
            raise error('Documents must contain 1 byte to 10 MiB.',413)
        if suffix=='.pdf':
            if not data.startswith(b'%PDF-'):raise error('The PDF header is invalid.',415)
        else:
            try:
                decoded=data.decode('utf-8-sig')
                if not decoded.strip() or any(ord(c)<32 and c not in '\n\r\t' for c in decoded):raise ValueError()
            except (UnicodeError,ValueError):
                raise error('Text documents must contain readable UTF-8 text.',415)
        document,created=self.db.add(name,data,hashlib.sha256(data).hexdigest())
        if created:self.schedule(document['id'])
        return document

    def schedule(self, did):
        token=self.db.own(did)
        self.jobs[did]=asyncio.create_task(self._index(did,token))
        return self.db.get(did)

    async def stop(self, did, delete=False):
        self.db.get(did)
        # Invalidate before awaiting cancellation, including callbacks already queued.
        self.db.own(did,'cancelled','Indexing cancelled. Retry when ready.')
        task=self.jobs.pop(did,None)
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):await task
        if delete:
            for task,ids in list(self.chat_tasks.items()):
                if did in ids:task.cancel()
            self.db.delete(did)
            return {'deleted':True,'revision':self.db.revision()}
        return self.db.get(did)

    async def retry(self,did):
        if self.db.get(did)['status']=='ready':
            raise error('This document is already ready.',409)
        await self.stop(did)
        return self.schedule(did)

    async def close(self):
        self.closed=True
        for did in list(self.jobs):
            await self.stop(did)
        for task in list(self.chat_tasks):task.cancel()
        for task in list(self.chat_tasks):
            with suppress(asyncio.CancelledError):await task

    async def wait_idle(self):
        while self.busy() or any(k in ('chat','voice','warm','extract','model-switch') for k in self.coordinator.tasks.values()):
            await asyncio.sleep(.1)

    async def extract(self,did):
        document=self.db.get(did)
        path=self.db.directory/did
        if Path(document['name']).suffix.lower()!='.pdf':
            return {'pages':[{'page':None,'text':path.read_text(encoding='utf-8-sig')}],'warning':''}
        proc=await asyncio.create_subprocess_exec(sys.executable,str(Path(__file__).with_name('pdf_worker.py')),str(path),stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL)
        async def memory_watch():
            while proc.returncode is None:
                if sys.platform == 'darwin':
                    probe=await asyncio.create_subprocess_exec('/bin/ps','-o','rss=','-p',str(proc.pid),stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL)
                    try:
                        raw,_=await asyncio.wait_for(probe.communicate(),2)
                        if raw.strip() and int(raw.strip())>768*1024:
                            raise error('PDF extraction exceeded the 768 MiB memory limit.',413)
                    finally:
                        if probe.returncode is None:
                            with suppress(ProcessLookupError):probe.kill()
                            await probe.wait()
                await asyncio.sleep(.1)
        monitor=asyncio.create_task(memory_watch())
        async def read_output():
            output=bytearray()
            while True:
                part=await proc.stdout.read(65536)
                if not part:break
                if len(output)+len(part)>MAX_OUTPUT:raise error('PDF extraction output exceeded the safe limit.',413)
                output.extend(part)
            await proc.wait()
            return output
        reader=asyncio.create_task(read_output())
        try:
            async with asyncio.timeout(EXTRACT_TIMEOUT):
                done,_=await asyncio.wait((reader,monitor),return_when=asyncio.FIRST_COMPLETED)
                if monitor in done:
                    await monitor
                output=await reader
                code=await proc.wait()

            try:result=json.loads(output)
            except (ValueError,UnicodeError):raise error('The PDF could not be read safely.',422)
            if code or 'error' in result:raise error(result.get('error','The PDF could not be read safely.'),422)
            return result
        except TimeoutError:
            raise error('PDF extraction exceeded 60 seconds. Try a smaller PDF.',422)
        finally:
            for running in (monitor,reader):
                running.cancel()
                with suppress(asyncio.CancelledError,Exception):await running
            if proc.returncode is None:
                with suppress(ProcessLookupError):proc.kill()
                await proc.wait()

    async def background_request(self, operation):
        """Release model ownership promptly when audio or foreground work begins."""
        async def foreground():
            while not (self.busy() or any(k in ('chat','voice','warm','extract','model-switch') for k in self.coordinator.tasks.values())):
                await asyncio.sleep(.05)
        work=asyncio.create_task(operation)
        watcher=asyncio.create_task(foreground())
        try:
            done,_=await asyncio.wait((work,watcher),return_when=asyncio.FIRST_COMPLETED)
            if watcher in done:
                raise error('Indexing paused for foreground activity.',409)
            return await work
        finally:
            for running in (work,watcher):
                running.cancel()
                with suppress(asyncio.CancelledError,Exception):await running

    async def embed_piece(self,piece,depth=0,background=False):
        if background:await self.wait_idle()
        async def request():
            return await bounded_json(self.client,self.settings.ollama+'/api/embed',{
                'model':MODEL,'input':[piece['text']],'truncate':False,'keep_alive':MODEL_KEEP_ALIVE},256*1024,30)
        try:
            if background:
                while True:
                    await self.wait_idle()
                    try:
                        async with self.coordinator.slot('index'):
                            if self.busy():raise error('Foreground audio is active.',409)
                            result=await self.background_request(request())
                        break
                    except JuneError as exc:
                        if exc.status!=409:raise
                        await asyncio.sleep(.1)
            else:result=await request()
            values=result.get('embeddings')
            if not isinstance(values,list) or len(values)!=1:raise error('Invalid embedding response.',502)
            return [dict(piece,vector=vector(values[0]))]
        except JuneError as exc:
            if exc.status!=422 or depth>=8:raise
            result=[]
            for child in split_piece(piece):
                result.extend(await self.embed_piece(child,depth+1,background))
            return result

    async def _index(self,did,token):
        try:
            async with self.index_lock:
                await self.wait_idle()
                if not self.db.update(did,token,status='extracting',message='Reading document.'):return
                while True:
                    await self.wait_idle()
                    try:
                        extracted=await self.background_request(self.extract(did))
                        break
                    except JuneError as exc:
                        if exc.status!=409:raise
                        await asyncio.sleep(.1)
                chunks=passages(extracted['pages'])
                if not chunks:raise error('No readable text was found.',422)
                self.db.update(did,token,status='indexing',message='Creating local search index.')
                ready=[]
                for i,piece in enumerate(chunks):
                    ready.extend(await self.embed_piece(piece,background=True))
                    if len(ready)>MAX_PASSAGES:raise error('The document exceeds the passage limit.',413)
                    if not self.db.update(did,token,progress=(i+1)/len(chunks)):return
                self.db.publish(did,token,ready,len(extracted['pages']),extracted['warning'])
        except asyncio.CancelledError:
            self.db.update(did,token,status='interrupted',message='Indexing interrupted. Retry explicitly.')
            raise
        except (JuneError,httpx.HTTPError,TimeoutError,OSError,ValueError) as exc:
            self.db.update(did,token,status='failed',message=exc.message if isinstance(exc,JuneError) else 'Local indexing failed. Check the model and retry.')
        finally:
            if self.jobs.get(did) is asyncio.current_task():self.jobs.pop(did,None)

    async def search(self,query,ids):
        ids=self.db.select(ids)
        query_parts=await self.embed_piece({'id':'query','text':query,'page':None,'lineStart':1,'lineEnd':query.count('\n')+1})
        dimensions=len(query_parts[0]['vector'])
        if any(len(p['vector'])!=dimensions for p in query_parts):raise error('Embedding dimensions changed. Retry indexing.',502)
        q=vector([sum(p['vector'][i] for p in query_parts) for i in range(dimensions)])
        placeholders=','.join('?' for _ in ids)
        with self.db.store.db() as db:
            rows=[dict(r) for r in db.execute('SELECT p.*,d.name FROM passages p JOIN documents d ON d.id=p.document WHERE d.status=\'ready\' AND p.document IN ('+placeholders+')',ids)]
            words=re.findall(r'\w+',query)[:64]
            fts=' OR '.join('"'+w+'"' for w in words)
            lexical=[r[0] for r in db.execute('SELECT f.id FROM passage_fts f JOIN passages p ON p.id=f.id WHERE passage_fts MATCH ? AND p.document IN ('+placeholders+') ORDER BY bm25(passage_fts) LIMIT 100',[fts,*ids])] if fts else []
        scores={}
        for r in rows:
            v=vector(json.loads(r.pop('vector')))
            if len(v)!=len(q):raise error('Embedding dimensions changed. Retry indexing.',409)
            r['similarity']=sum(a*b for a,b in zip(q,v))
        semantic=sorted(rows,key=lambda r:r['similarity'],reverse=True)
        for ranking in (lexical,[r['id'] for r in semantic[:100]]):
            for rank,cid in enumerate(ranking):scores[cid]=scores.get(cid,0)+1/(60+rank+1)
        ordered=sorted(rows,key=lambda r:scores.get(r['id'],0),reverse=True)
        chosen=[];counts={};size=0
        for r in ordered:
            # Suppress adjacent overlapping passages; prefer document diversity.
            if counts.get(r['document'],0)>=2 and len(ids)>1:continue
            if any(r['document']==p['document'] and r['page']==p['page'] and (r['text'][:100] in p['text'] or p['text'][:100] in r['text']) for p in chosen):continue
            if size+len(r['text'])>2400:continue
            chosen.append(r);size+=len(r['text']);counts[r['document']]=counts.get(r['document'],0)+1
            if len(chosen)==4:break
        return chosen

