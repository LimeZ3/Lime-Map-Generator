'use strict';
const atlas = window.MAPGEN_ATLAS;
const h = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const icon = name => `<i data-lucide="${h(name)}" aria-hidden="true"></i>`;
const byId = id => atlas.models.find(model => model.id === id);
const toolById = id => atlas.tools.find(tool => tool.id === id);
const rel = path => '../../'+path;
const link = (url, text) => `<a href="${h(url)}" target="_blank" rel="noopener">${h(text)} ${icon('external-link')}</a>`;
const down = label => `<div class="down">${icon('arrow-down')}<span>${h(label || '')}</span></div>`;

function node(id, tool = false, text = '') {
  const item = tool ? toolById(id) : byId(id);
  const planned = item.status === 'planned';
  const status = !tool && !planned ? (item.short_status || item.status_text) : null;
  return `<button type="button" class="flow-node ${tool?'tool ':''}${planned?'planned':''}" data-route="${tool?'tool:':''}${h(id)}">${icon(item.icon)}<span><span class="tag">${planned?'Planned ':''}${tool?'Tool / rules':'Neural model'}</span><strong>${h(item.title || item.name)}</strong><small>${h(text || (tool?item.output:item.status_text))}</small>${status?`<span class="node-state">${h(status)}</span>`:''}</span></button>`;
}

function assetGallery(ids) {
  if (!ids?.length) return '';
  return `<div class="gallery">${ids.map(id => {
    const a = atlas.assets[id];
    const context = /^(source_|texture_|slope_example$)/.test(id)?'generated/comparisons/8553_17709-vault.png':null;
    return `<figure class="channel"><a class="${context?'contextual-layer':''}" href="${h(a.image)}" target="_blank" rel="noopener">${context?`<img class="vault-context" src="${h(context)}" alt="" aria-hidden="true">`:''}<img src="${h(a.image)}" class="${context?'tensor-image ':''}${a.shape.length>2 && a.title.includes('palette')?'wide':''}" alt="${h(a.title)}" loading="lazy"></a><figcaption><h4>${h(a.title)}</h4><span class="shape">${h(a.shape.join(' x '))}</span><span class="legend-text">${h(a.legend)}</span>${a.minimum===null?'':`<span class="channel-meta">Values ${a.minimum.toPrecision(3)} to ${a.maximum.toPrecision(3)}</span>`}<span class="field-source"><code>${h(a.array)}${a.channel===null?'':`[${a.channel}]`}</code>${a.source?` · <a href="${h(a.source)}" target="_blank" rel="noopener">NPZ / source</a>`:''}</span>${a.note?`<span class="legend-text">${h(a.note)}</span>`:''}</figcaption></figure>`;
  }).join('')}</div>`;
}

// Default source illustrations use Setons. Other figures retain their original provenance behind a disclosure.
function assets(ids) {
  if(!ids?.length) return '';
  const reference = ids.filter(id=>id.startsWith('source_') || id.startsWith('texture_') || id==='slope_example');
  const archived = ids.filter(id=>!reference.includes(id));
  return assetGallery(reference)+(archived.length?`<details class="saved-experiment"><summary>Original saved experiment / training figures (${archived.length})</summary><p class="small muted">These figures retain their original run or training-map identity. They are not Setons predictions.</p>${assetGallery(archived)}</details>`:'');
}

function jointExperimentOverview() {
  return (atlas.experiments||[]).map(e=>`<section class="band"><h2>${h(e.title)}</h2><p>${h(e.run_status)}. Separate experiment; ${h(e.cohort)}.</p><div class="mini-chain"><div class="flow-node tool"><span><strong>Gaussian noise + 12 ratings</strong><small>No source spatial conditions</small></span></div><div class="arrow">${icon('arrow-right')}</div><div class="flow-node"><span><strong>${h(e.kind)}</strong></span></div><div class="arrow">${icon('arrow-right')}</div><div class="flow-node tool"><span><strong>13 jointly generated channels</strong><small>Height, depth, starts, markers, natural energy/mass, wreck mass, civilians, RGB</small></span></div></div><p>${h(e.postprocessing)}</p><div class="links">${link(rel(e.review),'Open pilot review')}${link(rel(e.doc),'Training contract')}${link(rel(e.progress),'Saved run status')}${e.actual_training_receipt?link(rel(e.receipt),'Actual training receipt'):''}</div></section>`).join('');
}

