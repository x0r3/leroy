export interface Parameter {name:string; label:string; description:string; kind:string; default:unknown; choices:string[]; required:boolean}
export interface Step {id:string; name:string; needs:string[]; status:string; reason:string; started_at:string|null; finished_at:string|null; exit_code:number|null; outputs:Record<string,unknown>; log_bytes:number}
export interface Artifact {id:string; name:string; size:number; sha256:string; step_id:string}
export interface Run {id:string; number:number; pipeline_id:string; status:string; trigger:string; actor:string; commit:string|null; image_digest:string|null; runner:string|null; reason:string; created_at:string; started_at:string|null; finished_at:string|null; parent_id:string|null; retry_of:string|null; parameters:Record<string,unknown>; outputs:Record<string,unknown>; snapshot:{steps:Step[]; name:string}; steps:Step[]; artifacts:Artifact[]; children:Run[]; cancel_requested:boolean}
export interface Pipeline {id:string; enabled:boolean; revision:number; last_run:Run|null; spec:{name:string; group:string; description:string; parameters:Parameter[]; steps:Step[]; repository:string; ref:string; concurrency:string; schedule:string|null; poll_seconds:number; timeout:number; profile:string; source:Record<string,unknown>}}
export interface Runner {id:string; profiles:string[]; online:boolean; capacity:number; last_seen:string}
export interface Event {id:number; kind:string; step_id:string|null; data:Record<string,unknown>; created_at:string}
export const labels:Record<string,string> = {queued:'In Warteschlange',pending:'Ausstehend',running:'Läuft',waiting:'Wartet auf Unterjob',succeeded:'Erfolgreich',failed:'Fehlgeschlagen',cancelled:'Abgebrochen',skipped:'Übersprungen',interrupted:'Unterbrochen',timed_out:'Zeitlimit erreicht'};
export const terminal = (status:string) => !['queued','running','waiting','pending'].includes(status);
export const date = (value:string|null) => value ? new Intl.DateTimeFormat('de-DE',{dateStyle:'medium',timeStyle:'short'}).format(new Date(value)) : '—';
export const elapsed = (start:string|null, end:string|null) => {if(!start)return '—'; const secs=Math.max(0,Math.floor(((end?Date.parse(end):Date.now())-Date.parse(start))/1000));return secs<60?`${secs}s`:`${Math.floor(secs/60)}m ${secs%60}s`};
export class ApiError extends Error { constructor(message:string, public status:number){super(message)} }
export async function api<T>(path:string, method='GET', body?:unknown):Promise<T> {
  const response=await fetch('/api'+path,{method,headers:{'Content-Type':'application/json','X-Leroy-Request':'1'},body:body===undefined?undefined:JSON.stringify(body)});
  if(!response.ok){const error=await response.json().catch(()=>({detail:response.statusText}));throw new ApiError(typeof error.detail==='string'?error.detail:JSON.stringify(error.detail),response.status);}
  return response.json();
}
