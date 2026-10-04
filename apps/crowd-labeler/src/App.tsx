import { hosted, loadRemote, saveRemoteProfile, saveRemoteReview } from './lib/remote';
import { LanguageContext, useTranslation } from './lib/language';
import { translate } from './lib/i18n';
import { useEffect, useRef, useState } from 'react';
import { ArrowRight, ArrowUpRight, Check, CheckCircle2, ChevronRight, Compass, Download, Flag, Layers, Map as MapIcon, Maximize2, Settings2, ShieldCheck, Sparkles, Users, X } from 'lucide-react';
import catalog from './data/review-maps.json';
import { downloadText, toCsv } from './lib/csv';
import { anchorFolders, defaultAnswers, defaultConfiguration, isComplete, uniqueSuggestions, vaultPreview, calibrationStatus, familiarityOptions, modes, questions, initialState, readState, selectMap, STORAGE_KEY, suggestion } from './lib/survey';
import type { Answer, CatalogMap, Profile, State, Submission } from './lib/survey';

const maps = catalog as CatalogMap[];
const fmt=(n:number|null,suffix='')=>n===null?'—':`${Number.isInteger(n)?n:n.toFixed(1)}${suffix}`;
const toggle=(list:string[],value:string)=>list.includes(value)?list.filter(x=>x!==value):[...list,value];
const biomes=['Earthlike','Martian','Lunar','Desert','Tundra','Forest','Volcanic','Tropical','Barren rock','Snow & ice'];


function usePreference(key:string, fallback:boolean):[boolean,(value:boolean)=>void] {
  const [value,setValue]=useState(()=>{try{return JSON.parse(localStorage.getItem(`mapgen.ui.${key}`)??JSON.stringify(fallback));}catch{return fallback;}});
  return [value,(next:boolean)=>{setValue(next);try{localStorage.setItem(`mapgen.ui.${key}`,JSON.stringify(next));}catch{/* In-memory preference still works. */}}];
}