function overview() {
  return `<div class="intro"><div class="eyebrow">${h(atlas.scope)}</div><h1>From map request to game files</h1><p class="lede">Four trained stages predict structure and allocation. Deterministic tools turn their arrays into geometry, marker coordinates and actual entities. Planned stages are separate.</p><div class="links">${link('pipeline-overview.png','Overview PNG')}</div></div>
  <div class="legend"><span><i></i>Learned prediction</span><span><i class="tool"></i>Deterministic tool / asset binding</span><span><i class="plan"></i>Planned, not built</span></div>
  <div id="pipeline-diagram" class="flow" role="group" aria-label="Current generation pipeline">
    <div class="single"><button class="flow-node tool" data-route="spawns" type="button">${icon('sliders-horizontal')}<span><span class="tag">Supplied inputs</span><strong>Map request + planned base coordinates + seed</strong><small>Current scope: 10km, 1v1; starts are not model predictions</small></span></button></div>
    ${down('base heatmaps + control vector + diffusion noise')}
    <div class="single">${node('terrain',false,'3 x 256 x 256: height + water distance + depth')}</div>
    ${down('decode and constrain the predicted geometry')}
    <div class="single">${node('terrain_finish',true,'Symmetry, water consistency, smoothing, native quantization')}</div>
    ${down('terrain channels + derived passability + planned bases')}
    <div class="single">${node('resources',false,'2 x 256 x 256: mex and hydro scores')}</div>
    ${down('score maps + count caps + symmetry')}
    <div class="single">${node('marker_decode',true,'Actual mex/hydro coordinates; starts stay supplied')}</div>
    <div class="shared-packet"><strong>Shared aligned terrain-and-marker packet</strong><small>9 channels: height, water SDF, depth, land/hover passability, two bases, mexes, hydros</small></div>
    <div class="branches">
      <div class="branch"><span class="route">Same packet, reduced to 128 x 128</span>${node('natural',false,'2 allocation fields: tree energy + rock mass')}${down('relative allocation, not amounts')}${node('natural_compose',true,'Native tree and rock prop instances')}<div class="budget-side">Extra tool inputs: energy/mass budgets, stock asset pool and composer seed.</div></div>
      <div class="branch"><span class="route">Same packet; NOT tree/rock heatmaps</span>${node('wrecks',false,'1 allocation field: wreck mass')}${down('relative allocation, not unit IDs')}${node('wreck_compose',true,'Unit wreck records + runtime creation script')}<div class="budget-side">Extra tool inputs: wreck-mass budget, unit pool and composer seed.</div></div>
      <div class="branch"><span class="route">Proposed: terrain + bases/resources</span>${node('civilians',false,'Density / layout target not finalized')}${down('future layout field')}${node('civilian_compose',true,'Living building records in save-Lua')}<div class="budget-side">Future building pools, budgets and allegiance.</div></div>
      <div class="branch"><span class="route">Proposed: terrain + chosen palette</span>${node('textures',false,'Source tensors ready; no trained painter')}${down('future material painting')}${node('texture_compile',true,'Material masks and references')}<div class="budget-side">Current bypass: inherit a stock base material. No learned texture generation.</div></div>
    </div>
    <div class="merge">Geometry + markers + props + scripts + inherited material converge here ${icon('arrow-down')}</div>
    <div class="single">${node('export',true,'SCMAP + scenario/save/script Lua + preview + metadata')}</div>
    <button type="button" class="bypass" data-route="tool:repair">Optional terrain / resource repair validator: implemented, but BYPASSED for current raw tests.</button>
    <div class="single">${node('playtest',true,'Install hashes, load logs, then player assessment')}</div>
  </div>
  <div class="callouts"><div><span class="number">01 / WHERE VS HOW MUCH</span><h3>The network draws allocation</h3><p>Budgets and asset values enter the composers, not the current tree/rock or wreck model.</p></div><div><span class="number">02 / SHARED INPUTS, NOT A CHAIN</span><h3>Natural reclaim and wrecks branch</h3><p>They use the same nine channels. Wreck initialization copied feature weights during training only.</p></div><div><span class="number">03 / TEXTURES ARE NOT LEARNED YET</span><h3>Visible grass is a template material</h3><p>Extraction is complete. A palette-aware texture model and learned painting export remain planned.</p></div></div>${jointExperimentOverview()}`;
}

