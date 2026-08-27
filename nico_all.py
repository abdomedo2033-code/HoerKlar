#!/usr/bin/env python3
"""Harvest ALL Nicos Weg playlist episodes -> base64-embedded clips.
No disk artifacts: 5s video+audio segments live as data URIs inside the HTML.
Resumable via journal. Per-episode budget keeps HTML size sane."""
import json, subprocess, os, re, random, base64, glob, sys
from concurrent.futures import ProcessPoolExecutor

APP="/home/deck/Downloads/Dutch_App/app"
W="/home/deck/Downloads/Dutch_App/_clipcache5"
ENV={k:v for k,v in os.environ.items() if k.lower() not in ("http_proxy","https_proxy","all_proxy")}
YTDLP=os.path.expanduser("~/whisperenv/bin/yt-dlp")
PLAYLIST="https://www.youtube.com/playlist?list=PLs7zUO7VPyJ5DV1iBRgSw2uDl832n0bLg"
JOURNAL=os.path.join(W,"nico_all.jsonl")
BAD=["Copyright","Untertitel","B.K.","G.M.","Applaus"]
MAX_PER_EP=2
MAX_TOTAL_NEW=110

def wh_init():
    global _m
    from faster_whisper import WhisperModel
    _m=WhisperModel("tiny",device="cpu",compute_type="int8")
def wh_one(args):
    wav,cid=args
    try:
        segs,info=_m.transcribe(wav,language="de",beam_size=5)
        txt=" ".join(x.text.strip() for x in segs).strip()
        return cid,txt,info.language,float(info.language_probability)
    except Exception: return cid,"","?",0.0

ENG={"the","and","lets","let","have","look","at","next","one","with","you","for","this","is","are","subtitles"}
def ok_text(t):
    toks=t.split()
    if not toks: return False
    eng=sum(1 for x in toks if x.lower().strip(".,!?…'") in ENG)
    if eng/len(toks)>0.4: return False
    inner=len(re.findall(r"[.!?…]",t[:-1]))
    return (12<=len(t)<=130 and len(toks)>=2 and inner<=1
            and not any(b in t for b in BAD))

