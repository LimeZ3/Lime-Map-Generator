import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {execFileSync} from 'node:child_process';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const page=path.join(root,'docs/model-atlas');
const site=path.join(root,'sites/mapgen-project-atlas');
const build=path.join(root,'.tmp/atlas-public-build');
const payload=path.join(build,'payload-'+Date.now());await fs.mkdir(payload,{recursive:true});
const markedPath=process.env.ATLAS_MARKED_MODULE||'C:/Users/limon/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/marked/lib/marked.esm.js';
const {marked}=await import(pathToFileURL(markedPath).href);
const aliases={};const queue=[];const copied=new Set();
const repo='https://github.com/LimeZ3/Lime-Map-Generator';
const hash=x=>crypto.createHash('sha256').update(x).digest('hex');
const escape=x=>String(x).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
function scrub(x){
 if(typeof x==='string'){
  const normalized=x.replaceAll('\\','/');const prefix=root.replaceAll('\\','/');
  if(normalized.toLowerCase().startsWith(prefix.toLowerCase()+'/'))return normalized.slice(prefix.length+1);
  if(/^[A-Za-z]:\//.test(normalized))return '[local installation]/'+path.posix.basename(normalized);
  return x;
 }
 if(Array.isArray(x))return x.map(scrub);
 if(x&&typeof x==='object')return Object.fromEntries(Object.entries(x).map(([k,v])=>[scrub(k),scrub(v)]));
 return x;
}
async function put(rel,data){const p=path.join(payload,rel);await fs.mkdir(path.dirname(p),{recursive:true});await fs.writeFile(p,data);copied.add(rel);}
function reference(value,from='docs/model-atlas/index.html'){
 if(typeof value!=='string'||/^(https?:|#|data:|mailto:|javascript:)/.test(value))return;
 const clean=value.split('#')[0].split('?')[0];if(!clean||clean.includes('\n'))return;
 let rel=path.posix.normalize(path.posix.join(path.posix.dirname(from),clean.replaceAll('\\','/')));
 if(/^(data|docs|src|tools|configs)\//.test(clean))rel=clean;
 if(rel.startsWith('../')||path.isAbsolute(rel))return;
 if(!aliases[rel]){aliases[rel]=rel;queue.push(rel);}
}
function scan(x){if(typeof x==='string'){if(/^(\.\.?\/|data\/|docs\/|src\/|tools\/)/.test(x))reference(x);}else if(x&&typeof x==='object')Object.values(x).forEach(scan);}
async function walk(folder){let entries=[];for(const d of await fs.readdir(folder,{withFileTypes:true})){if(d.name.startsWith('.'))continue;const full=path.join(folder,d.name);if(d.isDirectory())entries.push(...await walk(full));else entries.push(full);}return entries;}
// Copy the reviewed atlas itself; source data remain outside this root.
for(const file of await walk(page)){
 let rel=path.relative(root,file).replaceAll('\\','/');if(rel.endsWith('layer-review-inventory.json'))continue;
 const ext=path.extname(file).toLowerCase();let bytes=await fs.readFile(file);
 if(ext==='.json'){
  let value=scrub(JSON.parse(bytes.toString('utf8')));scan(value);bytes=Buffer.from(JSON.stringify(value));
 }else if(ext==='.js'){
  let code=bytes.toString('utf8').replace(/^\uFEFF/,'');
  const match=code.match(/^(window\.MAPGEN_\w+\s*=\s*)([\s\S]*);\s*$/);
  if(match){try{const value=scrub(JSON.parse(match[2]));scan(value);code=match[1]+JSON.stringify(value).replaceAll('<','\\u003c')+';\n';}catch{}}
  for(const m of code.matchAll(/['"](\.\.?\/[^'"\n]+\.(?:md|json|html|py))['"]/g))reference(m[1]);
  bytes=Buffer.from(code);
 }
 if(ext==='.md'){reference(path.basename(file),rel);continue;}
 await put(rel,bytes);aliases[rel]=rel;
}
for(const file of await walk(path.join(root,'docs'))){if(path.extname(file)==='.md'&&!file.includes(path.sep+'portfolio'+path.sep))reference(path.relative(root,file).replaceAll('\\','/'));}
function htmlDoc(title,body){return `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${escape(title)} | MapGen atlas</title><style>body{font:16px/1.65 system-ui;margin:40px auto;padding:0 24px;max-width:1050px;color:#21372d}a{color:#11695b}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f1f4f2;padding:16px}table{border-collapse:collapse;display:block;overflow:auto}td,th{border:1px solid #ccd7d0;padding:8px}img{max-width:100%}.meta{font-size:13px;color:#63776b}</style></head><body><p><a href="docs/model-atlas/index.html" data-atlas-home>← Project atlas</a> · <a href="${repo}">GitHub</a></p>${body}<script src="docs/model-atlas/public-links.js" data-public-links></script></body></html>`;}
const omitted=[];
for(let i=0;i<queue.length;i++){
 const rel=queue[i];if(copied.has(rel))continue;
 const full=path.resolve(root,rel);let stat;try{stat=await fs.stat(full);}catch{}
 const ext=path.extname(rel).toLowerCase();const safe=/^(docs\/|src\/|tools\/|configs\/|data\/(models|tensors|processed)\/)/.test(rel)&&!/(private|review-backups|responses|\.env)/i.test(rel);
 if(!safe||!stat?.isFile()||stat.size>2_000_000||['.pt','.pth','.npz','.zip','.gz','.i32','.u16'].includes(ext)||rel.startsWith('data/')&&ext==='.html'){
  const target='evidence/'+hash(rel).slice(0,20)+'.html';aliases[rel]=target;omitted.push(rel);
  await put(target,htmlDoc(path.posix.basename(rel),`<h1>${escape(path.posix.basename(rel))}</h1><p>This research artifact stays in the full project checkout. The public atlas includes selected previews, contracts, recorded status and methodology; it does not distribute checkpoints, full raw arrays, or local review applications.</p><p><code>${escape(rel)}</code></p><p>Use the atlas methods and source receipts to locate it locally. A missing public download is not a missing or zero-valued scientific result.</p>`));continue;
 }
 let text=await fs.readFile(full,'utf8');let target=rel;
 if(ext==='.md'){
  target=rel.slice(0,-3)+'.html';aliases[rel]=target;
  for(const m of text.matchAll(/\]\(([^)]+)\)/g))reference(m[1],rel);
  let body=marked.parse(text);body=body.replace(/<h([1-6])>(.*?)<\/h\1>/g,(_,n,inside)=>`<h${n} id="${inside.replace(/<[^>]+>/g,'').toLowerCase().replace(/[^\w\s-]/g,'').trim().replace(/\s+/g,'-')}">${inside}</h${n}>`);
  await put(target,htmlDoc(path.posix.basename(rel),body));
 }else if(['.py','.mjs','.js','.json','.toml','.txt','.csv'].includes(ext)){
  if(ext==='.json'){try{text=JSON.stringify(scrub(JSON.parse(text)),null,2);}catch{}}
  text=text.replaceAll(root.replaceAll('\\','/'),'[project]').replaceAll(root,'[project]');target='evidence/'+hash(rel).slice(0,20)+'.html';aliases[rel]=target;
  await put(target,htmlDoc(path.posix.basename(rel),`<h1>${escape(path.posix.basename(rel))}</h1><p class="meta">Saved public evidence snapshot: ${escape(rel)}</p><pre>${escape(text)}</pre>`));
 }else if(['.png','.jpg','.jpeg','.svg','.css','.html'].includes(ext))await put(rel,await fs.readFile(full));
 else{aliases[rel]='evidence/unavailable.html';}
}
await put('evidence/unavailable.html',htmlDoc('Research artifact','<h1>Local research artifact</h1><p>This artifact is not included in the public snapshot. Consult the methods and recorded evidence in the project atlas.</p>'));
const bridge=`const links=${JSON.stringify(aliases)};function rewrite(){for(const a of document.querySelectorAll('a[href]')){if(a.dataset.publicResolved)continue;const raw=a.getAttribute('href');if(!raw||raw.startsWith('#')||/^(https:|mailto:|data:)/.test(raw))continue;let rel;try{rel=new URL(raw,'https://atlas.invalid/'+window.MAPGEN_DOCUMENT_PATH).pathname.slice(1);}catch{continue;}const target=links[rel];if(!target)continue;let hash='';try{hash=new URL(raw,'https://atlas.invalid/'+window.MAPGEN_DOCUMENT_PATH).hash;}catch{}a.href=window.MAPGEN_PORTAL_ORIGIN+'/?view='+encodeURIComponent(target)+(hash?'&anchor='+encodeURIComponent(hash.slice(1)):'');if(a.target!=='_blank')a.target='_top';a.dataset.publicResolved='true';}}document.addEventListener('click',event=>{const a=event.target.closest('a[href]');const raw=a?.getAttribute('href');if(raw?.startsWith('#')){event.preventDefault();if(window.MAPGEN_DOCUMENT_PATH==='docs/model-atlas/index.html')location.hash=raw;else document.getElementById(raw.slice(1))?.scrollIntoView();}},true);new MutationObserver(rewrite).observe(document.body,{childList:true,subtree:true});rewrite();if(window.MAPGEN_DOCUMENT_PATH==='docs/model-atlas/index.html')window.addEventListener('hashchange',()=>parent.postMessage({type:'mapgen-route',hash:location.hash},window.MAPGEN_PORTAL_ORIGIN));`;
await put('docs/model-atlas/public-links.js',bridge);
for(const rel of [...copied].filter(x=>x.endsWith('.html'))){
 let html=await fs.readFile(path.join(payload,rel),'utf8');
 if(rel==='docs/model-atlas/index.html')html=html.replace('</body>','<script src="public-links.js"></script></body>');
 else html=html.replace('href="docs/model-atlas/index.html" data-atlas-home','href="'+path.posix.relative(path.posix.dirname(rel),'docs/model-atlas/index.html')+'" data-atlas-home').replace('src="docs/model-atlas/public-links.js" data-public-links','src="'+path.posix.relative(path.posix.dirname(rel),'docs/model-atlas/public-links.js')+'" data-public-links');
 await put(rel,html);
}
const entries=[...copied].sort();const files=[];for(const rel of entries){const data=await fs.readFile(path.join(payload,rel));files.push({path:rel,sha256:hash(data),bytes:data.length});}
const revision=hash(JSON.stringify(files)).slice(0,20);
const manifest={schema:'mapgen_public_atlas_v1',revision,entry:'docs/model-atlas/index.html',repository:repo,source_of_truth:'docs/model-atlas',recorded_at:JSON.parse(await fs.readFile(path.join(page,'project-status.json'),'utf8')).recorded_at,files};
const release=path.join(build,'releases',revision);await fs.mkdir(release,{recursive:true});await fs.cp(payload,release,{recursive:true});
await fs.writeFile(path.join(release,'manifest.json'),JSON.stringify(manifest));
const pointer={revision,prefix:'releases/'+revision+'/',entry:manifest.entry,recorded_at:manifest.recorded_at};await fs.writeFile(path.join(build,'latest.json'),JSON.stringify(pointer));
await fs.mkdir(path.join(site,'dist','releases',revision),{recursive:true});await fs.cp(release,path.join(site,'dist','releases',revision),{recursive:true});await fs.writeFile(path.join(site,'dist','latest.json'),JSON.stringify(pointer));
try{await fs.copyFile(path.join(site,'portal.html'),path.join(site,'dist/index.html'));}catch{}
await fs.writeFile(path.join(build,'publication.json'),JSON.stringify({revision,release,build,files:files.length,bytes:files.reduce((n,f)=>n+f.bytes,0),omitted:omitted.length}));
if(process.argv.includes('--push')){
 const checkout=path.join(build,'github-live');await fs.mkdir(checkout,{recursive:true});const env={...process.env,GIT_TERMINAL_PROMPT:'0'};
 const git=(args)=>execFileSync('git',args,{cwd:checkout,env,stdio:'pipe',encoding:'utf8'}).trim();
 try{await fs.access(path.join(checkout,'.git'));}catch{git(['init','-b','codex/atlas-live']);git(['remote','add','origin',repo+'.git']);}
 await fs.mkdir(path.join(checkout,'releases',revision),{recursive:true});await fs.cp(release,path.join(checkout,'releases',revision),{recursive:true});await fs.writeFile(path.join(checkout,'latest.json'),JSON.stringify(pointer));
 await fs.writeFile(path.join(checkout,'README.md'),'# MapGen public atlas snapshots\n\nGenerated from the project atlas. Visit https://mapgen-project-atlas.elven-bowl-7506.chatgpt.site for the readable live page. The main branch holds the research project; this branch holds immutable public snapshots and a latest.json pointer.\n');
 git(['add','--all']);let changed=git(['status','--porcelain']);if(changed){git(['-c','user.name=LimeZ3','-c','user.email=137434032+LimeZ3@users.noreply.github.com','commit','-m','Publish atlas snapshot '+revision]);git(['push','origin','HEAD:refs/heads/codex/atlas-live']);}
 console.log(JSON.stringify({published:true,commit:git(['rev-parse','HEAD']),...pointer,files:files.length}));
}else console.log(JSON.stringify({prepared:true,...pointer,files:files.length,bytes:files.reduce((n,f)=>n+f.bytes,0),omitted:omitted.length}));
