import type { PlayerAdapter } from '../providers/types';
export class HTML5Player implements PlayerAdapter{
  private video: HTMLVideoElement; private end=0; private cb?:()=>void; private onTime=()=>{
    if(this.video.currentTime>=this.end){ this.video.pause(); this.cb?.(); this.video.removeEventListener('timeupdate', this.onTime); }
  };
  constructor(container:HTMLElement){
    this.video=document.createElement('video');
    this.video.controls=true; this.video.preload='metadata'; this.video.crossOrigin='anonymous';
    this.video.style.width='100%'; container.appendChild(this.video);
    if(typeof window!=='undefined' && (window as any).Hls) {/* hls.js handled externally */}
  }
  async load(id:string){ this.video.src=id; }
  async play(s:number,e:number){
    this.end=e; this.video.currentTime=s; await this.video.play();
    this.video.addEventListener('timeupdate', this.onTime);
  }
  async pause(){ this.video.pause(); }
  async seek(t:number){ this.video.currentTime=t; }
  currentTime(){ return this.video.currentTime; }
  onEnded(cb:()=>void){ this.cb=cb; }
  setRate(r:number){ this.video.playbackRate=r; }
}
