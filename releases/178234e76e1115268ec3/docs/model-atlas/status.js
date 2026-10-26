projectViews.status = () => {
 const p=window.MAPGEN_PROJECT_STATUS;
 return projectIntro('Project source of truth · recorded '+p.recorded_at,'MapGen project status',p.phase)+
 `<div class="links">${link(p.repository,'GitHub repository')}${link('../progress/2026-10-25-project-update.md','Progress report · 25 October')}${link('../map-extraction-todos.md','Maps extraction work queue')}</div>
 <div class="fact-row"><span><strong>${p.metrics.selected_trained_stages}</strong> selected trained stages</span><span><strong>${p.metrics.checkpoint_runs}</strong> checkpoint runs inventoried</span><span><strong>${p.metrics.curated_train} / ${p.metrics.curated_validation}</strong> train / validation</span></div>
 ${(p.milestones||[]).map(m=>`<section class="band milestone"><span class="status approved">Milestone achieved / ${h(m.achieved_on)}</span><h2>${h(m.title)}</h2><p><strong>${h(m.map_name)}</strong></p><blockquote>${h(m.assessment)}</blockquote><p>${h(m.meaning)}</p><div class="links">${link('../../'+m.doc,'Presentation and shareable export')}${link('../../'+m.receipt,'Frozen map receipt')}</div></section>`).join('')}
 <section class="band"><h2>Implemented work and collected data</h2><div class="project-grid">${p.completed.map(x=>`<article class="project-card"><h3>${h(x.title)}</h3><p>${h(x.text)}</p><p>${link('../../'+x.evidence,'Evidence / method')}</p></article>`).join('')}</div></section>
 <section class="band"><h2>What the results establish</h2><ul>${p.results.map(x=>`<li>${h(x)}</li>`).join('')}</ul></section>
 <section class="band"><h2>Experimental branches · saved state</h2>${p.runs.map(r=>`<article class="tool-row"><h3>${h(r.title)}</h3><span class="status experimental">${h(r.state)}</span><p>${h(r.stage||'')}</p>${(r.stages||[]).length?`<ul>${(r.stages||[]).map(s=>`<li>${h(s.id)}: ${h(s.status)}${s.step?' · update '+h(s.step):''}</li>`).join('')}</ul>`:''}<p>${link('../../'+r.evidence,'Branch evidence')}</p></article>`).join('')}<p class="small muted">Saved supervisor state, not a live process-health assertion.</p></section>
 <section class="band"><h2>Next work and known limitations</h2><ul>${p.planned.map(x=>`<li>${h(x)}</li>`).join('')}</ul></section>
 <div class="note neutral"><strong>How this page stays current</strong><p>${h(p.update_contract)}</p></div>`;
};
