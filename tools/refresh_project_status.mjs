import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const page=path.join(root,'docs/model-atlas');
const atlas=JSON.parse(await fs.readFile(path.join(page,'generated/atlas.json'),'utf8'));
const catalog=JSON.parse(await fs.readFile(path.join(page,'catalog.json'),'utf8'));
const runs=[];
for(const experiment of catalog.experiments||[]){
 try{
  const data=JSON.parse(await fs.readFile(path.join(root,experiment.progress),'utf8'));
  runs.push({id:experiment.id,title:experiment.title,state:data.state,stage:data.stage,
   stages:(data.stages||[]).map(x=>({id:x.id,status:x.status,step:x.summary?.step??null})),evidence:experiment.doc});
 }catch{runs.push({id:experiment.id,title:experiment.title,state:'unavailable',evidence:experiment.doc});}
}
const status={schema:'mapgen_project_status_v1',recorded_at:atlas.generated_at,repository:'https://github.com/LimeZ3/Lime-Map-Generator',
 atlas_url:'https://mapgen-project-atlas.elven-bowl-7506.chatgpt.site',phase:'Research prototype — playable exports; competitive quality unproven',
 source_of_truth:'docs/model-atlas: catalog, controls, saved receipts, map comparisons and extraction work queue',
 metrics:{selected_trained_stages:atlas.models.filter(m=>m.checkpoint).length,checkpoint_runs:atlas.historical.length,curated_train:1020,curated_validation:97,
 texture_maps:atlas.texture_status.completed,fully_resolved_albedo_maps:atlas.texture_status.fully_resolved_albedo_maps,comparison_maps:5,layer_families:19,
 joint_channels:13,joint_train:782,joint_validation:69},
 completed:[
  {title:'Map extraction and source representations',text:'Terrain/water, starts, resource markers, natural energy/mass, wrecks, civilians and surface material representations have source receipts. Unknown values and unsupported runtime rules remain explicit.',evidence:'docs/map_layers_v2.md'},
  {title:'Four selected generation stages',text:'Terrain/water, resource markers, natural reclaim allocation and wreck allocation have selected checkpoints. Deterministic finishing/composition exports geometry, markers and entities.',evidence:'docs/model-atlas/catalog.json'},
  {title:'Dataset and texture preparation',text:'The selected curated cohort contains 1,020 training and 97 validation maps. Texture extraction completed 1,117 maps with no decode failures; 929 albedo sources are fully resolved. Extraction success does not certify every shader’s training semantics.',evidence:'docs/map_texture_tensors.md'},
  {title:'Gameplay-analysis and annotation pipeline',text:'Versioned route/front, resource-economy and air/drop analyses exist. The 3,108-version annotation-pool milestone reports 2,764 scored maps, 329 exclusions and 15 failures. These are heuristic 1v1 observations, not map-quality ground truth.',evidence:'docs/map-rating-extraction/README.md'},
  {title:'Joint source-layer experiment and diagnostics',text:'A separate 73.3M-parameter network jointly predicts 13 source channels from noise and 12 rating controls. The 782/69 cohort and completed diagnostic arms are experimental; they do not replace the selected stages.',evidence:'docs/joint_source_diagnostics.md'},
  {title:'Navigable project atlas',text:'Five exact FAF map versions, 19 comparison families, source/method links, model contracts, archived runs, global preview sliders and explicit extraction TODOs now organize the project.',evidence:'docs/model-atlas/index.html'}],
 results:[
  'Selected terrain geometry and natural reclaim composition have been observed in game; resource markers were exported and playtested, with balance still unproven.',
  'Wreck allocation is trained and exported, but its current runtime behavior is not yet verified.',
  'The joint one-map baseline reproduced a spatial template (height correlation 0.9980 at update 2,365), while sparse-density totals remained badly biased (Start A integral 139.6 instead of one). This is memorization evidence, not generalization.',
  'The joint-source continuation ended by user request at update 22,947. The separate baseline/lower-LR/balanced one-map and lower-LR full-cohort diagnostic arms have saved completed receipts.'
 ],
 planned:[
  'Correct DualGap Adaptive’s archived air pair (slot 12 used where the intended comparison needs slot 2).',
  'Improve main-base/rear/forward zoning, define contestability coherently and fill missing exact-version outputs.',
  'Add hover/navy battle-path comparisons and newer frontier coverage for FAF Beetles.',
  'Diagnose sparse-density/background errors and held-out behavior before selecting any joint-source checkpoint.',
  'Learned texture painting, civilian composition and spawn-layout generation remain planned or experimental, with exact boundaries in the catalog.',
  'Continue structuring completed work and the TODO list in this atlas; validate exports and gameplay rather than equating loss with playability.'
 ],runs,
 update_contract:'Progress must be recorded in the atlas, then published as a GitHub codex/atlas-live snapshot. Open pages check for a newer snapshot every 60 seconds. Uncommitted local work is not automatically visible.'};
