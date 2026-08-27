#!/usr/bin/env python3
"""Replace Whisper transcripts with real subtitle text where available."""
import json, subprocess, os, re, glob, random, difflib

APP="/home/deck/Downloads/Dutch_App/app"
SUB="/home/deck/Downloads/Dutch_App/_clipcache/subs"; os.makedirs(SUB,exist_ok=True)
ENV={k:v for k,v in os.environ.items() if k.lower() not in ("http_proxy","https_proxy","all_proxy")}
YTDLP=os.path.expanduser("~/whisperenv/bin/yt-dlp")

def dl(url,out):
    if os.path.exists(out) and os.path.getsize(out)>200: return True
    r=subprocess.run(["curl","-sL","--max-time","30","-A","Mozilla/5.0",url,"-o",out],env=ENV)
    return os.path.exists(out) and os.path.getsize(out)>200

# 1 fetch all subtitle files -------------------------------------------------
files={}
files["kan"]=os.path.join(SUB,"kan.deu.vtt")
dl("https://static.media.ccc.de/media/congress/2025/2193-514cda00-fd8e-5417-ba56-a882572a660e-deu.vtt",files["kan"])
files["ryf"]=os.path.join(SUB,"ryf.de.srt")
dl("https://cdn.media.ccc.de/events/rc3/2021/rc3-2021-import-1980-deu-eng-ita-Reclaim_Your_Face.de.srt",files["ryf"])
files["ddr"]=os.path.join(SUB,"ddr.asr.srt")
dl("https://archive.org/download/UmbruchInDerDdr-Interviewausschnitte/Interviewausschnitte.asr.srt",files["ddr"])
nico=os.path.join(SUB,"nico1.de.vtt")
if not os.path.exists(nico):
    subprocess.run([YTDLP,"--no-warnings","--skip-download","--write-auto-subs","--sub-langs","de",
        "--sub-format","vtt","-o",os.path.join(SUB,"nico1"),
        "https://www.youtube.com/watch?v=dC6ZGLzdaTs"],env=ENV,capture_output=True,timeout=120)
got=[f for f in glob.glob(os.path.join(SUB,"nico1*.vtt"))]
if got: files["nico"]=got[0]

for k,f in files.items():
    print(k, os.path.getsize(f) if os.path.exists(f) else "MISSING")

# 2 parse cues ----------------------------------------------------------------
def ts2sec(x):
    x=x.replace(",",".")
    p=x.split(":")
    try:
        if len(p)==3: return int(p[0])*3600+int(p[1])*60+float(p[2])
        if len(p)==2: return int(p[0])*60+float(p[1])
        return float(p[0])
    except Exception: return None

def parse(path):
    cues=[]
    cur_s=cur_e=None; buf=[]
    for line in open(path,encoding="utf-8",errors="ignore"):
        line=line.rstrip()
        m=re.match(r"(\d[\d:,\.]*)\s*-->\s*(\d[\d:,\.]*)",line)
        if m:
            if cur_s is not None and buf: cues.append((cur_s,cur_e," ".join(buf)))
            cur_s,cur_e=ts2sec(m.group(1)),ts2sec(m.group(2)); buf=[]
            continue
        if not line or line.startswith(("WEBVTT","NOTE","Kind:","Language:")) or re.match(r"^\d+$",line):
            continue
        t=re.sub(r"<[^>]+>","",line).strip()
        if t and (not buf or buf[-1]!=t): buf.append(t)
    if cur_s is not None and buf: cues.append((cur_s,cur_e," ".join(buf)))
    return cues

cues={k:parse(f) for k,f in files.items() if os.path.exists(f)}
for k,c in cues.items(): print(k,len(c),"cues")

# 3 match clips ----------------------------------------------------------------
def text_for(key,start,end):
    out=[]
    for s,e,t in cues[key]:
        if s<end and e>start: out.append(t)
    txt=" ".join(out)
    txt=re.sub(r"\s+"," ",txt).strip()
    # drop leading partial duplicated from previous cue already included
    return txt

