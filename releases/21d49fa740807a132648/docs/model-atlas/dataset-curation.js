/* Shared owner-edited inclusion decisions and human symmetry hypotheses. */
(() => {
 const origin=window.MAPGEN_PORTAL_ORIGIN||'https://mapgen-project-atlas.elven-bowl-7506.chatgpt.site';
 const endpoint=origin+'/api/dataset-curation';
 const labels={unset:'Not suggested',none:'None / asymmetric',mirror_vertical:'Mirror · left/right',mirror_horizontal:'Mirror · top/bottom',mirror_both:'Mirrors · both axes',mirror_diagonal:'Mirror · diagonal ↘',mirror_antidiagonal:'Mirror · diagonal ↗',rotation_2:'Rotation · 180° (2-fold)',rotation_3:'Rotation · 120° (3-fold)',rotation_4:'Rotation · 90° (4-fold)',rotation_6:'Rotation · 60° (6-fold)',rotation_8:'Rotation · 45° (8-fold)',dihedral_3:'3-fold rotation + mirrors',dihedral_4:'4-fold rotation + mirrors',dihedral_6:'6-fold rotation + mirrors',dihedral_8:'8-fold rotation + mirrors',unsure:'Approximate / unsure'};
 let rows=new Map(),pending=new Map(),canEdit=false,authenticated=false,busy=false,loaded=false,requestSerial=0,notice='Loading shared dataset curation…';
 const escape=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const cohort=()=>window.MAPGEN_DATASETS?.cohort;
 function effective(map){return rows.get(map.key)||{key:map.key,decision:map.decision==='exclude'?'exclude':'keep',manualSymmetry:'unset',version:0,updatedAt:null};}
 const visual=map=>({...effective(map),...pending.get(map.key)});
 const editable=()=>canEdit&&!busy;
 function controls(map){const row=visual(map);return `<div class="dataset-curation" data-curation-key="${escape(map.key)}"><label class="dataset-keep"><input type="checkbox" data-curation-keep aria-label="Keep ${escape(map.name)} in dataset" ${row.decision==='keep'?'checked':''} ${editable()?'':'disabled'}><span data-curation-label>${row.decision==='keep'?'Kept':'Excluded'}</span></label><label class="dataset-manual">Manual symmetry suggestion<select data-curation-symmetry aria-label="Manual symmetry suggestion: ${escape(map.name)}" ${editable()?'':'disabled'}>${options(row.manualSymmetry)}</select></label><small data-curation-saved>${busy?'Saving…':row.updatedAt?'Saved '+new Date(row.updatedAt).toLocaleString():row.decision==='exclude'?'Existing exclusion':'Default: Kept'}</small></div>`;}
 function options(value=''){return Object.entries(labels).map(([id,label])=>`<option value="${id}" ${id===value?'selected':''}>${escape(label)}</option>`).join('');}
 function paint(){
  for(const el of document.querySelectorAll('[data-curation-key]')){const map=window.MAPGEN_DATASETS?.maps.find(m=>m.key===el.dataset.curationKey);if(!map)continue;const row=visual(map),keep=el.querySelector('[data-curation-keep]'),select=el.querySelector('[data-curation-symmetry]');keep.checked=row.decision==='keep';keep.disabled=!editable();select.value=row.manualSymmetry;select.disabled=!editable();el.dataset.decision=row.decision;el.querySelector('[data-curation-label]').textContent=row.decision==='keep'?'Kept':'Excluded';el.querySelector('[data-curation-saved]').textContent=busy?'Saving…':row.updatedAt?'Saved '+new Date(row.updatedAt).toLocaleString():row.decision==='exclude'?'Existing exclusion':'Default: Kept';}
  for(const button of document.querySelectorAll('[data-bulk-decision]'))button.disabled=!editable()||button.dataset.visibleCount==='0';
  for(const span of document.querySelectorAll('[data-dataset-selection-key]')){const map=window.MAPGEN_DATASETS.maps.find(m=>m.key===span.dataset.datasetSelectionKey);if(map)span.textContent='Dataset selection: '+(effective(map).decision==='keep'?'Kept':'Excluded');}
  const banner=document.getElementById('dataset-curation-status');if(banner)banner.innerHTML=escape(notice)+(authenticated?'':` <a target="_top" href="${origin}/signin-with-chatgpt?return_to=${encodeURIComponent('/'+location.hash)}">Owner sign in</a>`);
 }
 function changed(){paint();document.dispatchEvent(new Event('mapgen-curation-change'));}
 async function refresh(){
  if(busy)return;
  const serial=++requestSerial;
  try{const response=await fetch(endpoint,{cache:'no-store',credentials:window.MAPGEN_PORTAL_ORIGIN?'same-origin':'omit'});if(!response.ok)throw Error('Shared dataset curation is unavailable; editing is disabled.');const data=await response.json();if(serial!==requestSerial)return;if(data.cohort!==cohort())throw Error('Dataset version changed. Use Check updates before editing.');rows=new Map(data.rows.map(r=>[r.key,r]));canEdit=!!data.canEdit&&!!window.MAPGEN_PORTAL_ORIGIN;authenticated=!!data.authenticated;loaded=true;notice=canEdit?'Owner editing enabled · decisions and manual suggestions are shared.':'Shared dataset selection · owner-only editing.';}
  catch(e){if(serial!==requestSerial)return;canEdit=false;notice=e.message;}
  changed();
 }
 async function update(keys,patch){
  if(!editable()||keys.length<1||keys.length>24)return;
  const maps=new Map(window.MAPGEN_DATASETS.maps.map(m=>[m.key,m]));
  const updates=keys.map(key=>({key,...patch,expectedVersion:effective(maps.get(key)).version}));
  ++requestSerial;pending=new Map(keys.map(key=>[key,patch]));busy=true;notice=`Saving ${keys.length} map${keys.length===1?'':'s'}…`;paint();
  try{const response=await fetch(endpoint,{method:'PUT',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({cohort:cohort(),updates})});const data=await response.json();if(data.rows)rows=new Map(data.rows.map(r=>[r.key,r]));if(!response.ok){if(response.status===401||response.status===403)canEdit=false;throw Error(data.error||'Dataset changes could not be saved.');}notice=`Saved ${data.updated} map${data.updated===1?'':'s'}.`;}
  catch(e){notice=e.message;}
  finally{busy=false;pending.clear();changed();}
 }
 document.addEventListener('change',event=>{const control=event.target.closest('[data-curation-key]');if(!control)return;const key=control.dataset.curationKey;if(event.target.matches('[data-curation-keep]'))update([key],{decision:event.target.checked?'keep':'exclude'});if(event.target.matches('[data-curation-symmetry]'))update([key],{manualSymmetry:event.target.value});});
 window.atlasDatasetCuration={effective,controls,options,labels,update,paint,refresh,editable,selectionUrl:endpoint+'?format=selection',get loaded(){return loaded;}};
 refresh();setInterval(()=>{if(!document.hidden)refresh();},60000);document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
})();
