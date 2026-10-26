/* Geometric guides for human suggestions. Does not infer or alter measured symmetry. */
(() => {
 const colors=[[238,35,65],[35,195,250],[250,185,30],[175,90,250],[40,225,145],[250,120,45],[240,100,190],[100,145,255]];
 const cache=new Map(),hidden=new Set();
 const allowed=()=>document.getElementById('ds-view')?.value==='symmetry';
 function geometry(type){
  const axes={mirror_vertical:[Math.PI/2],mirror_horizontal:[0],mirror_diagonal:[Math.PI/4],mirror_antidiagonal:[-Math.PI/4],mirror_both:[0,Math.PI/2]};
  if(type==='mirror_both')return {family:'dihedral',n:2,axes:axes[type]};
  if(axes[type])return {family:'mirror',n:1,axes:axes[type]};
  const match=/^(rotation|dihedral)_(2|3|4|6|8)$/.exec(type||'');if(!match)return null;
  const n=Number(match[2]);return {family:match[1],n,axes:match[1]==='dihedral'?Array.from({length:n},(_,i)=>i*Math.PI/n):[]};
 }
 const mod=(a,b)=>{const phase=((a%b)+b)%b;return Math.min(phase,b-phase)<1e-10?0:phase;};
 function raster(type,size=512,guides=true){
  const g=geometry(type);if(!g)return null;
  const canvas=document.createElement('canvas');canvas.width=canvas.height=size;const ctx=canvas.getContext('2d'),image=ctx.createImageData(size,size),projection=new Float64Array(size*size),phases=new Float64Array(size*size);let low=Infinity,high=-Infinity;
  for(let y=0;y<size;y++)for(let x=0;x<size;x++){
   const dx=x+.5-size/2,dy=y+.5-size/2,index=y*size+x;let value,phase=0;
   if(g.family==='mirror')value=dx*Math.cos(g.axes[0])+dy*Math.sin(g.axes[0]);
   else{phase=mod(Math.atan2(dy,dx)+(g.family==='rotation'?Math.PI/2:0),2*Math.PI/g.n);if(g.family==='dihedral')phase=Math.min(phase,2*Math.PI/g.n-phase);value=Math.hypot(dx,dy)*Math.cos(phase);}
   projection[index]=value;phases[index]=phase;low=Math.min(low,value);high=Math.max(high,value);
  }
  for(let i=0;i<projection.length;i++){
   let color=colors[0];if(g.family==='dihedral'){const ramp=Math.min(phases[i]/(Math.PI/g.n),1)*(Math.min(g.n,colors.length)-1),index=Math.min(Math.floor(ramp),Math.min(g.n,colors.length)-2),f=ramp-index;color=colors[index].map((v,k)=>v*(1-f)+colors[index+1][k]*f);}
   const brightness=(high-projection[i])/Math.max(high-low,1e-9),dark=[2,1,3];for(let k=0;k<3;k++)image.data[i*4+k]=Math.round(dark[k]+(color[k]-dark[k])*brightness);image.data[i*4+3]=128;
  }
  ctx.putImageData(image,0,0);
  if(guides){
   const c=size/2,r=size*.8;ctx.lineWidth=size/256;ctx.setLineDash([]);
   g.axes.forEach((angle,index)=>{ctx.beginPath();ctx.moveTo(c-Math.cos(angle)*r,c-Math.sin(angle)*r);ctx.lineTo(c+Math.cos(angle)*r,c+Math.sin(angle)*r);ctx.strokeStyle='#101820';ctx.lineWidth=size/100;ctx.stroke();ctx.strokeStyle='rgb('+colors[index%colors.length].join(',')+')';ctx.lineWidth=size/240;ctx.stroke();});
   if(g.family==='rotation'){
    ctx.strokeStyle='#ffffffa8';ctx.lineWidth=size/300;ctx.setLineDash([size/80,size/80]);for(let i=0;i<g.n;i++){const a=-Math.PI/2+i*2*Math.PI/g.n;ctx.beginPath();ctx.moveTo(c,c);ctx.lineTo(c+Math.cos(a)*r,c+Math.sin(a)*r);ctx.stroke();}ctx.setLineDash([]);
    const a=-Math.PI/2,b=a+Math.min(2*Math.PI/g.n,.9*Math.PI),radius=size*.12;ctx.strokeStyle='white';ctx.lineWidth=size/180;ctx.beginPath();ctx.arc(c,c,radius,a,b);ctx.stroke();const x=c+Math.cos(b)*radius,y=c+Math.sin(b)*radius,tangent=b+Math.PI/2;ctx.beginPath();ctx.moveTo(x,y);ctx.lineTo(x-Math.cos(tangent-.5)*size*.025,y-Math.sin(tangent-.5)*size*.025);ctx.moveTo(x,y);ctx.lineTo(x-Math.cos(tangent+.5)*size*.025,y-Math.sin(tangent+.5)*size*.025);ctx.stroke();
   }
   ctx.fillStyle='white';ctx.beginPath();ctx.arc(c,c,size/180,0,Math.PI*2);ctx.fill();
  }
  return canvas;
 }
 function paint(){
  const curation=window.atlasDatasetCuration;if(!curation)return;
  for(const target of document.querySelectorAll('[data-manual-preview-key]')){
   const key=target.dataset.manualPreviewKey,map=window.MAPGEN_DATASETS?.maps.find(m=>m.key===key);if(!map)continue;const type=curation.visual(map).manualSymmetry,active=allowed()&&!!geometry(type)&&!hidden.has(key),inset=target.classList.contains('dataset-manual-inset');
   if(inset){target.hidden=!active||!target.closest('table');if(!target.closest('table')){target.querySelector('canvas')?.remove();target.querySelector('.manual-symmetry-caption')?.remove();continue;}}
   target.classList.toggle('dataset-manual-active',active);if(!active){target.querySelector('.manual-symmetry-layer')?.remove();target.querySelector('.manual-symmetry-caption')?.remove();delete target.dataset.manualSymmetry;continue;}
   if(target.dataset.manualSymmetry!==type||!target.querySelector('canvas')){
    if(!cache.has(type))cache.set(type,raster(type));let canvas=target.querySelector('.manual-symmetry-layer');if(!canvas){canvas=document.createElement('canvas');canvas.className='manual-symmetry-layer';canvas.width=canvas.height=512;target.append(canvas);}canvas.getContext('2d').drawImage(cache.get(type),0,0);canvas.setAttribute('role','img');canvas.setAttribute('aria-label','Manual symmetry preview: '+curation.labels[type]);target.dataset.manualSymmetry=type;
    let label=target.querySelector('.manual-symmetry-caption');if(!label){label=document.createElement('span');label.className='manual-symmetry-caption';target.append(label);}label.textContent='Manual preview · '+curation.labels[type];canvas.title='Centered geometric suggestion. '+(geometry(type).family==='rotation'?'Dashed rays mark rotation sectors.':'Colored lines mark mirror axes.');
   }
  }
 }
 window.atlasManualSymmetry={geometry,raster,paint,allowed,enabled:key=>!hidden.has(key),choose:key=>hidden.delete(key),toggle:(key,enabled)=>{enabled?hidden.delete(key):hidden.add(key);paint();}};
})();
