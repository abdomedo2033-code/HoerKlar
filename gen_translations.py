#!/usr/bin/env python3
"""Attach real EN/AR translations to Nicos Weg clips from YouTube
auto-translated caption tracks (en-de / ar-de), plus .en.srt for Reclaim.
Run AFTER nico_all.py."""
import json, subprocess, os, re, glob

APP="/home/deck/Downloads/Dutch_App/app"
SUB="/home/deck/Downloads/Dutch_App/_clipcache/subs"; os.makedirs(SUB,exist_ok=True)
ENV={k:v for k,v in os.environ.items() if k.lower() not in ("http_proxy","https_proxy","all_proxy")}
YTDLP=os.path.expanduser("~/whisperenv/bin/yt-dlp")

def ts2sec(x):
    x=x.replace(",","."); p=x.split(":")
    try:
        if len(p)==3: return int(p[0])*3600+int(p[1])*60+float(p[2])
        if len(p)==2: return int(p[0])*60+float(p[1])
        return float(p[0])
    except Exception: return None

def parse(path):
    cues=[]; s=e=None; buf=[]
    for line in open(path,encoding="utf-8",errors="ignore"):
        line=line.rstrip()
        m=re.match(r"(\d[\d:,\.]*)\s*-->\s*(\d[\d:,\.]*)",line)
        if m:
            if s is not None and buf: cues.append((s,e," ".join(buf)))
            s,e=ts2sec(m.group(1)),ts2sec(m.group(2)); buf=[]; continue
        if not line or line.startswith(("WEBVTT","NOTE","Kind:","Language:")) or re.match(r"^\d+$",line): continue
        t=re.sub(r"<[^>]+>","",line).strip()
        if t and (not buf or buf[-1]!=t): buf.append(t)
    if s is not None and buf: cues.append((s,e," ".join(buf)))
    return cues

def text_for(cues,start,end):
    out=[]
    for s,e,t in cues:
        if s<end and e>start: out.append(t)
    txt=re.sub(r"\s+"," "," ".join(out)).strip()
    if len(txt)>200:
        cut=txt[:200]
        for pu in ("?","!","."):
            i=cut.rfind(pu)
            if i>40: cut=cut[:i+1]; break
        txt=cut.strip()
    return txt

p=os.path.join(APP,"clips_modern.json")
clips=json.load(open(p))
nico=[c for c in clips if c.get("section")=="nicos"]
eps={}
for c in nico:
    eps.setdefault(c["video_id"],[]).append(c)
print(f"nico clips {len(nico)} across {len(eps)} episodes")

got_en=got_ar=0
for vid,cset in eps.items():
    base=os.path.join(SUB,f"nt_{vid}")
    if not glob.glob(base+"*.vtt"):
        subprocess.run([YTDLP,"--no-warnings","--skip-download","--write-auto-subs",
            "--sub-langs","en-de,ar-de","--sub-format","vtt/best","-o",base,
            f"https://www.youtube.com/watch?v={vid}"],env=ENV,capture_output=True,timeout=120)
    fen=glob.glob(base+"*.en*.vtt") or glob.glob(base+"*.en.vtt")
    far=glob.glob(base+"*.ar*.vtt")
    ce=parse(fen[0]) if fen else []
    ca=parse(far[0]) if far else []
    for c in cset:
        tr={}
        if ce:
            en=text_for(ce,c["start_time"],c["end_time"])
            if len(en)>=6: tr["en"]=en; got_en+=1
        if ca:
            ar=text_for(ca,c["start_time"],c["end_time"])
            if len(ar)>=4: tr["ar"]=ar; got_ar+=1
        if tr: c["translations"]=tr

# Reclaim Your Face english subs
ryf=[c for c in clips if "Reclaim" in c.get("attribution","")]
fen=os.path.join(SUB,"ryf.de.srt").replace(".de.srt",".en.srt")
if ryf and not os.path.exists(fen):
    dl("https://cdn.media.ccc.de/events/rc3/2021/rc3-2021-import-1980-deu-eng-ita-Reclaim_Your_Face.en.srt",fen)
if ryf and os.path.exists(fen):
    ce=parse(fen)
    for c in ryf:
        en=text_for(ce,c["start_time"],c["end_time"])
        if len(en)>=6:
            tr=c.setdefault("translations",{}); tr["en"]=en; got_en+=1

jsd=json.dumps(clips,ensure_ascii=False)
for name in ['app.js','standalone.html','index.html']:
    fp=os.path.join(APP,name)
    t=open(fp).read()
    t=re.sub(r'let clips=\[.*?}\];',f'let clips={jsd};',t,flags=re.DOTALL)
    open(fp,'w').write(t)
json.dump(clips,open(p,"w"),ensure_ascii=False,indent=2)
tr=sum(1 for c in clips if c.get("translations"))
print(f"\ntranslations attached: en={got_en} ar={got_ar} | clips with translations: {tr}")
