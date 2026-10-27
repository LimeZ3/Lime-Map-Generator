/* A visible daily checklist generated from the authoritative extraction queue. */
projectViews.extracts = () => {
 const queue=window.MAPGEN_EXTRACTION_WORK;
 if(!queue)return '<h1>Extraction checklist</h1><p>The saved work queue is unavailable.</p>';
 const tasks=queue.tasks,next=tasks.find(t=>t.id===queue.next_task);
 const foundations=tasks.filter(t=>t!==next&&/complete|resolved/.test(t.status));
 const deferred=tasks.filter(t=>/deferred|postponed|low_priority|out_of_current_scope/.test(t.status));
 const later=tasks.filter(t=>t!==next&&!foundations.includes(t)&&!deferred.includes(t));
 const doc=p=>'../'+p.replace(/^docs\//,'');
 function status(t){
  if(t===next)return 'Next';
  if(/resolved/.test(t.status))return 'Pairs resolved; rebuilding pending';
  if(/complete/.test(t.status))return 'Extracted; model integration pending';
  if(/out_of_current_scope/.test(t.status))return 'Out of current scope';
  if(/postponed/.test(t.status))return 'Postponed';
  if(/low_priority/.test(t.status))return 'Optional, low priority';
  if(/deferred/.test(t.status))return 'Deferred: rules or decisions needed';
  if(/proposed/.test(t.status))return 'Proposed; implementation pending';
  return 'Planned';
 }
 const card=t=>`<article class="project-card" id="${h(t.id)}"><span class="status ${foundations.includes(t)?'approved':'planned'}">${h(status(t))}</span><h3>${h(t.id)} · ${h(t.title)}</h3>${t.steps?.length?`<ul>${t.steps.map(s=>`<li><strong>${h(s.id)}</strong>: ${h(s.requirement)}</li>`).join('')}</ul>`:''}<div class="links">${link(doc(t.methods||t.doc),'Task notes and evidence')}</div></article>`;
 const section=(title,items)=>items.length?`<section class="band"><h2>${h(title)}</h2><div class="project-grid">${items.map(card).join('')}</div></section>`:'';
 return projectIntro('Daily project work queue','Extraction checklist','The current extraction plan, with completed data work separated from model integration and future research.')+
 `<div class="links">${link('../map-extraction-todos.md','Full extraction to-do list and notes')}${link('maps-data-gap-plan.md','Prioritized model-data plan')}</div>`+
 section('Next item',next?[next]:[])+
 section('Extracted foundations — integration remains',foundations)+
 section('Later implementation and research',later)+
 section('Deferred, optional or outside current scope',deferred)+
 `<div class="note neutral"><strong>Before the next training release</strong><p>Apply accepted symmetry overrides and actual spawn pairs, rebuild affected scenario-dependent data, include slope where relevant, and freeze field readiness, source hashes, validity and family splits. A completed extraction does not mean an existing checkpoint uses that field.</p></div>`;
};
