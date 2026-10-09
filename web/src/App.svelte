<script lang="ts">
  import { onMount } from 'svelte';
  import RunDetail from './RunDetail.svelte';
  import {ApiError,api,date,elapsed,labels,terminal,type Pipeline,type Run,type Runner} from './types';
  let account=$state<{name:string;role:string}|null>(null), loading=$state(true), error=$state(''), busy=$state(false);
  let refreshSerial=0, loadedRoute=$state('');
  let connected=$state(false), older=$state<Run[]>([]), moreBusy=$state(false), endOfHistory=$state(false);
  let username=$state('admin'), password=$state(''), route=$state(location.hash.slice(1)||'/overview');
  let pipelines=$state<Pipeline[]>([]), runs=$state<Run[]>([]), runners=$state<Runner[]>([]), run=$state<Run|null>(null);
  let allRuns=$derived([...runs,...older.filter(o=>!runs.some(r=>r.id===o.id))].sort((a,b)=>b.number-a.number));
  let system=$state<{version:string;database:string;storage:string;origin:string;timezone:string;counts:Record<string,number>}|null>(null);
  let query=$state(''), status=$state('all'), group=$state('all'), dialog=$state<Pipeline|null>(null), values=$state<Record<string,unknown>>({});
  let canOperate=$derived(account?.role==='admin'||account?.role==='operator');
  let current=$derived(pipelines.find(p=>route==='/pipelines/'+p.id));
  let groups=$derived([...new Set(pipelines.map(p=>p.spec.group))]);
  let filteredPipelines=$derived(pipelines.filter(p=>(group==='all'||p.spec.group===group)&&`${p.id} ${p.spec.description}`.toLowerCase().includes(query.toLowerCase())));
  let filteredRuns=$derived(allRuns.filter(r=>(status==='all'||r.status===status)&&(!current||r.pipeline_id===current.id)&&r.pipeline_id.toLowerCase().includes(query.toLowerCase())));
  let active=$derived(['queued','running','waiting'].reduce((count,state)=>count+(system?.counts[state]||0),0));
  let pageTitle=$derived(route==='/overview'?'Übersicht':route==='/runs'?'Ausführungen':route==='/runners'?'Runner':route==='/settings'?'System':current?.id||'Pipelines');
  async function refresh(){
    if(!account)return;
    const requestedRoute=route, serial=++refreshSerial;
    try{
      const [p,r,w,s]=await Promise.all([api<Pipeline[]>('/pipelines'),api<Run[]>('/runs?limit=100'+(requestedRoute.startsWith('/pipelines/')?'&pipeline='+encodeURIComponent(requestedRoute.split('/')[2]):'')),api<Runner[]>('/runners'),api<NonNullable<typeof system>>('/system')]);
      if(route!==requestedRoute||serial!==refreshSerial)return;
      pipelines=p;runs=r;runners=w;system=s;loadedRoute=requestedRoute;if(!connected)error='';connected=true;
      if(requestedRoute.startsWith('/runs/')){const detail=await api<Run>('/runs/'+requestedRoute.split('/')[2]);if(route===requestedRoute&&serial===refreshSerial)run=detail;}else run=null;
    }catch(e){connected=false;if(e instanceof ApiError&&e.status===401){account=null;loadedRoute='';run=null;dialog=null;error='Die Sitzung ist abgelaufen. Bitte erneut anmelden.'}else error=e instanceof ApiError?e.message:'Verbindung zum Controller unterbrochen. Die Ansicht wird nach der Wiederverbindung aktualisiert.'}
  }
  onMount(()=>{
    let stopped=false;
    api<{name:string;role:string}>('/auth/me').then(a=>{account=a;return refresh()}).catch(()=>{}).finally(()=>loading=false);
    const change=()=>{route=location.hash.slice(1)||'/overview';run=null;older=[];endOfHistory=false;query='';error='';window.scrollTo(0,0);refresh()};
    window.addEventListener('hashchange',change);
    const timer=setInterval(()=>{if(!stopped&&account&&!document.hidden)refresh()},3000);
    return()=>{stopped=true;clearInterval(timer);window.removeEventListener('hashchange',change)};
  });
  $effect(()=>{
    const id=route.startsWith('/runs/')?route.split('/')[2]:null;
    if(!account||!id)return;
    const stream=new EventSource('/api/runs/'+id+'/stream');let timeout:ReturnType<typeof setTimeout>|undefined;
    stream.addEventListener('session-expired',()=>{stream.close();account=null;loadedRoute='';run=null;dialog=null;error='Die Sitzung ist abgelaufen. Bitte erneut anmelden.'});
    stream.onmessage=()=>{if(!timeout)timeout=setTimeout(()=>{refresh();timeout=undefined},300)};
    return()=>{stream.close();clearTimeout(timeout)};
  });
  async function loadOlder(){
    moreBusy=true;const requestedRoute=route;
    try{const before=Math.min(...allRuns.map(r=>r.number));const page=await api<Run[]>(`/runs?limit=100&before=${before}${current?'&pipeline='+encodeURIComponent(current.id):''}`);if(route===requestedRoute){older=[...older,...page];endOfHistory=page.length<100;}}catch(e){error=String(e)}finally{moreBusy=false}
  }
  async function login(event:SubmitEvent){event.preventDefault();busy=true;error='';try{account=await api('/auth/login','POST',{username,password});password='';await refresh()}catch(e){error=String(e)}finally{busy=false}}
  function showModal(node:HTMLDialogElement){node.showModal()}
  async function logout(){await api('/auth/logout','POST',{});account=null;loadedRoute='';run=null}
  function openStart(p:Pipeline){dialog=p;values=Object.fromEntries(p.spec.parameters.map(v=>[v.name,v.default??(v.kind==='boolean'?false:'')]));error=''}
  async function start(event:SubmitEvent){event.preventDefault();if(!dialog)return;busy=true;error='';try{const created=await api<Run>('/pipelines/'+dialog.id+'/runs','POST',{parameters:values});dialog=null;location.hash='/runs/'+created.id;await refresh()}catch(e){error=String(e)}finally{busy=false}}
  async function toggle(p:Pipeline){try{await api('/pipelines/'+p.id+'/enabled','POST',{enabled:!p.enabled});await refresh()}catch(e){error=String(e)}}
  function navigateGroup(value:string){group=value;location.hash='/pipelines'}