export function App(){
  const [state,setState]=useState(()=>hosted?initialState(maps):readState(maps));
  const [loading,setLoading]=useState(hosted);
  const [loadError,setLoadError]=useState(false);
  useEffect(()=>{if(!hosted)return;let active=true;loadRemote().then(next=>{if(active){try{const lang=localStorage.getItem('mapgen.ui.language');if(lang==='en'||lang==='ru')next.profile.language=lang;}catch{}setState(next);setLoading(false);}}).catch(()=>{if(active)setLoadError(true);});return()=>{active=false;};},[]);
  const language=state.profile.language==='ru'?'ru':'en';
  const t=(text:string)=>translate(language,text);
  useEffect(()=>{document.documentElement.lang=language;},[language]);
  const [page,setPage]=useState<'annotate'|'collection'|'review'>('annotate');
  const [profileOpen,setProfileOpen]=useState(false);
  const [skipped,setSkipped]=useState<string[]>([]);
  const [browse,setBrowse]=useState(false);
  const [pool,setPool]=useState('priority');
  const [search,setSearch]=useState('');
  const [collectionPage,setCollectionPage]=useState(1);
  const [selected,setSelected]=useState<string|null>(null);
  const [message,setMessage]=useState('');
  const [storageError,setStorageError]=useState('');
  const status=calibrationStatus(state);
  const priorityCount=state.settings.priorityIds?.length??maps.filter(m=>m.priority).length;
  const persist=(next:State)=>{if(hosted){setState(next);setStorageError('');return true;}try{localStorage.setItem(STORAGE_KEY,JSON.stringify(next));setState(next);setStorageError('');return true;}catch{setStorageError('Could not save on this device. Export your existing work before continuing.');return false;}};
  const current=selected?maps.find(m=>m.id===selected):selectMap(maps,state,skipped,browse,pool);
  const calibration=!browse && !selected && status.completed<state.settings.anchors.length;
  const priorityIds=new Set(state.settings.priorityIds??maps.filter(m=>m.priority).map(m=>m.id));
  const completed=new Set(state.submissions.filter(s=>s.phase==='collection'&&priorityIds.has(s.mapId)).map(s=>s.mapId)).size;
  const exportData=()=>downloadText('mapgen-annotations.json',JSON.stringify({schemaVersion:3,questionDefinitions:questions,exportedAt:new Date().toISOString(),...state,calibration:status},null,2),'application/json');
  const filteredMaps=maps.filter(m=>(pool==='all'||priorityIds.has(m.id))&&`${m.canonicalName} ${m.mapDir}`.toLowerCase().includes(search.toLowerCase()));
  const pageCount=Math.max(1,Math.ceil(filteredMaps.length/24));
  const activePage=Math.min(collectionPage,pageCount);
  const visibleMaps=filteredMaps.slice((activePage-1)*24,activePage*24);
  const saveProfile=async(profile:Profile)=>{try{const saved=hosted?await saveRemoteProfile(profile):{...profile,saved:true};if(persist({...state,profile:saved})){setProfileOpen(false);setMessage('Player profile saved.');}}catch{setStorageError('Could not save online. Your answers are still here. Please retry.');}};
  const saveReview=async(submission:Submission)=>{const saved=hosted?await saveRemoteReview(submission):submission;if(persist({...state,submissions:[...state.submissions.filter(s=>s.id!==saved.id),saved]})){setMessage(hosted?'Review saved online. Thank you!':'Review saved on this device. Thank you!');setSelected(null);setSkipped([]);}};
  const changeLanguage=(language:'en'|'ru')=>{try{localStorage.setItem('mapgen.ui.language',language);}catch{}persist({...state,profile:{...state.profile,language}});};
  if(loading)return <div className="empty" role={loadError?'alert':'status'}><h2>{t(loadError?'Could not connect to the collection server.':'Loading your reviews…')}</h2>{loadError&&<button className="button primary" onClick={()=>window.location.reload()}>{t('Retry')}</button>}</div>;
  return <LanguageContext.Provider value={language}><div className="app">
    <aside className="sidebar">
      <a className="brand" href="#" onClick={e=>{e.preventDefault();setPage('annotate');}}><span className="brand-icon"><Layers size={23}/></span><span>MAP<span className="brand-light">GEN</span><small>{t("COMMUNITY ATLAS")}</small></span></a>
      <div className="nav-label">{t("WORKSPACE")}</div>
      <nav aria-label={t("Main navigation")}>
        <button className={page==='annotate'?'nav-item active':'nav-item'} onClick={()=>setPage('annotate')}><Compass size={19}/>{t("Annotate maps")}<ChevronRight size={15}/></button>
        <button className={page==='collection'?'nav-item active':'nav-item'} onClick={()=>setPage('collection')}><MapIcon size={19}/>{t("Map collection")}<span className="nav-count">{maps.length.toLocaleString()}</span></button>
        {!hosted&&<button className={page==='review'?'nav-item active':'nav-item'} onClick={()=>setPage('review')}><ShieldCheck size={19}/>{t("Review setup")}</button>}
      </nav>
      <div className="campaign"><div className="eyebrow">{t("COLLECTION 01")}</div><h3>{t("Adaptive maps")}</h3><p>{t("Build a shared understanding of how our maps play.")}</p><div className="progress"><i style={{width:`${Math.min(100,completed/priorityCount*100)}%`}}/></div><div className="campaign-count"><strong>{completed}</strong> {t("annotated by you")} <span>/ {priorityCount}</span></div><small>{t(state.settings.priorityIds?'Curated priority collection':'Technical-audit candidates · provisional')}</small></div>
      <div className="sidebar-bottom"><span className="local-dot"/> {t(hosted?'Live collection':'Local review version')}<p>{t(hosted?'Submitted reviews are stored securely on the server.':'Responses stay in this browser.')}<br/>{t(hosted?'This browser remembers your anonymous session.':'Export them before switching devices.')}</p><button onClick={exportData}><Download size={15}/> {t("Export my work")}</button></div>
      <button className="profile-button" onClick={()=>setProfileOpen(true)}><span className="avatar">{state.profile.name?state.profile.name.slice(0,2).toUpperCase():'YOU'}</span><span><strong>{state.profile.name||t('Your player profile')}</strong><small>{state.profile.saved?`${state.profile.rating||t('Unrated')} · ${t(state.profile.ratingMode)}`:t('Add rating & experience')}</small></span><Settings2 size={16}/></button>
    </aside>
    <main>
      <header className="topbar"><span>{t("Community atlas")} <ChevronRight size={13}/> <strong>{t(page==='annotate'?'Map annotation':page==='collection'?'Map collection':'Review setup')}</strong></span><span className="review-badge"><span/> {t(hosted?'LIVE COLLECTION':'PRIVATE PREVIEW')}</span></header>
      {storageError&&<div className="error" role="alert">{t(storageError)}</div>}
      {message&&<div className="toast" role="status"><CheckCircle2 size={17}/>{t(message)}<button aria-label={t("Dismiss notification")} onClick={()=>setMessage('')}><X size={15}/></button></div>}
      {page==='annotate'&&<>
        <div className="page-heading"><div><div className="eyebrow">{t("YOUR EXPERIENCE. BETTER MAPS.")}</div><h1>{t("Put your map knowledge to work.")}</h1><p>{t("A few thoughtful answers are more useful than a complete guess.")}</p></div><div className="session-total"><strong>{state.submissions.length}</strong><span>{t("reviews saved")}</span></div></div>
        <div className="steps"><div className={state.profile.saved?'done':'current'}><span>{state.profile.saved?<Check size={13}/>:1}</span>{t("Player profile")}<button onClick={()=>setProfileOpen(true)}>{t(state.profile.saved?'Edit':'Set up')}</button></div><i/><div className={status.completed===6?'done':state.profile.saved?'current':''}><span>{status.completed===6?<Check size={13}/>:2}</span>{t("Calibration")} <small>{status.completed} / 6</small></div><i/><div className={status.completed===6?'current':''}><span>3</span>{t("Explore the collection")}</div></div>
        {!state.profile.saved&&<div className="notice"><Users size={19}/><div><strong>{t("Tell us a little about your FAF experience")}</strong><p>{t("Your rating, preferred modes, and familiarity give context to your answers.")}</p></div><button className="button light" onClick={()=>setProfileOpen(true)}>{t("Set up profile")} <ArrowRight size={16}/></button></div>}
        {browse&&status.completed<6&&<div className="notice"><Compass size={18}/><div>{t("Browsing the collection. Complete calibration before submitting collection reviews.")}</div><button className="text-button" onClick={()=>{setBrowse(false);setSelected(null);}}>{t("Return to calibration")}</button></div>}
        {current?<Annotation key={`${current.id}:${calibration}:${state.settings.revision}`} map={current} state={state} calibration={calibration} canSubmit={state.profile.saved&&(calibration||status.completed===6)} onProfile={()=>setProfileOpen(true)} onSubmit={saveReview} onSkip={()=>{if(calibration){setMessage('Unknown is already selected by default. Submit a partial review to continue calibration.');}else{setSkipped([...skipped,current.id]);setSelected(null);}}}/>:<div className="empty"><CheckCircle2 size={40}/><h2>{t("You’ve reached the end of this queue.")}</h2><p>{t("Continue with the wider collection or revisit skipped maps.")}</p><button className="button primary" onClick={()=>{setPool('all');setSkipped([]);}}>{t("Explore all maps")} <ArrowRight size={16}/></button></div>}
      </>}
      {page==='collection'&&<><div className="page-heading"><div><div className="eyebrow">{t("THE MAP LIBRARY")}</div><h1>{t("Every map has a story.")}</h1><p>{priorityCount} {t("priority candidates.")} {maps.length.toLocaleString()} {t("maps to explore.")}</p></div></div><div className="collection-tools"><label className="search"><span>{t("Find a map")}</span><input value={search} onChange={e=>{setSearch(e.target.value);setCollectionPage(1);}} placeholder={t("Search by map name or version…")}/></label><label>{t("Collection")}<select value={pool} onChange={e=>{setPool(e.target.value);setCollectionPage(1);}}><option value="priority">{t("Adaptive priority (")}{priorityCount})</option><option value="all">{t("All maps (")}{maps.length})</option></select></label></div><div className="map-grid">{visibleMaps.map(m=><button className="map-card" key={m.id} onClick={()=>{setSelected(m.id);setBrowse(true);setPage('annotate');}}><MapImage map={m}/><div><h3>{m.canonicalName}</h3><span>{fmt(m.sizeX===null?null:m.sizeX/51.2,' km')} <b>·</b> {fmt(m.playerCount)} {t("slots")}</span><ArrowUpRight size={17}/></div></button>)}</div><nav className="pagination" aria-label={t("Collection pages")}><button className="button ghost" disabled={activePage===1} onClick={()=>setCollectionPage(activePage-1)}>{t("Previous")}</button><span>{filteredMaps.length ? `${(activePage-1)*24+1}–${Math.min(activePage*24,filteredMaps.length)} ${t('of')} ${filteredMaps.length} ${t('maps')}`:t('No matching maps')}</span><label>{t("Page")} <select aria-label={t("Collection page")} value={activePage} onChange={e=>setCollectionPage(Number(e.target.value))}>{Array.from({length:pageCount},(_,i)=><option key={i} value={i+1}>{i+1} / {pageCount}</option>)}</select></label><button className="button ghost" disabled={activePage===pageCount} onClick={()=>setCollectionPage(activePage+1)}>{t("Next")}</button></nav></>}
      {!hosted&&page==='review'&&<Review state={state} persist={persist} exportData={exportData}/>}
      <footer><span>{t("MAPGEN / ANNOTATION LAB")}</span><span>{t("Human experience, grounded in map data.")}</span></footer>
    </main>
    {profileOpen&&<ProfileForm profile={state.profile} onClose={()=>setProfileOpen(false)} onSave={saveProfile} error={storageError} onLanguageChange={changeLanguage}/>}
  </div></LanguageContext.Provider>;
}

