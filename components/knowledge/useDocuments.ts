"use client";
import {useCallback,useEffect,useRef,useState} from 'react';
import {knowledgeRequest,type KnowledgeDocument} from '@/lib/knowledge-types';
export function useDocuments(onDeleted:(ids:string[])=>void){
  const [documents,setDocuments]=useState<KnowledgeDocument[]>([]);
  const [loaded,setLoaded]=useState(false);const [error,setError]=useState('');
  const [status,setStatus]=useState<{state:string;message:string;model:string}|null>(null);
  const callback=useRef(onDeleted);callback.current=onDeleted;
  const known=useRef<string[]|null>(null);const channel=useRef<BroadcastChannel|null>(null);
  const generation=useRef(0);const alive=useRef(false);const refreshController=useRef<AbortController|null>(null);
  const refresh=useCallback(async()=>{
    if(refreshController.current)return;
    const version=++generation.current;const controller=new AbortController();refreshController.current=controller;
    try{
      const next=await knowledgeRequest<{documents:KnowledgeDocument[];revision:number}>('documents','GET',undefined,controller.signal);
      if(!alive.current||version!==generation.current)return;
      if(!Array.isArray(next.documents)||!Number.isInteger(next.revision))throw new Error('Invalid document list.');
      const ids=next.documents.map(d=>d.id);const removed=known.current?.filter(id=>!ids.includes(id))||[];
      known.current=ids;if(removed.length)callback.current(removed);
      setDocuments(next.documents);setLoaded(true);setError('');
      const info=await knowledgeRequest<{state:string;message:string;model:string}>('status','GET',undefined,controller.signal);
      if(alive.current&&version===generation.current)setStatus(info);
    }catch(e){if(alive.current&&version===generation.current&&!controller.signal.aborted)setError(e instanceof Error?e.message:'Documents unavailable.');}
    finally{if(refreshController.current===controller)refreshController.current=null;}
  },[]);
  const invalidate=useCallback((ids:string[])=>{
    generation.current++;refreshController.current?.abort();refreshController.current=null;
    if(known.current)known.current=known.current.filter(id=>!ids.includes(id));
    setDocuments(previous=>previous.filter(doc=>!ids.includes(doc.id)));
    callback.current(ids);
  },[]);
  useEffect(()=>{
    alive.current=true;void refresh();const timer=setInterval(()=>{if(!document.hidden)void refresh();},1500);
    const focus=()=>void refresh();window.addEventListener('focus',focus);
    const receive=(ids:unknown)=>{if(Array.isArray(ids)&&ids.every(id=>typeof id==='string')){invalidate(ids);void refresh();}};
    if(typeof BroadcastChannel!=='undefined'){channel.current=new BroadcastChannel('june-documents');channel.current.onmessage=e=>receive(e.data?.deleted);}
    const storage=(e:StorageEvent)=>{if(e.key==='june-documents-deleted'&&e.newValue){try{receive(JSON.parse(e.newValue).deleted);}catch{/* Ignore unrelated storage. */}}};
    window.addEventListener('storage',storage);
    return()=>{alive.current=false;generation.current++;refreshController.current?.abort();refreshController.current=null;clearInterval(timer);window.removeEventListener('focus',focus);window.removeEventListener('storage',storage);channel.current?.close();};
  },[refresh,invalidate]);
  async function remove(id:string){
    await knowledgeRequest(`documents/${encodeURIComponent(id)}`,'DELETE');
    invalidate([id]);channel.current?.postMessage({deleted:[id]});
    try{localStorage.setItem('june-documents-deleted',JSON.stringify({deleted:[id],nonce:crypto.randomUUID()}));}catch{/* Broadcast and polling remain available. */}
    await refresh();
  }
  return {documents,loaded,error,status,refresh,remove};
}
export type Documents=ReturnType<typeof useDocuments>;
