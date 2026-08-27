export type VMClip = { video_id:string; start_time:number; end_time:number };
declare global { interface Window { Vimeo:any } }
let loaded=false;
export function loadVimeoAPI(): Promise<void>{
  if(loaded && window.Vimeo) return Promise.resolve();
  return new Promise(res=>{
    const s=document.createElement('script');
    s.src="https://player.vimeo.com/api/player.js";
    s.onload=()=>{ loaded=true; res(); };
    document.head.appendChild(s);
  });
}
export function createVimeoPlayer(iframe:HTMLIFrameElement, clip:VMClip, onEnd:()=>void){
  const p=new window.Vimeo.Player(iframe);
  p.setCurrentTime(clip.start_time).then(()=>p.pause());
  p.on('timeupdate',(d:any)=>{
    if(d.seconds>=clip.end_time){ p.pause(); onEnd(); }
  });
  return p;
}