await fs.writeFile(path.join(page,'project-status.json'),JSON.stringify(status,null,2)+'\n');
await fs.writeFile(path.join(page,'generated/project-status-data.js'),'window.MAPGEN_PROJECT_STATUS = '+JSON.stringify(status).replaceAll('<','\\u003c')+';\n');
const metric=status.metrics;
let report=`# MapGen progress update — 25 October 2026\n\nThe [MapGen project atlas](${status.atlas_url}) is the main project reference for status, map layers, data, selected models, experimental branches, results and open work. The project remains **experimental research software**, not a finished or competitively validated generator.\n\nThis update records progress since the initial repository snapshot. Evidence is the atlas catalog and saved receipts, refreshed ${status.recorded_at}.\n\n## Implemented and collected\n\n`;
for(const item of status.completed)report+=`### ${item.title}\n\n${item.text}\n\nEvidence: [${item.evidence}](../${item.evidence.replace(/^docs\//,'')}).\n\n`;
report+=`## Current evidence\n\n- **${metric.selected_trained_stages} selected trained stages**; **${metric.checkpoint_runs} discovered checkpoint-bearing runs** are preserved as an inventory, not ${metric.checkpoint_runs} active pipeline stages.\n- **${metric.curated_train} train / ${metric.curated_validation} validation** in the selected curated cohort. No independent final test set is being claimed.\n- **${metric.texture_maps} texture extractions**, **${metric.fully_resolved_albedo_maps} fully resolved albedo sources**; learned painting is not selected.\n- **${metric.comparison_maps} exact map versions** across **${metric.layer_families} source/derived comparison rows**.\n- Separate joint experiment: **${metric.joint_channels} channels**, **${metric.joint_train} train / ${metric.joint_validation} validation**; no selected production release.\n\n`;
for(const result of status.results)report+=`- ${result}\n`;
report+='\n## Next work\n\n'+status.planned.map(x=>'- '+x).join('\n')+'\n\nThe [maps extraction work queue](../map-extraction-todos.md) tracks known source/pairing/zoning issues and missing coverage. Reports using stock Setons/Beetles must not be presented as the selected FAF versions.\n\n## Keeping this current\n\nThe atlas is the authoritative project index; this report is a dated snapshot. After meaningful progress, update the atlas catalog/status/work queue, refresh the saved evidence, and publish the public atlas snapshot. The ChatGPT Site checks GitHub for a newer snapshot every minute while open. This is publication-driven updating, not automatic access to uncommitted local files or a claim that training is continuously monitored. Hosting uses ChatGPT Sites, not Netlify.\n\nOriginal project code is MIT licensed. Existing maps and game assets retain their respective owners; the atlas identifies their versions and treats their previews as reference material.\n';
await fs.mkdir(path.join(root,'docs/progress'),{recursive:true});await fs.writeFile(path.join(root,'docs/progress/2026-10-25-project-update.md'),report);
console.log(JSON.stringify({recorded_at:status.recorded_at,selected:metric.selected_trained_stages,runs:metric.checkpoint_runs,report:'docs/progress/2026-10-25-project-update.md'}));
