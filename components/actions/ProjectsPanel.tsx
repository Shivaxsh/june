"use client";
import { useRef, useState } from "react";
import { changeProject, proposeProject, runProject, statusText } from "@/lib/actions";
import type { Actions } from "./useActions";

export default function ProjectsPanel({ actions, onAnnounce }: { actions: Actions; onAnnounce(text:string):void }) {
  const [name,setName]=useState(""); const [path,setPath]=useState("");
  const [busy,setBusy]=useState(""); const [error,setError]=useState(""); const lock=useRef(false);
  async function perform(key:string,work:()=>Promise<void>) {
    if(lock.current)return; lock.current=true;setBusy(key);setError("");
    try { await work(); } catch(e) { setError(e instanceof Error?e.message:"June could not update this project."); }
    finally {lock.current=false;setBusy("");}
  }
  return <section className="hands-projects" aria-label="Saved projects">
    <h3>Open a project.</h3>
    <p>Save a folder here, then ask “Open the June project in VS Code.” Each folder has its own approval.</p>
    <form className="project-form" onSubmit={event=>{event.preventDefault();if(!event.nativeEvent.isTrusted)return;void perform("add",async()=>{
      actions.replace(await changeProject("add",{name:name.trim(),path:path.trim()}));setName("");setPath("");onAnnounce("Project saved. Opening it needs its own review.");
    });}}>
      <label>Project name<input required maxLength={60} value={name} onChange={e=>setName(e.target.value)} placeholder="June" /></label>
      <label>Folder path<input required maxLength={1024} value={path} onChange={e=>setPath(e.target.value)} placeholder="/Users/you/Projects/June" autoCapitalize="none" spellCheck={false} /></label>
      <button className="quiet-button" type="submit" disabled={!!busy || !name.trim() || !path.trim()}>Save project</button>
    </form>
    <p className="hands-observed-note">Saving a folder does not open it or grant approval. VS Code may apply its own Workspace Trust check.</p>
    {(actions.state?.projects??[]).map(project=><div className="project-item" key={project.id}>
      <strong>{project.name}</strong><span className="project-path">{project.folderPath}</span>
      <span className="hands-observed-note">{project.remembered?"Approval remembered for this exact folder":"Review before opening"}</span>
      <div className="hands-actions">
        <button className="quiet-button" disabled={!!busy || !actions.state?.available} onClick={event=>{if(!event.nativeEvent.isTrusted)return;void perform(project.id,async()=>{
          const reply=await(project.remembered?runProject(project.id):proposeProject(project.id));actions.upsert(reply.action,reply.serverNow);onAnnounce(statusText(reply.action));
        });}}>{busy===project.id?"Working…":project.remembered?`Open ${project.name}`:`Review opening ${project.name}`}</button>
        {project.remembered&&<button className="quiet-button" disabled={!!busy} onClick={()=>void perform("forget",async()=>{actions.replace(await changeProject("forget",{id:project.id}));onAnnounce("June will ask before opening this folder again.");})}>Forget approval</button>}
        <button className="quiet-button" disabled={!!busy} onClick={()=>void perform("remove",async()=>{actions.replace(await changeProject("remove",{id:project.id}));onAnnounce("Project removed. Its approval and pending proposals are revoked.");})}>Remove project</button>
      </div>
    </div>)}
    {error&&<p className="error-notice" role="alert">{error}</p>}
  </section>;
}