</script>

{#if loading}<main class="loading-screen"><div class="brand-mark">L</div><p>Leroy wird geladen …</p></main>
{:else if !account}
<main class="login-page"><section class="login-form"><div class="brand"><span class="brand-mark">L</span><span>leroy<span class="brand-dot">.</span></span></div><form onsubmit={login}><h1>Anmelden</h1>{#if error}<div class="error" role="alert">{error.replace('Error: ','')}</div>{/if}<label>Benutzername<input autocomplete="username" bind:value={username} required/></label><label>Passwort<input type="password" autocomplete="current-password" bind:value={password} required/></label><button class="primary full" disabled={busy}>{busy?'Anmeldung läuft …':'Anmelden →'}</button></form></section></main>
{:else}
<div class="app-shell"><aside class="sidebar"><a class="brand" href="#/overview"><span class="brand-mark">L</span><span>leroy<span class="brand-dot">.</span></span></a><div class="workspace"><span class="workspace-icon">H</span><div><strong>Home Lab</strong></div></div><nav aria-label="Hauptnavigation">{#each [['/overview','◫','Übersicht'],['/pipelines','◇','Pipelines'],['/runs','≡','Ausführungen'],['/runners','▣','Runner'],['/settings','⚙','System']] as [path,icon,label]}<a class:active={route===path||route.startsWith(path+'/')} href="#{path}"><span class="nav-icon" aria-hidden="true">{icon}</span>{label}{#if path==='/runs'&&active}<span class="nav-count">{active}</span>{/if}</a>{/each}</nav><div class="sidebar-projects"><span class="eyebrow">PROJEKTE</span>{#each groups as g}<button onclick={()=>navigateGroup(g)}><span class="project-dot"></span>{g}<span>{pipelines.filter(p=>p.spec.group===g).length}</span></button>{/each}</div><div class="sidebar-bottom"><div class="connection" role="status"><span class="status-dot {connected?'succeeded':'interrupted'}"></span>{connected?'Controller verbunden':'Verbindung unterbrochen'}</div><button class="account" onclick={logout} aria-label="Abmelden"><span class="avatar">{account.name[0].toUpperCase()}</span><span><strong>{account.name}</strong><small>{account.role} · Abmelden</small></span><span aria-hidden="true">↗</span></button></div></aside>
<div class="main-shell"><header class="topbar"><div><span class="topbar-label">HOME LAB</span><span class="separator">/</span><span>{pageTitle}</span></div><span class="environment"><span class="status-dot {connected?'running':'interrupted'}"></span>{connected?'Live-Ansicht':'Offline'}</span><button class="mobile-logout" onclick={logout} aria-label="Abmelden">Abmelden</button></header><main class="page">
{#if error&&!dialog}<div class="error" role="alert">{error.replace('Error: ','')}<button aria-label="Fehlermeldung schließen" onclick={()=>error=''}>×</button></div>{/if}
{#if loadedRoute!==route}<div class="empty-state" role="status">Ansicht wird geladen …</div>
{:else if route.startsWith('/runs/')}{#if run}{#key run.id}<RunDetail {run} {refresh} {canOperate} onerror={text=>error=text}/>{/key}{:else}<div class="empty-state">Lauf wird geladen …</div>{/if}
{:else if route==='/overview'}
<div class="page-heading"><div><h1>Übersicht</h1></div><a class="button secondary" href="#/pipelines">Pipelines ↗</a></div>
<div class="stats"><div><span>Pipelines</span><strong>{pipelines.length}</strong><small>{groups.length} Projekte</small></div><div><span>Aktive Ausführungen</span><strong>{active}<span class="metric-dot"></span></strong><small>{system?.counts.queued||0} in der Warteschlange</small></div><div><span>Letzte Ergebnisse</span><strong>{runs.filter(r=>r.status==='succeeded').length}<span class="metric-unit">erfolgreich</span></strong><small>Aus den letzten {runs.length} Läufen</small></div><div><span>Runner verfügbar</span><strong>{runners.filter(r=>r.online).length}<span class="metric-unit">/ {runners.length}</span></strong><small>{runners.filter(r=>r.online).reduce((n,r)=>n+r.capacity,0)} Ausführungsplätze</small></div></div>
<section class="section-heading"><div><h2>Letzte Ausführungen</h2></div><a href="#/runs">Alle Ausführungen →</a></section>
<section class="panel">{@render runTable(runs.slice(0,8))}</section>
<section class="section-heading"><div><h2>Pipelines</h2></div><a href="#/pipelines">Alle Pipelines →</a></section><div class="pipeline-grid">{#each pipelines.slice(0,6) as p}{@render pipelineCard(p)}{/each}</div>
{:else if route==='/runners'}
<div class="page-heading"><div><h1>Runner</h1></div></div><div class="pipeline-grid">{#each runners as r}<section class="panel runner-card"><div class="card-top"><span class="project-label">DOCKER RUNNER</span><span class="badge {r.online?'succeeded':'interrupted'}">{r.online?'Online':'Offline'}</span></div><h2>{r.id}</h2><dl><dt>Kapazität</dt><dd>{r.capacity} gleichzeitige Aufträge</dd><dt>Profile</dt><dd>{r.profiles.join(', ')}</dd><dt>Letzte Meldung</dt><dd>{date(r.last_seen)}</dd></dl></section>{:else}<div class="empty-state"><strong>Noch kein Runner verbunden</strong></div>{/each}</div>
{:else if route==='/settings'}
<div class="page-heading"><div><h1>System</h1></div></div><section class="panel system-panel"><h2>Leroy Controller</h2><dl><dt>Version</dt><dd>{system?.version||'—'}</dd><dt>Datenbank</dt><dd>{system?.database||'—'}</dd><dt>Artefaktspeicher</dt><dd>Persistentes Dateisystem</dd><dt>Zeitzone</dt><dd>{system?.timezone||'—'}</dd><dt>Adresse</dt><dd>{system?.origin||'—'}</dd></dl></section>
{:else if current}
<div class="breadcrumbs"><a href="#/pipelines">Pipelines</a><span>/</span><span>{current.spec.group}</span></div><div class="page-heading"><div><div class="eyebrow">{current.spec.group.toUpperCase()}</div><h1>{current.spec.name}</h1>{#if current.spec.description}<p class="subtle">{current.spec.description}</p>{/if}</div>{#if canOperate}<button class="primary" onclick={()=>openStart(current!)}>Pipeline starten →</button>{/if}</div><section class="panel pipeline-config"><div><span>Quelle</span><code class="wrap">{current.spec.repository||'Betriebsaufgabe ohne Repository'}</code></div><div><span>Branch</span><strong>{current.spec.ref}</strong></div><div><span>Ausführung</span><strong>{current.spec.concurrency==='serial'?'Nacheinander':current.spec.concurrency==='replace'?'Veraltete Läufe abbrechen':'Parallel'}</strong></div><div><span>Automatische Auslöser</span><button class="text-button" disabled={account.role!=='admin'} onclick={()=>toggle(current!)}>{current.enabled?'Aktiv · deaktivieren':'Pausiert · aktivieren'}</button></div></section><section class="section-heading"><h2>{current.spec.steps.length} definierte Schritte</h2><span class="subtle">Definition v{current.revision}</span></section><div class="definition-steps">{#each current.spec.steps as s,i}<div><span class="step-order">{String(i+1).padStart(2,'0')}</span><strong>{s.name}</strong><small>{s.needs.length?'Nach '+s.needs.join(', '):'Startschritt'}</small></div>{/each}</div><section class="section-heading"><h2>Ausführungsverlauf</h2></section><section class="panel">{@render runTable(filteredRuns)}</section>{#if allRuns.length>=100&&!endOfHistory}<div class="history-more"><button disabled={moreBusy} onclick={loadOlder}>{moreBusy?'Wird geladen …':'Ältere Ausführungen laden'}</button></div>{/if}<details class="source-details"><summary>Herkunft und Migration</summary><!-- svelte-ignore a11y_no_noninteractive_tabindex (Scrollable output needs keyboard access.) --><pre class="json" tabindex="0" role="region" aria-label="Strukturierte Daten">{JSON.stringify(current.spec.source,null,2)}</pre></details>
{:else if route==='/runs'}
<div class="page-heading"><div><h1>Ausführungen</h1></div></div><div class="toolbar"><label class="search"><span aria-hidden="true">⌕</span><input aria-label="Ausführungen suchen" placeholder="Pipeline suchen …" bind:value={query}/></label><select aria-label="Nach Status filtern" bind:value={status}><option value="all">Alle Status</option>{#each Object.entries(labels).filter(([s])=>s!=='pending') as [key,value]}<option value={key}>{value}</option>{/each}</select><span class="subtle">{filteredRuns.length} Ausführungen</span></div><section class="panel">{@render runTable(filteredRuns)}</section>{#if allRuns.length>=100&&!endOfHistory}<div class="history-more"><button disabled={moreBusy} onclick={loadOlder}>{moreBusy?'Wird geladen …':'Ältere Ausführungen laden'}</button></div>{/if}
{:else}
<div class="page-heading"><div><h1>Pipelines</h1></div></div><div class="toolbar"><label class="search"><span aria-hidden="true">⌕</span><input aria-label="Pipelines suchen" placeholder="Pipelines suchen …" bind:value={query}/></label><select aria-label="Nach Projekt filtern" bind:value={group}><option value="all">Alle Projekte</option>{#each groups as g}<option value={g}>{g}</option>{/each}</select><span class="subtle">{filteredPipelines.length} Pipelines</span></div><div class="pipeline-grid">{#each filteredPipelines as p}{@render pipelineCard(p)}{:else}<div class="empty-state"><strong>Keine passende Pipeline</strong><p>Ändere den Suchbegriff oder den Projektfilter.</p></div>{/each}</div>
{/if}
</main></div></div>
{/if}

{#snippet pipelineCard(p:Pipeline)}<article class="panel pipeline-card"><div class="card-top"><span class="project-label">{p.spec.group}</span><span class="badge {p.last_run?.status||'pending'}">{p.last_run?labels[p.last_run.status]:'Noch nicht ausgeführt'}</span></div><a class="card-title" href="#/pipelines/{p.id}">{p.spec.name}<span>↗</span></a>{#if p.spec.description}<p>{p.spec.description}</p>{/if}<div class="mini-pipeline" role="img" aria-label="{p.spec.steps.length} Schritte">{#each p.spec.steps.slice(0,12) as s,i}<span></span>{#if i<Math.min(p.spec.steps.length,12)-1}<i></i>{/if}{/each}</div><div class="card-bottom"><span>{p.spec.steps.length} Schritte · {p.enabled?'Automatik aktiv':'Manueller Start'}</span>{#if canOperate}<button class="text-button" onclick={()=>openStart(p)}>Starten →</button>{/if}</div></article>{/snippet}

{#snippet runTable(items:Run[])}{#if items.length}<div class="table-scroll"><table><thead><tr><th>Pipeline / Lauf</th><th>Status</th><th>Revision</th><th>Auslöser</th><th>Dauer</th><th>Gestartet</th></tr></thead><tbody>{#each items as r}<tr><td><a class="run-link" href="#/runs/{r.id}"><strong>{r.pipeline_id}</strong><small>#{r.number}</small></a></td><td><span class="badge {r.status}">{labels[r.status]}</span></td><td><code>{r.commit?.slice(0,8)||'—'}</code></td><td><span class="trigger-label">{r.trigger}</span></td><td class="numeric">{elapsed(r.started_at,r.finished_at)}</td><td class="subtle nowrap">{date(r.created_at)}</td></tr>{/each}</tbody></table></div>{:else}<div class="empty-state"><div class="empty-symbol">◇</div><strong>Keine Ausführungen</strong><a href="#/pipelines">Pipeline auswählen →</a></div>{/if}{/snippet}

{#if dialog}<div class="modal-backdrop" role="presentation"><dialog class="modal" use:showModal onclose={()=>dialog=null} aria-labelledby="start-title"><div class="panel-heading"><div><div class="eyebrow">NEUE AUSFÜHRUNG</div><h2 id="start-title">{dialog.spec.name}</h2></div><button class="close-button" aria-label="Dialog schließen" onclick={()=>dialog=null}>×</button></div><form onsubmit={start}><div class="modal-content">{#if error}<div class="error" role="alert">{error.replace('Error: ','')}</div>{/if}{#each dialog.spec.parameters as p}<label class:checkbox={p.kind==='boolean'}>{#if p.kind==='boolean'}<input type="checkbox" checked={Boolean(values[p.name])} onchange={e=>values[p.name]=e.currentTarget.checked}/><span>{p.label||p.name}</span>{:else}<span>{p.label||p.name}{p.required?' *':''}</span>{#if p.kind==='choice'}<select value={String(values[p.name]??'')} onchange={e=>values[p.name]=e.currentTarget.value}>{#each p.choices as choice}<option value={choice}>{choice}</option>{/each}</select>{:else if p.kind==='text'}<textarea rows="3" value={String(values[p.name]??'')} onchange={e=>values[p.name]=e.currentTarget.value} required={p.required}></textarea>{:else}<input type={p.kind==='integer'?'number':'text'} value={String(values[p.name]??'')} onchange={e=>values[p.name]=p.kind==='integer'?Number(e.currentTarget.value):e.currentTarget.value} required={p.required}/>{/if}<small>{p.description}</small>{/if}</label>{:else}<p>Branch: <code>{dialog.spec.ref}</code></p>{/each}</div><div class="modal-footer"><button type="button" onclick={()=>dialog=null}>Abbrechen</button><button class="primary" disabled={busy}>{busy?'Wird eingeplant …':'Ausführung starten →'}</button></div></form></dialog></div>{/if}