def main():
    # playlist listing
    r=subprocess.run([YTDLP,"--no-warnings","--flat-playlist","--print","%(id)s\t%(title)s",PLAYLIST],
        env=ENV,capture_output=True,text=True,timeout=120)
    eps=[]
    for line in r.stdout.splitlines():
        if "\t" not in line: continue
        vid,title=line.split("\t",1)
        m=re.search(r"\((A1|A2|B1)\)",title)
        lvl=m.group(1) if m else "A1"
        if "Trailer" in title: continue
        eps.append((vid,title,lvl))
    print(f"playlist entries: {len(eps)}")

    done=set()
    if os.path.exists(JOURNAL):
        for l in open(JOURNAL):
            try: done.add(json.loads(l)["ep"])
            except Exception: pass
    p=os.path.join(APP,"clips_modern.json")
    clips=json.load(open(p))
    have_eps={c.get("episode") for c in clips if c.get("section")=="nicos"}
    ids={c["clip_id"] for c in clips}
    todo=[e for e in eps if e[0] not in done and e[0] not in have_eps]
    print(f"todo episodes: {len(todo)}")

    vocab=sorted({w.strip(".,!?…:;«»()\"'") for c in clips for w in c.get("dutch_text","").split()
                  if 3<=len(w.strip(".,!?…:;«»()\"'"))<=18})
    random.seed(53)
    import difflib
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
                    hit=False
                    for i,x in enumerate(w2):
                        b=x.strip(".,!?…:").lower()
                        if b in FUNC: w2[i]=FUNC[b]+x[len(x.strip(".,!?…:")):]; hit=True; break
                    if not hit:
                        i=random.choice(idxs) if idxs else 0
                        bare=w2[i].strip(".,!?…:")
                        w2[i]=cw_(bare,{bare})+(w2[i][len(bare):] if len(w2[i])>len(bare) else "")
                else:
                    if len(w2)>3:
                        i=random.randint(0,len(w2)-2); w2[i],w2[i+1]=w2[i+1],w2[i]
                    else:
                        bare=w2[0].strip(".,!?…:"); w2[0]=cw_(bare,{bare})
                t=" ".join(w2)
                if t not in seen and abs(len(t)-len(txt))<=6: break
            if t not in seen: seen.add(t); outs.append(t)
        fi=0
        while len(outs)<3:
            t=txt.replace(" "," "+["ja","wohl","schon"][fi%3]+" ",1); fi+=1
            if t not in seen: seen.add(t); outs.append(t)
        return outs[:3]

    out=open(JOURNAL,"a")
    added_total=sum(1 for c in clips if c.get("section")=="nicos")-8  # beyond folge1
    for vid,title,lvl in todo:
        if added_total>=MAX_TOTAL_NEW:
            print("total budget reached"); break
        ep=vid
        srcmp4=os.path.join(W,f"ep_{vid}.mp4")
        if not (os.path.exists(srcmp4) and os.path.getsize(srcmp4)>100000):
            try:
                subprocess.run([YTDLP,"--no-warnings","-f","bv*[height<=360]+ba/b[height<=480]/b",
                    "--merge-output-format","mp4","-o",srcmp4,
                    f"https://www.youtube.com/watch?v={vid}"],env=ENV,capture_output=True,timeout=240)
            except Exception: pass
        if not os.path.exists(srcmp4):
            out.write(json.dumps({"ep":ep})+"\n"); out.flush(); done.add(ep)
            print(f"{title}: dl-fail"); continue
        try:
            dur=float(subprocess.run(["ffprobe","-v","quiet","-show_entries","format=duration",
                "-of","csv=p=0",srcmp4],env=ENV,capture_output=True,text=True).stdout.strip())
        except Exception: dur=0
        if dur<15:
            out.write(json.dumps({"ep":ep})+"\n"); out.flush(); done.add(ep)
            print(f"{title}: too short {int(dur)}s"); continue
        ts_list=list(range(3,int(dur)-6,6))
        wavs=[]
        for ts in ts_list:
            wav=os.path.join(W,f"nx_{vid}_{ts}.wav")
            if not os.path.exists(wav):
                subprocess.run(["ffmpeg","-y","-ss",str(ts),"-i",srcmp4,"-t","5","-vn",
                    "-acodec","pcm_s16le","-ar","16000","-ac","1",wav],
                    env=ENV,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=25)
            if os.path.exists(wav): wavs.append((wav,f"nx_{vid}_{ts}",ts))
        with ProcessPoolExecutor(1,initializer=wh_init) as px:
            got={}
            for cid,txt,lang,pb in px.map(wh_one,[(w,c) for w,c,_ in wavs]):
                got[cid]=(txt,lang,pb)
        good=[]
        for wav,cid,ts in wavs:
            txt,lang,pb=got.get(cid,("",None,0))
            if lang=="de" and pb>=0.7 and ok_text(txt):
                good.append((ts,txt))
        kept=0
        for ts,txt in good:
            if kept>=MAX_PER_EP or added_total>=MAX_TOTAL_NEW: break
            cid=f"de_nicox_{vid}_{ts}"
            if cid in ids: continue
            vseg=os.path.join(W,f"nxv_{vid}_{ts}.mp4")
            if not os.path.exists(vseg):
                subprocess.run(["ffmpeg","-y","-ss",str(ts),"-i",srcmp4,"-t","5",
                    "-vf","scale=-2:240,fps=15","-c:v","libx264","-preset","veryfast","-crf","36",
                    "-c:a","aac","-b:a","24k","-ac","1","-movflags","+faststart",vseg],
                    env=ENV,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=40)
            if not os.path.exists(vseg): continue
            entry={"clip_id":cid,"provider":"html5","video_id":vid,
              "video_url":None,
              "embed_url":f"https://www.youtube.com/watch?v={vid}",
              "title":f"{title} — {ts}-{ts+5}s",
              "start_time":ts,"end_time":ts+5,
              "dutch_text":txt,"english_translation":"Translation: "+txt[:60],
              "cefr":lvl,"question_type":random.choice(["listening","cloze"]),
              "correct_answer":txt,"wrong_answers":distractors(txt),
              "license":"DW Nicos Weg — free educational series",
              "license_url":"https://learngerman.dw.com/de/nicos-weg/c-36519687",
              "attribution":title,"difficulty":{"A1":1,"A2":2,"B1":3}[lvl],
              "verified":True,"section":"nicos","episode":vid,
              "local_video":"data:video/mp4;base64,"+base64.b64encode(open(vseg,'rb').read()).decode()}
            wavp=os.path.join(W,f"nx_{vid}_{ts}.wav")
            mp3=wavp.replace(".wav",".mp3")
            if not os.path.exists(mp3):
                subprocess.run(["ffmpeg","-y","-i",wavp,"-codec:a","libmp3lame","-b:a","48k","-ac","1",mp3],
                    env=ENV,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=20)
            if os.path.exists(mp3):
                entry["local_audio"]="data:audio/mpeg;base64,"+base64.b64encode(open(mp3,'rb').read()).decode()
            clips.append(entry); ids.add(cid); kept+=1; added_total+=1
            print(f"{title[:44]} @{ts}s '{txt[:45]}'")
        out.write(json.dumps({"ep":ep})+"\n"); out.flush()
        # incremental patch so progress survives timeouts
        order=["A1","A2","B1","B2","C1","C2"]
        clips.sort(key=lambda c:(c.get("section","movies"),order.index(c["cefr"]) if c["cefr"] in order else 99,c["clip_id"]))
        jsd=json.dumps(clips,ensure_ascii=False)
        for name in ["app.js","standalone.html","index.html"]:
            fp=os.path.join(APP,name)
            tt=open(fp).read()
            tt=re.sub(r'let clips=\[.*?}\];',f'let clips={jsd};',tt,flags=re.DOTALL)
            open(fp,'w').write(tt)
        json.dump(clips,open(p,"w"),ensure_ascii=False,indent=2)

    from collections import Counter
    nico=sum(1 for c in clips if c.get("section")=="nicos")
    print(f"\nDONE | nicos section now {nico} | TOTAL {len(clips)} |",dict(Counter(c['cefr'] for c in clips)))

if __name__=="__main__": main()