function MapImage({map}:{map:CatalogMap}){
  const t=useTranslation();
  const [failed,setFailed]=useState(false);
  return failed?<div className="image-missing"><MapIcon size={35}/><strong>{t("Vault preview unavailable")}</strong><span>{t("Use your map experience, or leave ratings as “Not sure”.")}</span></div>:<img className="map-image" src={vaultPreview(map)} alt={`${map.canonicalName} vault preview`} onError={()=>setFailed(true)}/>;
}

function Annotation({map,state,calibration,canSubmit,onSubmit,onSkip,onProfile}:{map:CatalogMap;state:State;calibration:boolean;canSubmit:boolean;onSubmit:(s:Submission)=>Promise<void>;onSkip:()=>void;onProfile:()=>void}){
  const t=useTranslation();
  const [answers,setAnswers]=useState<Record<string,Answer>>(defaultAnswers);
  const [familiarity,setFamiliarity]=useState('Preview');
  const anchor=calibration?state.settings.anchors.find(a=>a.mapId===map.id):undefined;
  const [configuration,setConfiguration]=useState(()=>defaultConfiguration(map));
  const [setup,setSetup]=useState(anchor?.setup||'');
  const [note,setNote]=useState('');
  const [tags,setTags]=useState<string[]>([]);
  const [traits,setTraits]=useState<string[]>([]);
  const [uniqueText,setUniqueText]=useState('');
  const [compact,setCompact]=usePreference('compact',false);
  const [biomeOpen,setBiomeOpen]=usePreference('biomeOpen',true);
  const [detailsOpen,setDetailsOpen]=usePreference('detailsOpen',false);
  const [suggestions,setSuggestions]=usePreference('suggestions',false);
  const [suggestionsSeen,setSuggestionsSeen]=useState(suggestions);
  const [zoom,setZoom]=useState(false);
  const [start]=useState(Date.now());
  const [submissionId]=useState(()=>crypto.randomUUID());
  const [saving,setSaving]=useState(false);
  const [saveError,setSaveError]=useState('');
  const inFlight=useRef(false);
  const answered=questions.filter(q=>typeof answers[q.id]==='number').length;
  const complete=isComplete(answers,tags);
  const submit=async()=>{if(inFlight.current)return;inFlight.current=true;setSaving(true);setSaveError('');try{await onSubmit({id:submissionId,respondentId:state.respondentId,mapId:map.id,mapVersion:map.version,scaleVersion:5,profile:{...state.profile},familiarity,configuration,setup:setup.trim()||'Not specified',answers,note,biomes:tags,uniqueTraits:traits,uniqueText,phase:calibration?'calibration':'collection',createdAt:new Date().toISOString(),secondsSpent:Math.round((Date.now()-start)/1000),suggestionsShown:suggestionsSeen,calibrationRevision:state.settings.revision});}catch(error){setSaveError(error instanceof Error?error.message:'Could not save online. Your answers are still here. Please retry.');}finally{inFlight.current=false;setSaving(false);}};
  const isReady=canSubmit && !saving && configuration.trim()!=='';
  const submitButton=<button className={`button ${complete?'primary':'partial'}`} disabled={!isReady} onClick={submit}>{t(saving?'Saving…':'Submit review')} <ArrowRight size={16}/></button>;
  const rating=(q:typeof questions[number],number:number)=><div className="rating-question" role="group" aria-label={t(q.title)} key={q.id}><div className="question-heading"><span className="question-index">{number}</span>{t(q.title)}<span className="category">{t(q.group)}</span></div><p>{t(q.help)}</p><div className="rating-options">{q.labels.map((label,index)=><button title={`${index+1} · ${t(label)}`} aria-label={`${t(q.title)}: ${index+1} — ${t(label)}`} aria-pressed={answers[q.id]===index+1} className={answers[q.id]===index+1?'selected':''} key={t(label)} onClick={()=>setAnswers({...answers,[q.id]:index+1})}><span>{index+1}</span><span className="rating-label">{t(label)}</span></button>)}</div><button className={answers[q.id]==='unknown'?'unknown selected':'unknown'} aria-label={`${t(q.title)}: ${t("Not sure")}`} aria-pressed={answers[q.id]==='unknown'} onClick={()=>setAnswers({...answers,[q.id]:'unknown'})}>{t("Not sure")}</button></div>;
  return <div className="workspace"><section className="map-column"><div className="map-title"><div><div className="eyebrow">{calibration?`${t('Calibration')} ${calibrationStatus(state).completed+1} / 6`:t('MAP EXPLORATION')}</div><h2>{map.canonicalName}</h2></div><span className="version">v{map.version||'—'}</span></div><div className="map-stage"><MapImage map={map}/><div className="map-toolbar"><span className="vault-badge">{t("FAF vault preview")}</span><button aria-label={t("Enlarge map")} onClick={()=>setZoom(true)}><Maximize2 size={17}/></button></div></div>
      <div className="data-heading"><h3>{t("From the map data")}</h3><span>{t("EXTRACTED")}</span></div><div className="metrics">{[['Player slots',fmt(map.playerCount)],['Map size',`${fmt(map.sizeX===null?null:map.sizeX/51.2)} × ${fmt(map.sizeZ===null?null:map.sizeZ/51.2)} km`],['Mass extractors',fmt(map.mexCount)],['Hydros',fmt(map.hydroCount)],['Initial reclaim',fmt(map.reclaimMass)],['Water coverage',fmt(map.waterPercent,'%')],['Buildable area',fmt(map.buildablePercent,'%')]].map(([label,value])=><div key={t(label)}><span>{t(label)}</span><strong>{value}</strong></div>)}</div><p className="data-note">{t("Counts describe the extracted layout. Adaptive options and active slots can change the playable setup. Initial reclaim is mass; “—” means unavailable.")}</p>
      <div className="suggestions"><div><Sparkles size={18}/><strong>{t("Data-based suggestions")}</strong><button onClick={()=>{setSuggestions(!suggestions);setSuggestionsSeen(true);}}>{t(suggestions?'Hide':'Reveal')}</button></div>{suggestions?<><div className="suggestion-chips">{suggestion(map).map(s=><span key={t(s.label)} title={t(s.reason)}>{t(s.label)}</span>)}</div>{suggestion(map).map(s=><p key={t(s.reason)}>{t(s.reason)}</p>)}<small>{t("Heuristic hints, not verified ratings.")}</small></>:<p>{t("Reveal hints from the extracted map data.")}</p>}</div>
    </section><section className={`annotation-panel ${compact?'compact':''}`}><div className="panel-heading"><div><span className="eyebrow">{t(calibration?'GETTING CALIBRATED':'YOUR PERSPECTIVE')}</span><h2>{t("How does this map play?")}</h2></div><span className="answer-count">{answered} / {questions.length}</span></div>
      <p className="intro">{t("1–5 ratings · 3 = average · Not sure is the default. Partial reviews are welcome.")}</p>
      <div className="context-fields configuration-context"><label>{t("Your experience with this map")}<select value={familiarity} onChange={e=>setFamiliarity(e.target.value)}>{familiarityOptions.map(x=><option key={x} value={x}>{t(x)}</option>)}</select></label><div role="group" aria-label={t("Game configuration")}><div className="configuration-label">{t("Game configuration")}</div><div className="chips configuration-options">{Array.from(new Set(['1v1','2v2','3v3','4v4','5v5','6v6','7v7','8v8','FFA','Unknown / preview only',defaultConfiguration(map)])).map(option=><button key={option} type="button" aria-pressed={configuration===option} className={configuration===option?'selected':''} onClick={()=>setConfiguration(option)}>{t(option)}</button>)}<button type="button" className={`configuration-flexible ${configuration==='Multiple configurations'?'selected':''}`} aria-pressed={configuration==='Multiple configurations'} onClick={()=>setConfiguration('Multiple configurations')}>{t("This map plays well with different configurations")}</button></div></div></div>
      {saveError&&<p className="error" role="alert">{t(saveError)}</p>}
      <div className="top-submit"><button className="button ghost" disabled={saving} onClick={onSkip}>{t("Skip map")}</button>{submitButton}</div>
      <div className="question-list">
        {rating(questions[0],-1)}
        <section className="unique-traits"><h3><span className="question-index">0</span> {t("Map-specific unique traits")} <small>{t("optional")}</small></h3><p>{t("Suggested from map data. Toggle any that fit, or describe something else.")}</p><div className="chips">{uniqueSuggestions(map).map(trait=><button key={t(trait)} aria-pressed={traits.includes(trait)} className={traits.includes(trait)?'selected':''} onClick={()=>setTraits(toggle(traits,trait))}>{t(trait)}</button>)}</div><label><span className="sr-only">{t("Unique traits description")}</span><textarea aria-label={t("Unique traits description")} value={uniqueText} maxLength={1200} onChange={e=>setUniqueText(e.target.value)} placeholder={t("What makes this particular map different?")}/></label></section>
        {questions.slice(1).map((q,index)=>rating(q,index+1))}
      </div>
      <details className="biome-details" open={biomeOpen} onToggle={e=>setBiomeOpen(e.currentTarget.open)}><summary>{t("17 · Biome")} <span>{tags.length?tags.map(t).join(', '):t('Not sure')}</span></summary><p>{t("Choose multiple tags for mixed environments.")}</p><div className="chips"><button className={!tags.length?'selected':''} aria-pressed={!tags.length} onClick={()=>setTags([])}>{t("Not sure")}</button>{biomes.map(tag=><button aria-pressed={tags.includes(tag)} className={tags.includes(tag)?'selected':''} key={t(tag)} onClick={()=>setTags(toggle(tags,tag))}>{t(tag)}</button>)}</div></details>
      <details className="extended-details" open={detailsOpen} onToggle={e=>setDetailsOpen(e.currentTarget.open)}><summary>{t("Extended options & notes")}</summary><label className="setup-field">{t("Spawns & adaptive settings")} <span>{t("optional")}</span><input value={setup} onChange={e=>setSetup(e.target.value)} placeholder={t("e.g. standard positions, default resources")}/></label><label className="note">{t("Anything else?")} <span>{t("optional")}</span><textarea value={note} onChange={e=>setNote(e.target.value)} maxLength={1200} placeholder={t("Additional context for your review…")}/></label></details>
      <div className="submit-area"><div><span><ShieldCheck size={14}/> {t(hosted?'Saved online after submission':'Saved on this device')}</span><small>{!state.profile.saved?<button className="text-button" onClick={onProfile}>{t("Complete your player profile first")}</button>:!canSubmit?t('Finish the six calibration maps first'):complete?t('All ratings and biome answered.'):t('Some answers are Not sure. You can still submit.')}</small></div><div><button className="button ghost" disabled={saving} onClick={onSkip}>{t("Skip map")}</button>{submitButton}</div></div>
      <div className="view-toggle" role="group" aria-label={t("Question display")}><button aria-pressed={!compact} className={!compact?'selected':''} onClick={()=>setCompact(false)}>{t("Detailed questions")}</button><button aria-pressed={compact} className={compact?'selected':''} onClick={()=>setCompact(true)}>{t("Extreme compact")}</button></div>
    </section>{zoom&&<div className="modal-backdrop" onClick={()=>setZoom(false)}><section className="zoom-modal" role="dialog" aria-modal="true" aria-label={t("Enlarged map")}><button autoFocus className="close" aria-label={t("Close enlarged map")} onClick={()=>setZoom(false)}><X/></button><MapImage map={map}/></section></div>}</div>;
}