function contract(group) {
  return `<div class="contract"><div class="contract-heading"><h3>${h(group.name)}</h3><span class="shape">${h(group.shape)}</span></div><p>${h(group.source)}</p>${assets(group.tiles)}</div>`;
}

function modelView(id) {
  const m = byId(id);
  const after = m.after ? toolById(m.after) : null;
  return `<div class="eyebrow">${m.status==='planned'?'Planned contract, not an implemented model':'Generation contract'} / ${h(m.kind)}</div><h1>${h(m.title)}</h1><p class="lede">${h(m.purpose)}</p>
  <div class="status-line"><span class="status ${h(m.status)}">${h(m.status_text)}</span><span class="muted small">${h(m.run_status)}</span></div>
  <div class="mini-chain"><div class="flow-node tool"><span><span class="tag">Inputs at generation</span><strong>${h(m.inputs.map(g=>g.shape).join(' + '))}</strong></span></div><div class="arrow">${icon('arrow-right')}</div><div class="flow-node ${m.status==='planned'?'planned':''}"><span><span class="tag">${m.status==='planned'?'Future stage':'Neural network'}</span><strong>${h(m.title)}</strong><small>${m.parameters?(m.parameters/1e6).toFixed(2)+'M parameters':'Architecture pending'}</small></span></div><div class="arrow">${icon('arrow-right')}</div><div class="flow-node tool"><span><span class="tag">Outputs</span><strong>${h(m.outputs.map(g=>g.shape).join(' + '))}</strong></span></div></div>
  ${m.checkpoint?`<div class="fact-row"><span><strong>Selected update</strong> ${m.step.toLocaleString()}</span><span><strong>Dataset</strong> ${h(m.cohort)}</span><span><strong>Weights used</strong> EMA</span></div><div class="pathline"><code>${h(m.checkpoint)}</code></div>`:`<p class="muted">${h(m.cohort)}. No trained checkpoint.</p>`}
  <div class="links">${Object.entries(m.links).map(([key,url])=>link(url,({checkpoint:'Checkpoint',review:'Results gallery',code:'Source code',doc:'Detailed notes'})[key])).join('')}</div>
  ${m.training_evidence?`<nav class="section-jumps" aria-label="Model evidence"><button type="button" data-jump=".training-receipt">${icon('database')} Actual training tensors</button><button type="button" data-jump=".runtime-settings">${icon('sliders-horizontal')} Generation settings</button></nav>`:''}
  <section class="band"><h2>Default source reference: Setons FAF</h2><p>Physical source illustration from the 20km FAF version. The selected 10km model contract and its exact historical evidence are documented below; no Setons model inference is claimed.</p>${assets(['source_height','source_depth','source_mex'])}</section>
  <section class="band"><h2>Inputs to this model</h2>${m.inputs.map(contract).join('')}</section>
  <section class="band"><h2>${m.status==='planned'?'Proposed outputs / available source representation':'Model outputs, before composition'}</h2>${m.outputs.map(contract).join('')}<div class="note neutral"><strong>Not produced by this model</strong><p>${h(m.not_outputs)}</p></div></section>
  ${trainingReceipt(m)}
  ${settings(id)}
  ${after?`<section class="band"><h2>What happens after the output?</h2>${node(m.after,true)}<p>${h(after.meaning)}</p>${id==='natural'?'<p><strong>Current medium composition:</strong> 2,694 trees + 644 rocks. 11,835.5 tree energy and 3,765 rock mass; total mass also includes 1,610.5 from trees.</p>':''}${id==='wrecks'?'<p><strong>Current export:</strong> 18 wrecks, 4,943.52 mass placed / 6,000 requested. Two underwater centers retained. Runtime not yet verified.</p>':''}${['natural','wrecks','resources'].includes(id)?`<details class="saved-experiment"><summary>Original composed experiment result</summary><a href="${atlas.assets[{natural:'natural_composed',wrecks:'wreck_composed',resources:'resource_points'}[id]].image}" target="_blank" rel="noopener"><img class="result-image" src="${atlas.assets[{natural:'natural_composed',wrecks:'wreck_composed',resources:'resource_points'}[id]].image}" alt="${h(m.title)} decoded output" loading="lazy"></a></details>`:''}</section>`:''}
  <div class="note"><strong>Current limitation / policy</strong><p>${h(m.caution)}</p></div>`;
}

