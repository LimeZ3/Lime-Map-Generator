/* Global visual preferences change display only, never saved numeric data. */
const atlasDisplay = {background:10,mask:100};
try {
 const saved=JSON.parse(localStorage.getItem('mapgen-atlas-display-v1')||'null');
 for(const key of ['background','mask']) if(typeof saved?.[key]==='number' && Number.isFinite(saved[key])) atlasDisplay[key]=Math.max(0,Math.min(100,Math.round(saved[key])));
} catch {}
let sidebarFrame;
function positionAtlasDisplay() {
 const sidebar=document.querySelector('.shell > aside');
 if(!sidebar || matchMedia('(max-width:800px)').matches) return;
 sidebar.style.setProperty('--sidebar-top',Math.max(0,sidebar.getBoundingClientRect().top)+'px');
}
function applyAtlasDisplay() {
 document.documentElement.style.setProperty('--atlas-background-opacity',atlasDisplay.background/100);
 document.documentElement.style.setProperty('--atlas-mask-opacity',atlasDisplay.mask/100);
 for(const [key,id] of [['background','background-brightness'],['mask','mask-opacity']]){
  const input=document.getElementById(id);if(input) input.value=atlasDisplay[key];
  const output=document.getElementById(id+'-value');if(output) output.value=atlasDisplay[key]+'%';
  document.querySelectorAll('.'+id+'-value').forEach(el=>el.textContent=atlasDisplay[key]);
 }
 positionAtlasDisplay();
}
document.addEventListener('input',event=>{
 const key=event.target.id==='background-brightness'?'background':event.target.id==='mask-opacity'?'mask':null;
 if(!key) return;
 atlasDisplay[key]=Math.max(0,Math.min(100,Number(event.target.value)));
 applyAtlasDisplay();
 try {localStorage.setItem('mapgen-atlas-display-v1',JSON.stringify(atlasDisplay));} catch {}
});
for(const type of ['scroll','resize']) window.addEventListener(type,()=>{
 cancelAnimationFrame(sidebarFrame);sidebarFrame=requestAnimationFrame(positionAtlasDisplay);
},{passive:true});
applyAtlasDisplay();