function ProfileForm({profile,onSave,onClose,onLanguageChange,error}:{error:string;profile:Profile;onSave:(p:Profile)=>Promise<void>;onClose:()=>void;onLanguageChange:(language:'en'|'ru')=>void}){
  const t=useTranslation();
  const [draft,setDraft]=useState(profile);
  const [savingProfile,setSavingProfile]=useState(false);
  const formRef=useRef<HTMLFormElement>(null);
  useEffect(()=>{
    const previous=document.activeElement as HTMLElement|null;
    const form=formRef.current;
    const handle=(event:KeyboardEvent)=>{
      if(event.key==='Escape'){event.preventDefault();onClose();}
      if(event.key==='Tab'&&form){
        const controls=Array.from(form.querySelectorAll<HTMLElement>('button:not(:disabled),input,select,textarea'));
        const first=controls[0],last=controls[controls.length-1];
        if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}
        else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}
      }
    };
    document.addEventListener('keydown',handle);
    return ()=>{document.removeEventListener('keydown',handle);previous?.focus();};
  },[onClose]);
  return <div className="modal-backdrop"><form ref={formRef} className="profile-modal" role="dialog" aria-modal="true" aria-labelledby="profile-title" onSubmit={async e=>{e.preventDefault();if(savingProfile)return;setSavingProfile(true);try{await onSave(draft);}finally{setSavingProfile(false);}}}><button type="button" className="close" aria-label={t("Close profile")} onClick={onClose}><X size={20}/></button><span className="modal-icon"><Users size={25}/></span><div className="eyebrow">{t("THE PLAYER BEHIND THE PERSPECTIVE")}</div><div className="language-picker" role="group" aria-label="Language / Язык"><span>Language / Язык</span>{(['en','ru'] as const).map(language=><button type="button" key={language} aria-pressed={(draft.language||'en')===language} className={(draft.language||'en')===language?'selected':''} onClick={()=>{setDraft({...draft,language});onLanguageChange(language);}}>{language.toUpperCase()}</button>)}</div>{error&&<p className="error" role="alert">{t(error)}</p>}<h2 id="profile-title">{t("Your FAF experience")}</h2><p>{t("Your preferences provide context. They don’t make your opinion right or wrong.")}</p><label>{t("FAF name")} <span>{t("optional")}</span><input autoFocus value={draft.name} maxLength={60} onChange={e=>setDraft({...draft,name:e.target.value})} placeholder={t("Commander name")}/></label><div className="context-fields"><label>{t("Current rating")} <span>{t("optional")}</span><input type="number" min="-1000" max="5000" value={draft.rating} onChange={e=>setDraft({...draft,rating:e.target.value})} placeholder={t("Unrated / prefer not to say")}/></label><label>{t("Rating leaderboard")}<select value={draft.ratingMode} onChange={e=>setDraft({...draft,ratingMode:e.target.value})}>{['Global','1v1','2v2','3v3','4v4'].map(x=><option key={x} value={x}>{t(x)}</option>)}</select></label></div><label>{t("How long have you played?")} <select required value={draft.experience} onChange={e=>setDraft({...draft,experience:e.target.value})}><option value="" disabled>{t("Select experience")}</option>{['Less than 6 months','6–12 months','1–3 years','3–5 years','5+ years'].map(x=><option key={x} value={x}>{t(x)}</option>)}</select></label><label>{t("What do you usually play?")}</label><div className="chips">{modes.map(mode=><button type="button" key={t(mode)} className={draft.modes.includes(mode)?'selected':''} aria-pressed={draft.modes.includes(mode)} onClick={()=>setDraft({...draft,modes:toggle(draft.modes,mode)})}>{t(mode)}</button>)}</div><p className="data-note">{t("Select all that apply. Rating is self-reported; familiarity is recorded separately for every map.")}</p><button className="button primary full" disabled={savingProfile||!draft.experience||!draft.modes.length}>{t(savingProfile?'Saving…':'Save profile')} <ArrowRight size={17}/></button></form></div>;
}

