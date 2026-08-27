#!/usr/bin/env python3
"""Download low-res 5s video segments for OK.ru (audio-only) clips into
app/videos/<clip_id>.mp4 and set local_video relative path. Resumable."""
import json, subprocess, os, re, glob
from concurrent.futures import ThreadPoolExecutor

APP="/home/deck/Downloads/Dutch_App/app"
VD=os.path.join(APP,"videos"); os.makedirs(VD,exist_ok=True)
W="/home/deck/Downloads/Dutch_App/_clipcache5"
ENV={k:v for k,v in os.environ.items() if k.lower() not in ("http_proxy","https_proxy","all_proxy")}
YTDLP=os.path.expanduser("~/whisperenv/bin/yt-dlp")

p=os.path.join(APP,"clips_modern.json")
clips=json.load(open(p))
targets=[c for c in clips if c.get("license","").startswith("OK.ru") and not c.get("local_video")]
print(f"video targets: {len(targets)}")

def grab(c):
    cid=c["clip_id"]; ts=c["start_time"]; vid=c["video_id"]
    out=os.path.join(VD,cid+".mp4")
    if os.path.exists(out) and os.path.getsize(out)>30000: return cid,True
    raw=os.path.join(W,f"vid_{cid}")
    try:
        subprocess.run([YTDLP,"--no-warnings","--download-sections",f"*{ts}-{ts+5}",
            "-o",raw+".%(ext)s",f"https://ok.ru/video/{vid}"],env=ENV,capture_output=True,timeout=120)
    except Exception: pass
    cand=[f for f in glob.glob(raw+".*") if not f.endswith(".part")]
    if not cand: return cid,False
    try:
        subprocess.run(["ffmpeg","-y","-i",cand[0],"-vf","scale=-2:360","-c:v","libx264",
            "-preset","veryfast","-crf","30","-c:a","aac","-b:a","48k","-movflags","+faststart",out],
            env=ENV,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=60)
        return cid, os.path.exists(out) and os.path.getsize(out)>30000
    except Exception: return cid,False

ok=set()
with ThreadPoolExecutor(2) as ex:
    for cid,r in ex.map(grab,targets):
        if r: ok.add(cid)
print(f"fetched {len(ok)}/{len(targets)}")

for c in targets:
    if c["clip_id"] in ok:
        c["local_video"]=f"videos/{c['clip_id']}.mp4"

jsd=json.dumps(clips,ensure_ascii=False)
for name in ["app.js","standalone.html","index.html"]:
    fp=os.path.join(APP,name)
    t=open(fp).read()
    t=re.sub(r'let clips=\[.*?}\];',f'let clips={jsd};',t,flags=re.DOTALL)
    open(fp,'w').write(t)
json.dump(clips,open(p,"w"),ensure_ascii=False,indent=2)
print(f"local_video set on {len(ok)} clips | patched 3 files")
