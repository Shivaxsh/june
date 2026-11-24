"use client";
import {useEffect,useId,useRef,useState} from 'react';
import {knowledgeRequest,supportingPassage,type Citation,type DocumentPreview,type Passage} from '@/lib/knowledge-types';
export default function CitationSources({citations,deleted}:{citations:Citation[];deleted:string[]}){
  const [preview,setPreview]=useState<{citation:Citation;passage:Passage}|null>(null);
  const [loading,setLoading]=useState<string|null>(null);const [error,setError]=useState('');
  const active=useRef<{id:string;controller:AbortController}|null>(null);
  const title=useId();const region=useRef<HTMLElement>(null);const opener=useRef<HTMLButtonElement|null>(null);
  useEffect(()=>()=>{active.current?.controller.abort();},[]);
  useEffect(()=>{
    if(active.current&&deleted.includes(active.current.id)){active.current.controller.abort();active.current=null;setLoading(null);}
    if(preview&&deleted.includes(preview.citation.documentId)){setPreview(null);setError('Source deleted. The supporting passage is no longer available.');}
  },[deleted,preview]);
  useEffect(()=>{if(preview)region.current?.focus();},[preview]);
  async function open(citation:Citation,button:HTMLButtonElement){
    opener.current=button;active.current?.controller.abort();const controller=new AbortController();active.current={id:citation.documentId,controller};
    setPreview(null);setLoading(citation.chunkId);setError('');
    try{
      const doc=await knowledgeRequest<DocumentPreview>(`documents/${encodeURIComponent(citation.documentId)}`,'GET',undefined,controller.signal);
      controller.signal.throwIfAborted();
      setPreview({citation,passage:supportingPassage(doc,citation)});
    }catch(e){if(!controller.signal.aborted)setError(e instanceof Error?e.message:'Source preview unavailable.');}
    finally{if(active.current?.controller===controller){active.current=null;setLoading(null);}}
  }
  return <div className="citation-sources"><p>Document sources</p><ol>{citations.map((citation,i)=><li key={`${citation.chunkId}-${i}`}><button className="quiet-button" data-document-id={citation.documentId} disabled={deleted.includes(citation.documentId)||citation.deleted} onClick={e=>void open(citation,e.currentTarget)}>{deleted.includes(citation.documentId)||citation.deleted?(citation.deleted?'Source deleted':`${citation.name} · Source deleted`):`${citation.name} · ${citation.page?`Page ${citation.page}`:`Lines ${citation.lineStart ?? '?'}–${citation.lineEnd ?? '?'}`} · Open supporting passage`}</button></li>)}</ol>{loading&&<p role="status">Opening supporting passage…</p>}{error&&<p role="alert">{error}</p>}{preview&&<section ref={region} tabIndex={-1} className="document-preview" aria-labelledby={title}><h3 id={title}>{preview.citation.name}</h3><p>{preview.passage.page?`Page ${preview.passage.page}`:`Lines ${preview.passage.lineStart ?? '?'}–${preview.passage.lineEnd ?? '?'}`}</p><blockquote>{preview.citation.quote}</blockquote><p>{preview.passage.text}</p><button className="quiet-button" onClick={()=>{setPreview(null);opener.current?.focus();}}>Close supporting passage</button></section>}</div>;
}
