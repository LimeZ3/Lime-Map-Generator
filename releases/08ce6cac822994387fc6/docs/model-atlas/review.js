/* Shared human review judgements; separate from model validation and task receipts. */
(() => {
  const labels={unflagged:'Unflagged',complete:'Complete',some_work:'Needs some work',far_from_done:'Far from done'};
  const origin=window.MAPGEN_PORTAL_ORIGIN||'https://mapgen-project-atlas.elven-bowl-7506.chatgpt.site';
  const endpoint=origin+'/api/review-flags';
  let flags=new Map(),canEdit=false,authenticated=false,loaded=false,error='',currentRoute='';
  const widgets=new Set();
  const slug=s=>s.toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'').slice(0,150)||'section';
  const escape=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function authLink(){return origin+'/signin-with-chatgpt?return_to='+encodeURIComponent('/#'+(location.hash.slice(1)||'status'));}
  function paint(){
    for(const w of widgets){
      if(!w.host.isConnected){widgets.delete(w);continue;}
      const flag=flags.get(w.key),status=flag?.status||'unflagged';
      w.host.dataset.reviewStatus=status;w.select.value=status;w.select.disabled=!canEdit||w.saving;
      w.select.title=canEdit?'Set shared project review flag':'Shared project review flag · only the owner can edit';
      w.message.textContent=w.message.dataset.error|| (w.saving?'Saving…':flag?.updatedAt?'Saved '+new Date(flag.updatedAt).toLocaleDateString():'');
    }
    let panel=document.getElementById('review-summary');
    if(!panel){panel=document.createElement('section');panel.id='review-summary';panel.className='review-summary';document.querySelector('aside .display-controls')?.before(panel);}
    const active=[...flags.values()].filter(f=>f.status!=='unflagged');
    panel.innerHTML='<a href="#reviews">⚑ Project review flags</a><p>'+active.length+' flagged sections · '+(canEdit?'Owner editing enabled':authenticated?'Read only · owner account required':'Public read only')+'</p>'+(error?'<p role="status">'+escape(error)+'</p>':!loaded?'<p>Loading shared flags…</p>':'')+(!authenticated?'<a target="_top" href="'+escape(authLink())+'">Owner sign in with ChatGPT</a>':'');
    if(currentRoute==='reviews')reviewList();
  }
  async function refresh(){
    try{const response=await fetch(endpoint,{credentials:window.MAPGEN_PORTAL_ORIGIN?'same-origin':'omit',cache:'no-store'});if(!response.ok)throw Error();const data=await response.json();flags=new Map(data.flags.map(f=>[f.key,f]));canEdit=!!data.canEdit&&!!window.MAPGEN_PORTAL_ORIGIN;authenticated=!!data.authenticated;loaded=true;error='';}
    catch{error='Shared flags unavailable. Changes are disabled until reconnected.';canEdit=false;}
    paint();
  }
  function widget(host,key,title,route){
    const control=document.createElement('span');control.className='review-control';
    const select=document.createElement('select');select.setAttribute('aria-label','Review flag: '+title);
    for(const [value,label] of Object.entries(labels)){const option=document.createElement('option');option.value=value;option.textContent='⚑ '+label;select.append(option);}
    const message=document.createElement('small');message.className='review-save';message.setAttribute('role','status');control.append(select,message);host.append(control);
    const w={host,key,title,route,select,message,saving:false};widgets.add(w);
    select.addEventListener('change',async()=>{
      const status=select.value,expectedVersion=flags.get(key)?.version||0;w.saving=true;message.dataset.error='';paint();
      try{const response=await fetch(endpoint,{method:'PUT',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({key,title,route,status,expectedVersion})});const data=await response.json();if(!response.ok)throw Error(data.error||'Could not save flag.');flags.set(key,data.flag);}
      catch(e){message.dataset.error=e.message;await refresh();}
      finally{w.saving=false;paint();}
    });
  }
  function reviewList(){
    const list=document.getElementById('review-list');if(!list)return;
    const rank={far_from_done:0,some_work:1,complete:2};
    const active=[...flags.values()].filter(f=>f.status!=='unflagged').sort((a,b)=>rank[a.status]-rank[b.status]||a.title.localeCompare(b.title));
    list.replaceChildren();
    if(!active.length){list.textContent=loaded?'No sections flagged yet. Open any atlas section to set its review flag.':'Loading shared flags…';return;}
    for(const f of active){const row=document.createElement('article');row.className='review-list-row';const a=document.createElement('a');a.href='#'+f.route;a.textContent=f.title;row.append(a);widget(row,f.key,f.title,f.route);list.append(row);}
    // Paint new list widgets without rebuilding the list recursively.
    for(const w of widgets){if(w.host.isConnected){const status=flags.get(w.key)?.status||'unflagged';w.host.dataset.reviewStatus=status;w.select.value=status;w.select.disabled=!canEdit||w.saving;}}
  }
  window.attachAtlasReview=route=>{
    currentRoute=route;
    if(route!=='reviews'){
      const duplicates=new Map();
      for(const heading of document.querySelectorAll('#main h1,#main h2,#main h3')){
        const title=heading.textContent.trim(),layer=heading.closest('.layer-section[id]');
        let key,link=route;
        if(layer){key='layers:'+layer.id;link='layers/'+layer.id.replace(/^layer-/,'');}
        else if(heading.tagName==='H1')key='page:'+route;
        else {const base=slug(title),count=(duplicates.get(base)||0)+1;duplicates.set(base,count);key=route+':section:'+base+(count>1?'-'+count:'');heading.id=heading.id||'review-'+slug(key);link=route+'/section/'+heading.id;}
        const host=document.createElement('div');host.className='review-heading';heading.before(host);host.append(heading);widget(host,key,title,link);
      }
    }
    paint();
  };
  projectViews.reviews=()=>'<h1>Project review flags</h1><p class="lede">Shared human review judgements. These flags track what you want to revisit; they do not replace model validation or recorded completion evidence.</p><p>Green: complete · Amber: needs some work · Red: far from done. Only the project owner can change flags.</p><button type="button" id="export-review-flags">Export shared flags</button><div id="review-list"></div>';
  document.addEventListener('click',event=>{if(event.target.id==='export-review-flags'){const blob=new Blob([JSON.stringify([...flags.values()],null,2)],{type:'application/json'});const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='mapgen-review-flags.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}});
  refresh();setInterval(()=>{if(!document.hidden)refresh();},60000);document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
})();