function Review({state,persist,exportData}:{state:State;persist:(s:State)=>boolean;exportData:()=>void}){
  const t=useTranslation();
  const [settings,setSettings]=useState(state.settings);
  const [priorityText,setPriorityText]=useState(state.settings.priorityIds?.map(id=>maps.find(m=>m.id===id)?.mapDir||id).join('\n')||'');
  const [feedback,setFeedback]=useState('');
  const status=calibrationStatus(state);
  const patchAnchor=(index:number,patch:Partial<typeof settings.anchors[number]>)=>setSettings({...settings,anchors:settings.anchors.map((a,i)=>i===index?{...a,...patch}:a)});
  const save=()=>{
    if(new Set(settings.anchors.map(a=>a.mapId)).size!==6){setFeedback('Choose six different maps.');return;}
    const names=priorityText.split('\n').map(s=>s.trim()).filter(Boolean);
    const ids=names.map(name=>maps.find(m=>m.mapDir===name||m.id===name)?.id);
    if(ids.some(id=>!id)){setFeedback('Some priority maps were not found. Use exact folder names from the catalog.');return;}
    if(persist({...state,settings:{...settings,priorityIds:names.length?[...new Set(ids as string[])]:null,revision:new Date().toISOString()}}))setFeedback('Setup saved. Calibration restarts under this reference revision; previous answers are preserved.');
  };
  const exportCsv=()=>{const rows=state.submissions.flatMap(s=>Object.entries(s.answers).map(([questionId,value])=>({submissionId:s.id,respondentId:s.respondentId,mapId:s.mapId,mapVersion:s.mapVersion,phase:s.phase,scaleVersion:s.scaleVersion??4,questionId,value,uniqueTraits:(s.uniqueTraits??[]).join('|'),uniqueText:s.uniqueText??'',configuration:s.configuration,setup:s.setup,familiarity:s.familiarity,rating:s.profile.rating,ratingMode:s.profile.ratingMode,modes:s.profile.modes.join('|'),experience:s.profile.experience,note:s.note,biomes:s.biomes.join('|'),createdAt:s.createdAt,suggestionsShown:s.suggestionsShown,calibrationRevision:s.calibrationRevision})));downloadText('mapgen-answers.csv',toCsv(rows),'text/csv');};
  return <><div className="page-heading"><div><div className="eyebrow">{t("OWNER REVIEW · LOCAL ONLY")}</div><h1>{t("Set the reference, then collect.")}</h1><p>{t("Six calibration maps. Expert ranges. A focused priority collection.")}</p></div><button className="button light" onClick={exportData}><Download size={16}/>{t("Export JSON")}</button></div><div className="review-summary"><ShieldCheck size={26}/><div><h3>{t(status.status)}</h3><p>{status.completed} {t("/ 6 calibration maps ·")} {status.comparisons} {t("comparable answers ·")} {status.disagreements} {t("outside reference ranges")}</p></div></div><div className="notice"><Flag size={20}/><div><strong>{t("References need your review")}</strong><p>{t("Five positive maps and Astro Crater Battles as your negative quality reference. Low quality does not imply low land relevance, eco safety, or defensive strength. No automatic bans.")}</p></div></div><div className="reference-grid">{settings.anchors.map((a,index)=><section className="reference-card" key={index}><div className="eyebrow">{`${String(index+1).padStart(2,'0')} / ${t(index===5?'NEGATIVE QUALITY REFERENCE':'POSITIVE REFERENCE')}`}</div><label>{t("Exact map version")}<select value={a.mapId} onChange={e=>patchAnchor(index,{mapId:e.target.value,reference:{}})}>{maps.filter(m=>m.id===a.mapId||m.mapDir.toLowerCase().includes(anchorFolders[index].split('.')[0].replace('adaptive_','').replace('_-_faf_version','').split('_').slice(0,2).join('_'))).map(m=><option value={m.id} key={m.id}>{m.canonicalName} · {m.mapDir}</option>)}</select></label><div className="context-fields"><label>{t("Configuration")}<input placeholder={t("e.g. 4v4")} value={a.configuration} onChange={e=>patchAnchor(index,{configuration:e.target.value})}/></label><label>{t("Spawns / settings")}<input placeholder={t("Default slots & resources")} value={a.setup} onChange={e=>patchAnchor(index,{setup:e.target.value})}/></label></div><details><summary>{t("Expert answer ranges")} <span>{Object.keys(a.reference).length} {t("set")}</span></summary><p className="data-note">{t("Choose an acceptable range for at least three traits. Unset traits are not checked.")}</p>{questions.map(q=><div className="reference-row" key={q.id}><label>{t(q.title)}</label><select aria-label={`${t(q.title)} minimum for reference ${index+1}`} value={a.reference[q.id]?.min??''} onChange={e=>{const next={...a.reference};if(e.target.value==='')delete next[q.id];else next[q.id]={min:Number(e.target.value),max:Math.max(Number(e.target.value),next[q.id]?.max??Number(e.target.value))};patchAnchor(index,{reference:next});}}><option value="">{t("Not set")}</option>{q.labels.map((l,i)=><option value={i+1} key={l}>{i+1} · {t(l)}</option>)}</select><select aria-label={`${t(q.title)} maximum for reference ${index+1}`} disabled={!a.reference[q.id]} value={a.reference[q.id]?.max??''} onChange={e=>patchAnchor(index,{reference:{...a.reference,[q.id]:{min:Math.min(a.reference[q.id].min,Number(e.target.value)),max:Number(e.target.value)}}})}><option value="" disabled>{t("To")}</option>{q.labels.map((l,i)=><option value={i+1} key={l}>{i+1} · {t(l)}</option>)}</select></div>)}</details></section>)}</div><section className="settings-card"><h2>{t("Priority collection")}</h2><p>{t("Currently using 429 adaptive maps with a “ready” technical audit. This does not establish gameplay quality. Paste your curated list to replace it.")}</p><label>{t("Exact map folder names, one per line")}<textarea value={priorityText} onChange={e=>setPriorityText(e.target.value)} placeholder={t("Leave empty to use the provisional adaptive collection")}/></label><div className="action-row"><button className="button primary" onClick={save}>{t("Save review setup")} <Check size={17}/></button><button className="button light" onClick={exportCsv}><Download size={16}/>{t("Export answers CSV")}</button></div><p role="status">{t(feedback)}</p></section><section className="settings-card"><h3>{t("How review flags work")}</h3><p>{t("Calibration remains unscored until every map has a configuration, setup, and at least three expert reference ranges. After at least ten comparable answers, repeated disagreements across two or more maps can flag the profile for review. “Not sure” is missing evidence, not a wrong answer. Flags never delete responses.")}</p><p>{t("Rating, preferred modes, and familiarity are preserved with each submission. Weighting is deliberately deferred until we review the rubric. This local version has no shared database or verified player identity.")}</p></section></>;
}
