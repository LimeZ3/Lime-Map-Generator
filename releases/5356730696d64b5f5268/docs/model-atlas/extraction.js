/* A visible daily checklist generated from the authoritative extraction queue. */
projectViews.extracts = () => {
 const queue=window.MAPGEN_EXTRACTION_WORK;
 if(!queue)return '<h1>Extraction checklist</h1><p>The saved work queue is unavailable.</p>';
 const tasks=queue.tasks,next=tasks.find(t=>t.id===queue.next_task);
 const finished=tasks.filter(t=>t.checklist_state==='finished');
 const planned=tasks.filter(t=>t.checklist_state==='planned');
 const deferred=tasks.filter(t=>t.checklist_state==='deferred');
 const longTerm=tasks.filter(t=>t.checklist_state==='long_term');
 const outside=tasks.filter(t=>t.checklist_state==='out_of_scope');
 const legacyTitles={'EXTRACT-06':'Named 10x10 km dataset release and non-square classes','EXTRACT-07':'Dataset-wide multi-axis/radial symmetry and model encoding'};
 const slug=s=>s.toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'').slice(0,150)||'section';
 const taskKey=t=>'extracts:section:'+slug(t.id+' · '+(legacyTitles[t.id]||t.title));
 const doc=p=>'../'+p.replace(/^docs\//,'');
 function status(t){
  return {finished:'Finished',planned:'Planned · not started',deferred:'Deferred',long_term:'Long-term · nice to have',out_of_scope:'Out of scope'}[t.checklist_state]||'Status not recorded';
 }
 const card=t=>`<article class="project-card" id="${h(t.id)}" data-review-key="${h(taskKey(t))}" data-review-route="extracts/section/${h(t.id)}"><span class="status ${t.checklist_state==='finished'?'approved':'planned'}">${h(status(t))}</span><h3>${h(t.id)} · ${h(t.title)}</h3><p>${h(t.summary||'')}</p>${t.steps?.length?`<ul>${t.steps.map(s=>`<li><strong>${h(s.id)}</strong> (${h(s.status==='finished'?'Finished':s.id==='EXTRACT-06a'?'Deferred · no non-square maps': 'Postponed')}): ${h(s.requirement)}</li>`).join('')}</ul>`:''}<div class="links">${link(doc(t.methods||t.doc),'Task notes and evidence')}</div></article>`;
 const section=(title,items,legacyTitle=title)=>items.length?`<section class="band"><h2 data-review-key="extracts:section:${h(slug(legacyTitle))}" data-review-route="extracts">${h(title)}</h2><div class="project-grid">${items.map(card).join('')}</div></section>`:'';
 return projectIntro('Daily project work queue','Extraction checklist','The current extraction plan, with completed data work separated from model integration and future research.')+
 `<div class="links">${link('../map-extraction-todos.md','Full extraction to-do list and notes')}${link('maps-data-gap-plan.md','Prioritized model-data plan')}</div>`+
 `<div class="note neutral"><strong>Updated ${h(queue.updated_on)}</strong><p>${finished.length} finished · ${planned.length} planned · ${deferred.length} deferred · ${longTerm.length} long-term · ${outside.length} outside scope.</p><p>Finalized selection: <strong>${h(queue.source_candidate.maps)} maps in ${h(queue.source_candidate.families)} families</strong> (${h(queue.source_candidate.train)} train / ${h(queue.source_candidate.validation)} validation candidates); ${h(queue.source_candidate.excluded)} excluded. Original extraction audit: ${h(queue.audit_population.maps)} maps. New numeric dataset release not yet rebuilt.</p><p>${h(queue.next_task_note)}</p></div>`+
 section('Finished extracts',finished,'Extracted foundations — integration remains')+
 section('Planned research — not started',planned,'Later implementation and research')+
 section('Deferred — rules or decisions needed',deferred,'Deferred, optional or outside current scope')+
 section('Long-term quality-of-life goals',longTerm)+
 section('Outside current scope',outside)+
 `<section class="band"><h2>Separate follow-up: model and dataset release integration</h2><p>These follow-ups do not reopen finished extracts and do not imply existing checkpoints already use the new fields.</p><div class="project-grid">${(queue.integration_followups||[]).map(t=>`<article class="project-card"><span class="status planned">Not completed</span><h3>${h(t.title)}</h3><p>${h(t.summary)}</p></article>`).join('')}</div></section>`;
};