function training() {
  return `<div class="eyebrow">Source data is separate from neural inference</div><h1>Map data, tensors and training pairs</h1><p class="lede">Physical layers, derived gameplay observations and the arrays actually consumed by our models are distinct parts of the dataset.</p><nav class="section-jumps" aria-label="Dataset evidence"><button type="button" data-jump=".map-information">${icon('layers')} Map information inventory</button></nav>
  <div class="stage-flow"><div class="item"><strong>Map folders</strong><small>SCMAP + Lua + blueprint archives</small></div>${icon('arrow-right')}<div class="item"><strong>Extractor + audits</strong><small>Physical values, coordinates, materials</small></div>${icon('arrow-right')}<div class="item"><strong>Curation + family split</strong><small>Keep exclusions and latest representatives</small></div>${icon('arrow-right')}<div class="item"><strong>Per-role tensor exporters</strong><small>Aligned input conditions + separate target fields</small></div></div>
  <div class="note neutral"><strong>During training</strong><p>Known source conditions accompany a separate extracted target. The tree/rock and wreck allocation networks never receive their clean target as an input. Diffusion training deliberately receives a noised version of the target plus its timestep, and learns denoising updates. At generation time diffusion starts with seeded noise; no original target map is supplied.</p></div>
  <div class="source-grid">${['extract','curate','tensorize'].map(id=>`<div>${node(id,true)}</div>`).join('')}</div>
  ${mapInformation()}
  <section class="band"><h2>One real source map, split into layers</h2><p>Setons Clutch – FAF version (8553_17709, 20km source reference). These PNGs visualize saved numeric arrays, not training on the map's preview image.</p>${assets(['source_height','source_depth','source_mex','source_hydro','source_tree','source_rock','source_wreck','texture_palette','texture_weights'])}</section>
  <section class="band"><h2>Tensor vocabulary</h2><dl class="terms"><div><dt>Tensor / channel</dt><dd>A stack of numeric grids. Shapes here omit batch size: <code>[channel, z, x]</code>. A PNG shows one channel or an explicitly labeled composite.</dd></div><div><dt>256 and 128 grids</dt><dd>Same whole 10km map at different sampling grids. The native map has 512 cells and 513 height vertices per side. Smaller network grids do not mean smaller playable maps.</dd></div><div><dt>Heatmap / score map</dt><dd>A spatial field. Mex/hydro scores are peak-decoded into markers. Their raw integral is not a trustworthy entity count.</dd></div><div><dt>Value allocation</dt><dd>A nonnegative field summing to one. A budget converts spatial shares into desired energy or mass per area. It is not an image of asset IDs.</dd></div><div><dt>Mask / validity flag</dt><dd>Marks usable data or known quantities. Missing values are not zero. Texture shader validity is separate from successfully decoding a file.</dd></div><div><dt>Symmetry and composition</dt><dd>Deterministic operations after prediction. They enforce pairing and instantiate selected assets; they do not constitute another neural model.</dd></div></dl></section>
  <section class="band"><h2>Current dataset states</h2><dl><div class="tensor-info"><dt>Main curated cohort</dt><dd>1,020 train / 97 validation. Family/version filtering and player exclusions retained. No independent final test set is being used here.</dd></div><div class="tensor-info"><dt>Natural reclaim</dt><dd>Fully known tree energy and natural-rock mass. Empty roles have no allocation loss; composer budget controls abundance.</dd></div><div class="tensor-info"><dt>Wrecks</dt><dd>193 train / 18 validation complete positive maps. 100 maps with unresolved wreck mass excluded for this role only; 806 known-zero maps are not spatial targets.</dd></div><div class="tensor-info"><dt>Textures</dt><dd>${atlas.texture_status.completed.toLocaleString()} maps extracted, ${atlas.texture_status.failed} decode failures, 15 unsupported paint semantics, ${atlas.texture_status.fully_resolved_albedo_maps} fully resolved albedo maps. No model training.</dd></div><div class="tensor-info"><dt>Human annotation</dt><dd>The crowd-labeling project is separate. It is not silently producing all current model controls: the active terrain profile uses direct algorithmic terrain measurements.</dd></div></dl></section>
  <section class="band"><h2>Terrain's ten control values</h2><p>The 21-number profile is these ten normalized values, ten availability flags and one water-enabled flag. The seed/noise and planned base grids are separate inputs.</p><ul>${atlas.controls.map(x=>`<li><code>${h(x)}</code></li>`).join('')}</ul></section>`;
}

