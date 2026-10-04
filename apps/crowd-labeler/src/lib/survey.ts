export type CatalogMap = {
  id: string; mapDir: string; canonicalName: string; version: string; sizeX: number | null; sizeZ: number | null;
  playerCount: number | null; previewUrl: string | null; structuralPreviewUrl: string | null; hasPreview: boolean;
  inventorySource: string; priority: boolean; waterPercent: number | null; buildablePercent: number | null;
  mexCount: number | null; hydroCount: number | null; reclaimMass: number | null; texturePack: string;
  auditStatus: string; teamSuggestion: string;
};
export type Profile = { language?: 'en' | 'ru'; name: string; rating: string; ratingMode: string; experience: string; modes: string[]; saved: boolean };
export type Question = { id: string; title: string; help: string; labels: string[]; group: string };
const intensity = ['Very low','Low','Average','High','Very high'];
const quality = ['Very bad','Bad','Average','Good','Excellent'];
export const questions: Question[] = [
  {id:'unique',title:'This map is unique',help:'How distinctive is this map compared with other FAF maps?',labels:['Very common','Familiar','Average','Distinctive','Truly unique'],group:'Identity'},
  {id:'quality',title:'Gameplay quality',help:'How good is the gameplay, considering strategic depth and viable options?',labels:quality,group:'Quality'},
  {id:'beauty',title:'Visual appeal',help:'How attractive is the map, independently of your preferred play style?',labels:quality,group:'Appearance'},
  {id:'land',title:'Land',help:'How much do ground armies shape the outcome?',labels:intensity,group:'Combat'},
  {id:'air',title:'Air',help:'How much does air control shape the outcome?',labels:intensity,group:'Combat'},
  {id:'navy',title:'Navy',help:'How much do fleets shape the outcome? Consider useful routes and targets.',labels:intensity,group:'Combat'},
  {id:'pressure',title:'Early combat',help:'How important is combat during the opening and early T1 phase?',labels:intensity,group:'Combat'},
  {id:'midCombat',title:'Mid-term combat',help:'How important is fighting during the transition through T2 and T3?',labels:intensity,group:'Combat'},
  {id:'lateCombat',title:'Late-game combat',help:'How important is late-game fighting, including experimentals and strategic weapons?',labels:intensity,group:'Combat'},
  {id:'eco',title:'Eco safety',help:'How safely can a player invest in economy instead of military?',labels:['Very exposed','Exposed','Average','Safe','Very safe'],group:'Economy'},
  {id:'open',title:'Frontline openness',help:'How broad are the movement routes and opportunities to flank?',labels:['Very choked','Constrained','Average','Open','Very open'],group:'Layout'},
  {id:'expansion',title:'Expansion',help:'How strongly does taking new territory improve your position?',labels:intensity,group:'Economy'},
  {id:'drops',title:'Offensive drops',help:'How valuable is transporting units behind the frontline?',labels:intensity,group:'Gameplay'},
  {id:'build',title:'Main-base build space',help:'How much usable contiguous build space is available near the active spawns?',labels:['Cramped','Limited','Average','Spacious','Vast'],group:'Layout'},
  {id:'readable',title:'Terrain readability',help:'Does the appearance clearly communicate paths, water, and buildable terrain?',labels:quality,group:'Readability'},
  {id:'gameReadability',title:'Gameplay readability',help:'How easy is the map to understand for someone who has never played it?',labels:['Very confusing','Confusing','Average','Clear','Very clear'],group:'Readability'},
  {id:'roles',title:'Pre-defined roles',help:'How strongly do spawn positions prescribe roles such as frontline, air, navy, or eco?',labels:intensity,group:'Team play'},
];
export const defaultAnswers = (): Record<string,Answer> => Object.fromEntries(questions.map(q=>[q.id,'unknown']));
export function defaultConfiguration(map: CatalogMap) {
  if(!map.playerCount || map.playerCount<2) return 'Unknown / preview only';
  return map.playerCount%2===0 ? `${map.playerCount/2}v${map.playerCount/2}` : `${Math.floor(map.playerCount/2)}v${Math.ceil(map.playerCount/2)}`;
}
export function vaultPreview(map: CatalogMap) {
  return `https://content.faforever.com/maps/previews/large/${encodeURIComponent(map.mapDir.toLowerCase())}.png`;
}
export function uniqueSuggestions(map: CatalogMap) {
  return [ /adaptive/i.test(map.mapDir)?'Adaptive setup':null,
    map.waterPercent!==null&&map.waterPercent>=50?'Water-rich terrain':null,
    map.waterPercent!==null&&map.waterPercent<5?'Almost entirely land':null,
    map.buildablePercent!==null&&map.buildablePercent<25?'Limited buildable terrain':null,
    map.mexCount!==null&&map.playerCount&&map.mexCount/map.playerCount>=15?'Many mexes per slot':null,
    map.sizeX!==null&&map.sizeX>=1024?'Large battlefield':null,
  ].filter((x):x is string=>Boolean(x));
}
export function isComplete(answers: Record<string,Answer>, biomes:string[]) {
  return questions.every(q=>typeof answers[q.id]==='number' && Number(answers[q.id])>=1 && Number(answers[q.id])<=5) && biomes.length>0;
}
export const legacyValue = (n:number) => [1,2,4,5][n] ?? n;
export const modes = ['1v1 ladder','2v2 / 3v3','4v4+ team games','Seton’s','Gap / Astro','FFA','Co-op / AI'];
export const familiarityOptions = ['Preview','Watched replays','Played a few times','Know it well'];
export type Answer = number | 'unknown';
export type Submission = { scaleVersion?: number; uniqueTraits?: string[]; uniqueText?: string; id: string; respondentId: string; mapId: string; mapVersion: string; profile: Profile; familiarity: string; configuration: string; setup: string; answers: Record<string,Answer>; note: string; biomes: string[]; phase: 'calibration'|'collection'; createdAt: string; secondsSpent: number; suggestionsShown: boolean; calibrationRevision: string };
export type Anchor = { mapId: string; configuration: string; setup: string; reference: Record<string,{min:number;max:number}> };
export type Settings = { scaleVersion?: number; anchors: Anchor[]; priorityIds: string[] | null; revision: string };
export type State = { respondentId: string; profile: Profile; submissions: Submission[]; settings: Settings };
export const anchorFolders = ['setons_clutch_-_faf_version.v0004','dualgap_adaptive.v0014','adaptive_canis_river.v0002','adaptive_diversity.v0002','adaptive_twin_rivers.v0002','astro_crater_battles'];
export function initialState(maps: CatalogMap[]): State {
  return {respondentId:crypto.randomUUID(),profile:{name:'',rating:'',ratingMode:'Global',experience:'',modes:[],saved:false},submissions:[],settings:{scaleVersion:5,
    anchors:anchorFolders.map((folder,index)=>({mapId:maps.find(m=>m.mapDir===folder)?.id??'',configuration:'',setup:'',reference:index===5?{quality:{min:1,max:1}}:{quality:{min:4,max:5}}})),priorityIds:null,revision:'initial'}};
}
export const STORAGE_KEY = 'mapgen.annotation-review.v2' + (typeof window !== 'undefined' && new URLSearchParams(window.location.search).has('qa') ? '.qa' : '');
export function readState(maps: CatalogMap[]): State {
  try { const raw=localStorage.getItem(STORAGE_KEY); if(raw){ const s=JSON.parse(raw); if(s.profile && Array.isArray(s.submissions) && s.settings?.anchors?.length===6) return {...s,respondentId:s.respondentId||crypto.randomUUID(),settings:s.settings.scaleVersion===5?s.settings:{...s.settings,scaleVersion:5,anchors:s.settings.anchors.map((a:Anchor)=>({...a,reference:Object.fromEntries(Object.entries(a.reference).map(([k,v])=>[k,{min:legacyValue(v.min),max:legacyValue(v.max)}]))}))}}; } } catch { /* Keep malformed storage untouched until the next explicit save. */ }
  return initialState(maps);
}
export function calibrationStatus(state: State) {
  const completed = state.settings.anchors.filter(a=>state.submissions.some(s=>s.phase==='calibration' && s.mapId===a.mapId && s.calibrationRevision===state.settings.revision));
  let comparisons=0, disagreements=0, mapsDisagreed=0;
  for(const anchor of state.settings.anchors){
    const s=state.submissions.find(s=>s.phase==='calibration' && s.mapId===anchor.mapId && s.calibrationRevision===state.settings.revision);
    let mismatches=0;
    if(s) for(const [key, range] of Object.entries(anchor.reference)){
      const stored=s.answers[key]; if(typeof stored!=='number') continue;
      const answer=s.scaleVersion===5?stored:legacyValue(stored);
      comparisons++; if(answer<range.min || answer>range.max){disagreements++;mismatches++;}
    }
    if(mismatches>=2) mapsDisagreed++;
  }
  const referenceReady=state.settings.anchors.every(a=>a.configuration.trim() && a.setup.trim() && Object.keys(a.reference).length>=3);
  return {completed:completed.length,comparisons,disagreements,referenceReady,
    status:completed.length<state.settings.anchors.length?'In progress':!referenceReady?'Awaiting expert references':comparisons<10?'Insufficient evidence':mapsDisagreed>=2 && disagreements/comparisons>0.5?'Review recommended':'No flag detected'};
}
export function selectMap(maps: CatalogMap[], state: State, skipped: string[], browse: boolean, collection: string) {
  const own = state.submissions;
  if(!browse){
    const anchor=state.settings.anchors.find(a=>!own.some(s=>s.phase==='calibration' && s.mapId===a.mapId && s.calibrationRevision===state.settings.revision));
    if(anchor) return maps.find(m=>m.id===anchor.mapId);
  }
  const eligible=maps.filter(m=>!skipped.includes(m.id) && !own.some(s=>s.phase==='collection' && s.mapId===m.id));
  const priority=(m:CatalogMap)=>state.settings.priorityIds?state.settings.priorityIds.includes(m.id):m.priority;
  return eligible.filter(m=>collection==='all'||priority(m)).sort((a,b)=>Number(priority(b))-Number(priority(a)) || a.canonicalName.localeCompare(b.canonicalName))[0];
}
export function batchFor(_map: CatalogMap, _submissions: Submission[], _calibration: boolean) {
  return questions;
}
export function suggestion(map: CatalogMap) {
  const water=map.waterPercent;
  return [water===null?null:{label:water<5?'Mostly dry':water<30?'Some water':water<65?'Mixed land & water':'Water-rich',reason:`${water.toFixed(1)}% water coverage`},
    map.mexCount!==null && map.playerCount?{label:`${(map.mexCount/map.playerCount).toFixed(1)} mex / slot`,reason:'Total mexes ÷ available slots; adaptive settings can change this'}:null,
    map.texturePack?{label:map.texturePack,reason:'Texture pack detected in map data; biome is unconfirmed'}:null].filter((s):s is {label:string;reason:string}=>s!==null);
}
