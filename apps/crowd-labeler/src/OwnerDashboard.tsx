import { useEffect, useMemo, useState } from 'react';
import { Download, RefreshCw, ShieldCheck, ArrowLeft } from 'lucide-react';
import { questions } from './lib/survey';
import { aggregateMaps, reviewsCsv, score } from './lib/owner-data';
import type { Dataset, Snapshot, OwnerReview, Participant } from './lib/owner-data';
import { downloadText } from './lib/csv';
import './owner.css';

class AccessError extends Error { constructor(public status: number) { super('Access denied'); } }
async function get<T>(path: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(path, { credentials: 'same-origin', cache: 'no-store', signal });
  if (response.status === 401 || response.status === 403) throw new AccessError(response.status);
  if (!response.ok) throw new Error('Unable to load the dataset. Please retry.');
  return response.json();
}
async function pages<T>(kind: string, through: number, signal: AbortSignal, onProgress: (n: number) => void) {
  const rows: T[] = []; let cursor = 0;
  do {
    const page = await get<{ rows: T[]; next: number | null }>(`/api/owner/${kind}?through=${through}&after=${cursor}`, signal);
    rows.push(...page.rows); onProgress(rows.length);
    if (page.next === null) break;
    if (!Number.isSafeInteger(page.next) || page.next <= cursor) throw new Error('Invalid export cursor. Please retry.');
    cursor = page.next;
  } while (true);
  return rows;
}
export function OwnerDashboard() {
  const [data,setData] = useState<Dataset|null>(null);
  const [error,setError] = useState('');
  const [access,setAccess] = useState(0);
  const [loading,setLoading] = useState(true);
  const [loaded,setLoaded] = useState(0);
  const [revision,setRevision] = useState(0);
  const [tab,setTab] = useState<'maps'|'reviews'>('maps');
  const [search,setSearch] = useState('');
  const [phase,setPhase] = useState('all');
  const [question,setQuestion] = useState('quality');
  const [page,setPage] = useState(1);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError(''); setAccess(0); setLoaded(0); setData(null);
    (async () => {
      const snapshot = await get<Snapshot>('/api/owner/snapshot', controller.signal);
      const reviewRows = await pages<OwnerReview>('reviews',snapshot.reviews.through,controller.signal,setLoaded);
      const participantRows = await pages<Participant>('participants',snapshot.participants.through,controller.signal,()=>{});
      if (reviewRows.length !== snapshot.reviews.count || participantRows.length !== snapshot.participants.count) throw new Error('Dataset changed while loading. Please refresh before exporting.');
      if (!controller.signal.aborted) { setData({...snapshot,reviewRows,participantRows}); setPage(1); }
    })().catch(e=>{if (!controller.signal.aborted) { if(e instanceof AccessError)setAccess(e.status);else setError(e.message); }}).finally(()=>{if(!controller.signal.aborted)setLoading(false);});
    return () => controller.abort();
  },[revision]);
  const filtered = useMemo(()=> (data?.reviewRows||[]).filter(r => (phase==='all'||r.phase===phase) && `${r.mapName} ${r.mapFolder} ${r.profile.name} ${r.respondentId}`.toLowerCase().includes(search.toLowerCase())),[data,phase,search]);
  const aggregates = useMemo(()=>aggregateMaps(filtered),[filtered]);
  const total = tab==='maps'?aggregates.length:filtered.length;
  const maxPage = Math.max(1,Math.ceil(total/25));
  const activePage = Math.min(page,maxPage);
  const start = (activePage-1)*25;
  function exportData(format: 'json'|'csv') {
    if (!data || loading) return;
    const stamp = data.exportedAt.replaceAll(':','-').replace(/\.\d+Z$/,'Z');
    if(format==='json') {
      const {reviewRows,participantRows,...metadata} = data;
      downloadText(`mapgen-full-dataset-${stamp}.json`,JSON.stringify({...metadata,snapshot:{reviews:metadata.reviews,participants:metadata.participants},exportNotes:'Append-only reviews through the recorded watermark; current participant profiles at export time. Session credentials excluded.',reviews:reviewRows,participants:participantRows},null,2),'application/json');
    } else downloadText(`mapgen-all-reviews-${stamp}.csv`,reviewsCsv(data.reviewRows),'text/csv;charset=utf-8');
  }
  return <main className="owner-page">
    <header className="owner-header"><div><span className="eyebrow"><ShieldCheck size={15}/> OWNER ONLY</span><h1>Collection dashboard</h1><p>Review annotations and save a complete local backup.</p></div><a className="button ghost" href="/"><ArrowLeft size={16}/> Public survey</a></header>
    {access!==0?<section className="owner-card owner-access"><ShieldCheck size={30}/><h2>{access===401?'Sign in to your owner account':'Owner access required'}</h2><p>{access===401?'Use the ChatGPT account that owns this site.':'This signed-in account is not authorized to view participant responses.'}</p><a className="button primary" href={access===401?'/signin-with-chatgpt?return_to=%2Fowner':'/signout-with-chatgpt?return_to=%2Fowner'} target="_top">{access===401?'Sign in with ChatGPT':'Switch account'}</a></section>:<>
    <section className="owner-toolbar"><button className="button light" disabled={loading} onClick={()=>setRevision(revision+1)}><RefreshCw size={16}/> Refresh data</button><span>{data?`Loaded ${new Date(data.exportedAt).toLocaleString()}`:'Loading central collection'}</span><button className="button primary" disabled={!data||loading} onClick={()=>exportData('json')}><Download size={16}/> Full dataset · JSON</button><button className="button ghost" disabled={!data||loading} onClick={()=>exportData('csv')}><Download size={16}/> All reviews · CSV</button></section>
    <p className="owner-note">Downloads include all collected records, regardless of the filters below. JSON includes reviews, current player profiles, question definitions and the calibration rubric. CSV contains one row per review. Keep JSON for complete backups.</p>
    {loading&&<p className="owner-card" role="status">Loading securely… {loaded} reviews received</p>}
    {error&&<p className="error" role="alert">{error} No partial export will be downloaded.</p>}
    {data&&<>
      <section className="owner-stats">{[['Total reviews',data.reviewRows.length],['Maps annotated',new Set(data.reviewRows.map(r=>r.mapId)).size],['Contributors',new Set(data.reviewRows.map(r=>r.respondentId)).size],['Registered profiles',data.participantRows.filter(p=>p.profile.saved).length],['Calibration reviews',data.reviewRows.filter(r=>r.phase==='calibration').length],['Collection reviews',data.reviewRows.filter(r=>r.phase==='collection').length]].map(([label,value])=><div className="owner-card" key={label}><span>{label}</span><strong>{value}</strong></div>)}</section>
      <section className="owner-card"><div className="owner-filters"><div className="view-toggle"><button aria-pressed={tab==='maps'} className={tab==='maps'?'selected':''} onClick={()=>{setTab('maps');setPage(1);}}>Map summaries</button><button aria-pressed={tab==='reviews'} className={tab==='reviews'?'selected':''} onClick={()=>{setTab('reviews');setPage(1);}}>Individual reviews</button></div><label>Search map or player<input value={search} onChange={e=>{setSearch(e.target.value);setPage(1);}} placeholder="Name, map folder or respondent ID"/></label><label>Review phase<select value={phase} onChange={e=>{setPhase(e.target.value);setPage(1);}}><option value="all">All phases</option><option value="calibration">Calibration</option><option value="collection">Collection</option></select></label>{tab==='maps'&&<label>Compare rating<select value={question} onChange={e=>setQuestion(e.target.value)}>{questions.map(q=><option value={q.id} key={q.id}>{q.title}</option>)}</select></label>}</div>
      {!data.reviewRows.length?<div className="owner-empty"><h2>Waiting for the first review</h2><p>Share the public survey link with your players. Their submitted reviews will appear here when you refresh.</p></div>:!total?<p className="owner-empty">No records match these filters.</p>:tab==='maps'?<><p className="owner-note">Unweighted averages of answered ratings; “Not sure” is excluded. Spread is the difference between the highest and lowest answers. Player experience and game configuration can explain disagreements.</p><div className="owner-table"><table><thead><tr><th>Map</th><th>Reviews</th><th>Players</th><th>Answered</th><th>Average / 5</th><th>Spread</th></tr></thead><tbody>{aggregates.slice(start,start+25).map(m=><tr key={m.id}><td><button className="text-button" onClick={()=>{setSearch(m.name);setTab('reviews');setPage(1);}}>{m.name}</button></td><td>{m.count}</td><td>{m.players}</td><td>{m.answers[question].n}</td><td>{m.answers[question].mean?.toFixed(2)??'—'}</td><td>{m.answers[question].spread??'—'}</td></tr>)}</tbody></table></div></>:<div className="owner-reviews">{filtered.slice(start,start+25).map(r=><details className="owner-review" key={r.id}><summary><strong>{r.mapName}</strong><span>{r.profile.name||'Unnamed player'} · {r.profile.rating||'Unrated'} {r.profile.ratingMode} · {r.familiarity} · {r.configuration}</span><small>{r.phase} · {new Date(r.receivedAt).toLocaleString()}</small></summary><p className="owner-note">{r.profile.experience} · {r.profile.modes.join(', ')} · Respondent: {r.respondentId}</p><dl className="owner-answers">{questions.map(q=><div key={q.id}><dt>{q.title}</dt><dd>{score(r,q.id)===null?'Not sure':`${score(r,q.id)} · ${q.labels[score(r,q.id)!-1]}`}</dd></div>)}</dl><p><b>Biomes:</b> {r.biomes.join(', ')||'Not sure'}</p><p><b>Unique traits:</b> {(r.uniqueTraits||[]).join(', ')||'—'} {r.uniqueText}</p><p><b>Setup:</b> {r.setup}</p><p><b>Notes:</b> {r.note||'—'}</p><p className="owner-note">Review {r.id} · Rubric {r.calibrationRevision} · {r.secondsSpent}s · Suggestions {r.suggestionsShown?'shown':'not shown'}</p></details>)}</div>}
      <nav className="pagination" aria-label="Dashboard pages"><button className="button ghost" disabled={activePage===1} onClick={()=>setPage(activePage-1)}>Previous</button><span>{total} {tab==='maps'?'maps':'reviews'} · Page {activePage} / {maxPage}</span><button className="button ghost" disabled={activePage===maxPage} onClick={()=>setPage(activePage+1)}>Next</button></nav></section>
      <p className="owner-note">Ratings and experience are self-reported. Calibration reference scoring is still pending expert ranges; this dashboard does not discard or automatically downweight responses.</p>
    </>}
    </>}
  </main>;
}