function checks() {
  return `<h1>Tools, constraints and different meanings of validation</h1><p class="lede">These checks answer different questions. A low training loss, a valid file and a map that plays well are not interchangeable outcomes.</p><div class="checks"><article><h3>1. Dataset integrity</h3><p>Shapes, finite values, source hashes, known-value masks, family separation and tensor alignment. Unknown quantities must not become invented zeros.</p><span class="status approved">Active</span></article><article><h3>2. Source-agreement diagnostics</h3><p>Denoising loss, NLL, allocation capture and held-out examples. Measures resemblance to source choices, not whether the resulting map is aesthetically or competitively better.</p><span class="status experimental">Diagnostic, not quality ranking</span></article><article><h3>3. Format / composition checks</h3><p>Native height and prop readback, exact XY pairing, local budget accounting, file hashes and safety caps. These do not prove buildability or balance.</p><span class="status approved">Active</span></article><article><h3>4. Gameplay / player assessment</h3><p>Actual meshes, commander spawning, engine reclaim values, navigation, expansion value and fairness. Natural reclaim has been seen in game; new wreck creation is still untested.</p><span class="status pilot">Partially playtested</span></article></div><div class="note"><strong>Repair is not currently hiding predictions</strong><p>The earlier marker/terrain repair system exists, but is bypassed. The current composer does not snap mexes, move starts, flatten resource pads or reject reclaim on water. Optional same-role prop spacing is a separate, explicit composer constraint.</p></div><section class="band"><h2>Tool contracts</h2>${atlas.tools.map(tool=>toolView(tool.id,true)).join('')}</section>`;
}

function toolView(id, compact=false) {
  const t = toolById(id);
  return `<${compact?'article':'section'} class="tool-row" id="tool-${h(id)}"><div class="tool-heading">${icon(t.icon)}<${compact?'h3':'h1'}>${h(t.name)}</${compact?'h3':'h1'}></div><span class="status ${h(t.status)}">${h(t.status.replaceAll('_',' '))}</span><dl><dt>Inputs</dt><dd>${h(t.input)}</dd><dt>Outputs</dt><dd>${h(t.output)}</dd></dl><p>${h(t.meaning)}</p><div class="links">${Object.entries(t.links).map(([key,url])=>link(url,key==='code'?'Source code':'Detailed notes')).join('')}</div></${compact?'article':'section'}>`;
}

function history() {
  return `<h1>Model runs and historical experiments</h1><p class="lede">${atlas.historical.length} checkpoint-bearing run folders discovered from local artifacts. Current selections are explicit; the other checkpoints are historical or comparison candidates, not extra hidden stages in today's generator.</p><p class="small muted">Metadata inspection uses a CPU meta-device view, not training or inference. Some early contracts differ from today's normalized fields. Galleries and reports without their own checkpoints are not counted as separate models.</p>${atlas.historical.map(run=>`<details class="archive-run"><summary><code>${h(run.name)}</code><span class="status ${run.active_model?'approved':''}">${run.active_model?'Selected for '+h(byId(run.active_model).title):'Historical / comparison'}</span></summary><div class="mini-chain"><div class="flow-node tool"><span><span class="tag">Saved experiment input</span><strong>${h(run.inputs)}</strong></span></div><div class="arrow">${icon('arrow-right')}</div><div class="flow-node"><span><span class="tag">Run</span><strong>${h(run.name)}</strong></span></div><div class="arrow">${icon('arrow-right')}</div><div class="flow-node tool"><span><span class="tag">Saved experiment output</span><strong>${h(run.outputs)}</strong></span></div></div><p>${h(run.note)}</p><div class="links">${run.artifacts.map(p=>link(p.href,p.name)).join('')}</div><details><summary>Saved configuration facts</summary><pre>${h(JSON.stringify(run.config,null,2))}</pre></details></details>`).join('')}`;
}

