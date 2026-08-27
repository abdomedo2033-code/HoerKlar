export type YTClip = { video_id:string; start_time:number; end_time:number };
declare global { interface Window { YT:any; onYouTubeIframeAPIReady:()=>void } }
let ready=false; let queue:(()=>void)[]=[];
export function loadYTAPI(): Promise<void>{
  if(ready) return Promise.resolve();
  return new Promise(res=>{
    queue.push(res);
    if(document.querySelector('script[data-yt]')) return;
    const s=document.createElement('script');
    s.src="https://www.youtube.com/iframe_api";
    s.dataset.yt="1";
    document.head.appendChild(s);
    window.onYouTubeIframeAPIReady=()=>{
      ready=true; queue.forEach(f=>f()); queue=[];
    };
  });
}
export function createYTPlayer(el:HTMLElement, clip:YTClip, onEnd:()=>void){
  return new window.YT.Player(el,{
    videoId: clip.video_id,
    playerVars:{ modestbranding:1, rel:0, playsinline:1, origin: location.origin },
    events:{
      onReady:(e:any)=>{ e.target.seekTo(clip.start_time,true); e.target.pauseVideo(); },
      onStateChange:(e:any)=>{
        if(e.data===window.YT.PlayerState.PLAYING){
          const t=setInterval(()=>{
            const cur=e.target.getCurrentTime();
            if(cur>=clip.end_time){ e.target.pauseVideo(); clearInterval(t); onEnd(); }
          },100);
        }
      }
    }
  });
}
