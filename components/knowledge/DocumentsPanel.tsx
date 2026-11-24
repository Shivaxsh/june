"use client";
import {useEffect,useRef,useState} from 'react';
import {DOCUMENT_LIMIT,knowledgeRequest,type DocumentPreview} from '@/lib/knowledge-types';
import type {Documents} from './useDocuments';
export default function DocumentsPanel({data}:{data:Documents}){
  const [pending,setPending]=useState('');const [error,setError]=useState('');const [preview,setPreview]=useState<DocumentPreview|null>(null);
  const currentDocuments=useRef(data.documents);currentDocuments.current=data.documents;
  const serial=useRef(0);const previewController=useRef<AbortController|null>(null);const mutation=useRef<AbortController|null>(null);
  useEffect(()=>()=>{serial.current++;previewController.current?.abort();mutation.current?.abort();},[]);
  useEffect(()=>{if(data.loaded&&preview&&!data.documents.some(d=>d.id===preview.id)){serial.current++;previewController.current?.abort();setPreview(null);}},[data.documents,data.loaded,preview]);
  async function action(key:string,work:()=>Promise<unknown>){setPending(key);setError('');try{await work();await data.refresh();}catch(e){
    // Cancelling an upload is the person's choice, not an error.
    if(!(e instanceof DOMException&&e.name==='AbortError')&&!(e instanceof Error&&/abort/i.test(e.name)))setError(e instanceof Error?e.message:'Document action failed.');
  }finally{setPending('');}}
  async function show(id:string){const version=++serial.current;previewController.current?.abort();const controller=new AbortController();previewController.current=controller;setPreview(null);setError('');try{const next=await knowledgeRequest<DocumentPreview>(`documents/${encodeURIComponent(id)}`,'GET',undefined,controller.signal);if(version===serial.current && currentDocuments.current.some(d=>d.id===id))setPreview(next);}catch(e){if(!controller.signal.aborted)setError(e instanceof Error?e.message:'Preview unavailable.');}}
  return <details className="documents-panel"><summary>Documents <span>{data.documents.length} saved</span></summary><div className="documents-body">
    <p>June uses ready documents when they can answer your question. Name a file in your message if you mean a specific one.</p>
    <p>Limits: 10 MiB per file, 200 PDF pages, 50 saved documents and 5,000 indexed passages. Scans and encrypted PDFs are not supported.</p>
    {data.status&&<p role="status">{data.status.message}</p>}
    <label className="document-upload">Import a document (up to 10 MiB)<input type="file" accept=".txt,.md,.markdown,.pdf,text/plain,text/markdown,application/pdf" disabled={!!pending} onChange={e=>{const file=e.target.files?.[0];e.target.value='';if(!file)return;if(file.size>DOCUMENT_LIMIT||!file.size||! /\.(txt|md|markdown|pdf)$/i.test(file.name)){setError('Choose a nonempty text, Markdown or text PDF file up to 10 MiB.');return;}mutation.current=new AbortController();void action('upload',()=>knowledgeRequest('documents','POST',file,mutation.current!.signal));}}/></label>
    {pending==='upload'&&<p role="status">Uploading document… <button className="quiet-button" onClick={()=>mutation.current?.abort()}>Cancel upload</button></p>}
    {error&&<p role="alert">{error} <button className="quiet-button" onClick={()=>setError('')}>Dismiss</button></p>}
    {data.error&&<p role="alert">{data.error} <button className="quiet-button" onClick={()=>{setError('');void data.refresh();}}>Retry connection</button></p>}
    <ul className="document-list">{data.documents.map(doc=><li key={doc.id}><strong>{doc.name}</strong><p>{doc.status} · {doc.message}{doc.pages?` · ${doc.pages} pages`:''}</p>{doc.warning&&<p>{doc.warning}</p>}{!['ready','failed','cancelled','error','interrupted'].includes(doc.status)&&<progress aria-label={`Indexing ${doc.name}`} max={1} value={Math.min(1,Math.max(0,doc.progress||0))}/>}
    <div className="document-actions"><button className="quiet-button" disabled={!!pending} onClick={()=>void show(doc.id)}>Preview</button>{['failed','cancelled','error','interrupted'].includes(doc.status)?<button className="quiet-button" disabled={!!pending} onClick={()=>void action(doc.id,()=>knowledgeRequest(`documents/${encodeURIComponent(doc.id)}/retry`,'POST'))}>Retry indexing</button>:doc.status!=='ready'&&<button className="quiet-button" disabled={!!pending} onClick={()=>void action(doc.id,()=>knowledgeRequest(`documents/${encodeURIComponent(doc.id)}/cancel`,'POST'))}>Cancel indexing</button>}<button className="quiet-button" disabled={!!pending} onClick={()=>void action(doc.id,()=>data.remove(doc.id))}>Delete <span className="sr-only">{doc.name}</span></button></div></li>)}</ul>
    {data.loaded&&!data.documents.length&&<p>No documents yet.</p>}
    {preview&&<section className="document-preview" aria-label={`Preview of ${preview.name}`}><h3>{preview.name}</h3><button className="quiet-button" onClick={()=>{serial.current++;previewController.current?.abort();setPreview(null);}}>Close preview</button>{preview.passages?.map(p=><div key={p.id}><small>{p.page?`Page ${p.page}`:`Lines ${p.lineStart ?? '?'}–${p.lineEnd ?? '?'}`}</small><p>{p.text}</p></div>)}</section>}
  </div></details>;
}