const navGroups = [
  ['Project library',[['status','Project status','activity'],['layers','Maps, Layers and Tensors','layers'],['library','Documents & results','book-open']]],
  ['Models & generation',[['overview','Generation chain','workflow'],['training','Data & training tensors','database'],['controls','Controls & data use','sliders-horizontal']]],
  ['Selected models',atlas.models.filter(m=>m.checkpoint).map(m=>[m.id,m.title,m.icon])],
  ['Planned models',atlas.models.filter(m=>!m.checkpoint).map(m=>[m.id,m.title,m.icon])],
  ['Evidence & next work',[['work','Work & open questions','list-checks'],['checks','Checks & tools','shield-check'],['history','Experiments & model runs','archive']]]
];
const routes = navGroups.flatMap(([,items])=>items);
document.getElementById('navigation').innerHTML = navGroups.map(([title,items])=>`<div class="nav-label">${h(title)}</div>${items.map(([id,title,ic])=>`<button type="button" class="nav-item ${byId(id)?.status==='planned'?'planned':''}" data-route="${h(id)}">${icon(ic)}<span>${h(title)}</span></button>`).join('')}`).join('');
document.getElementById('stage-picker').innerHTML = routes.map(([id,title])=>`<option value="${h(id)}">${h(title)}</option>`).join('');
function render() {
  let route = decodeURIComponent(location.hash.slice(1)) || (window.MAPGEN_PUBLIC_VIEW?'status':'layers');
  let anchor='';
  if(route==='home') route='layers';
  if(route==='derived'){route='layers';anchor='derived';}
  if(route.startsWith('layers/')){anchor=route.slice(7);route='layers';}
  anchor=({natural:'natural_energy',air:'air_expansion',abundance:'natural_mass'})[anchor]||anchor;
  let content;
  if (route.startsWith('tool:') && toolById(route.slice(5))) content = `<div class="eyebrow">Deterministic tool, not a learned model</div>${toolView(route.slice(5))}`;
  else if (byId(route)) content = modelView(route);
  else if (projectViews[route]) content = projectViews[route]();
  else if (route==='training') content = training();
  else if (route==='controls') content = controls();
  else if (route==='checks') content = checks();
  else if (route==='history') content = history();
  else if (route==='overview') content=overview();
  else {route='layers';content=projectViews.layers();}
  document.getElementById('main').innerHTML = content;
  applyAtlasDisplay();
  document.querySelectorAll('.nav-item').forEach(el=>{el.classList.toggle('active',el.dataset.route===route);el.setAttribute('aria-current',el.dataset.route===route?'page':'false');});
  document.getElementById('stage-picker').value = route.startsWith('tool:')?'checks':route;
  window.lucide.createIcons();
  if(anchor) requestAnimationFrame(()=>document.getElementById('layer-'+anchor)?.scrollIntoView({block:'start'}));
  document.title = (byId(route)?.title || routes.find(x=>x[0]===route)?.[1] || 'Tool')+' | MapGen project atlas';
}
document.addEventListener('click', event=>{
  const jump=event.target.closest('[data-jump]');
  if(jump){document.querySelector(jump.dataset.jump)?.scrollIntoView({block:'start'});return;}
  const target=event.target.closest('[data-route]');
  if(target){location.hash=target.dataset.route;window.scrollTo(0,0);}
});
document.getElementById('stage-picker').addEventListener('change',event=>{location.hash=event.target.value;window.scrollTo(0,0);});
window.addEventListener('hashchange',render);
render();