vocab=None
def build_vocab(clips):
    global vocab
    vocab=sorted({w.strip(".,!?…:;«»()\"'") for c in clips for w in c.get("dutch_text","").split()
                  if 3<=len(w.strip(".,!?…:;«»()\"'"))<=18})
random.seed(41)
def cw_(w,ex):
    cand=[v for v in vocab if abs(len(v)-len(w))<=1 and v.lower()!=w.lower() and v not in ex]
    m=difflib.get_close_matches(w,cand,n=8,cutoff=0.0)
    return random.choice(m[:6]) if m else (random.choice(cand) if cand else w+"n")
FUNC={"der":"die","die":"der","das":"der","ein":"eine","ist":"war","und":"oder","nicht":"nie","ich":"er"}
def distractors(txt):
    words=txt.split(); outs=[]; seen={txt}
    for s in range(3):
        for attempt in range(8):
            w2=words.copy()
            idxs=[i for i,x in enumerate(w2) if len(x.strip(".,!?…:"))>=3]
            if s==0 and idxs:
                i=max(idxs,key=lambda i:len(w2[i])); bare=w2[i].strip(".,!?…:")
                w2[i]=cw_(bare,{bare})+w2[i][len(bare):]
            elif s==1:
                done=False
                for i,x in enumerate(w2):
                    b=x.strip(".,!?…:").lower()
                    if b in FUNC: w2[i]=FUNC[b]+x[len(x.strip(".,!?…:")):]; done=True; break
                if not done and idxs:
                    i=random.choice(idxs); bare=w2[i].strip(".,!?…:")
                    w2[i]=cw_(bare,{bare})+(w2[i][len(bare):] if len(w2[i])>len(bare) else "")
            elif len(w2)>3:
                i=random.randint(0,len(w2)-2); w2[i],w2[i+1]=w2[i+1],w2[i]
            t=" ".join(w2)
            if t not in seen and abs(len(t)-len(txt))<=8: break
        if t not in seen: seen.add(t); outs.append(t)
    fi=0
    while len(outs)<3:
        t=txt.replace(" "," "+["ja","wohl","schon"][fi%3]+" ",1); fi+=1
        if t not in seen: seen.add(t); outs.append(t)
    return outs[:3]

p=os.path.join(APP,"clips_modern.json")
clips=json.load(open(p))
build_vocab(clips)

MAP=[("nicos","nico"),("Kaenguru","kan"),("Reclaim","ryf"),("DDR Umbruch","ddr")]
replaced=0
for c in clips:
    key=None
    for marker,k in MAP:
        if c.get("section")==marker or c.get("attribution","").find(marker)>=0:
            key=k; break
    if not key or key not in cues: continue
    txt=text_for(key,c["start_time"],c["end_time"])
    if not txt or len(txt)<8: continue
    if len(txt)>170:
        cut=txt[:170]
        for punct in ("?","!","."):
            idx=cut.rfind(punct)
            if idx>40: cut=cut[:idx+1]; break
        txt=cut.strip()
    old=c["dutch_text"]
    c["dutch_text"]=txt; c["correct_answer"]=txt
    c["english_translation"]="Translation: "+txt[:60]
    c["wrong_answers"]=distractors(txt)
    c["transcript_source"]="official_subs" if key!="ddr" else "archive_asr_subs"
    replaced+=1
    if replaced<=12: print(f"[{key}] {old[:38]} -> {txt[:48]}")

jsd=json.dumps(clips,ensure_ascii=False)
for name in ['app.js','standalone.html','index.html']:
    fp=os.path.join(APP,name)
    t=open(fp).read()
    t=re.sub(r'let clips=\[.*?}\];',f'let clips={jsd};',t,flags=re.DOTALL)
    open(fp,'w').write(t)
json.dump(clips,open(p,"w"),ensure_ascii=False,indent=2)
print(f"\nsubtitle-accurate replacements: {replaced} | total {len(clips)}")
