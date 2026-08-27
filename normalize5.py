#!/usr/bin/env python3
"""Progressively upgrade every clip to a 5s single-moderate-sentence window.
NON-destructive: clips whose window can't be fetched/validated keep their
current form (marked done only after real upgrade). Re-run to continue."""
import json, subprocess, os, re, random, base64, glob
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor

APP="/home/deck/Downloads/Dutch_App/app"
W5="/home/deck/Downloads/Dutch_App/_clipcache5"; os.makedirs(W5,exist_ok=True)
ENV={k:v for k,v in os.environ.items() if k.lower() not in ("http_proxy","https_proxy","all_proxy")}
YTDLP=os.path.expanduser("~/whisperenv/bin/yt-dlp")
random.seed(11)
BAD=["Copyright","Untertitel","Untertitlung","B.K.","G.M.","Applaus"]
LEVEL={"A1":1,"A2":2,"B1":3,"B2":4}
A1_WORDS=set("""ich du er sie es wir ihr und ist sind bin hast hat habe nicht kein keine der die das ein eine einen
mit auf für von zu im in am an den dem ja nein gut hier heute morgen wasser haus zeit mann frau kind buch tag jahr
stadt land bitte danke hallo rot blau grün groß klein alt jung neu vater mutter bruder schwester freund hund katze
essen trinken schlafen gehen kommen sehen hören sprechen""".split())

def grade(txt):
    w=[x.strip(".,!?…:;«»()\"'").lower() for x in txt.split()]
    w=[x for x in w if x]
    if not w: return "B2"
    avg=sum(len(x) for x in w)/len(w)
    lr=sum(1 for x in w if len(x)>=9)/len(w)
    common=sum(1 for x in w if x in A1_WORDS)/len(w)
    s=0
    if avg>5.4: s+=1
    if avg>6.4: s+=1
    if lr>0.22: s+=1
    if len(txt)>70: s+=1
    if common<0.25: s+=1
    if common>0.55: s-=1
    return ["A1","A2","B1","B2"][max(0,min(3,s))]

def sent_ok(t):
    if not t or len(t)<20 or len(t)>105 or len(t.split())<3: return False
    if len(re.findall(r"[.!?]", t[:-1]))>0: return False
    return not any(b in t for b in BAD)

def f_archive(url,ts,wav):
    try:
        subprocess.run(["ffmpeg","-y","-ss",str(ts),"-i",url,"-t","5","-vn",
            "-acodec","pcm_s16le","-ar","16000","-ac","1",wav],
            env=ENV,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=38)
        return os.path.exists(wav) and os.path.getsize(wav)>25000
    except Exception: return False

def f_okru(vid,ts,wav,cid):
    raw=os.path.join(W5,f"raw_{cid}")
    try:
        subprocess.run([YTDLP,"--no-warnings","--download-sections",f"*{ts}-{ts+5}",
            "-o",raw+".%(ext)s",f"https://ok.ru/video/{vid}"],env=ENV,capture_output=True,timeout=110)
    except Exception: pass
    c=[f for f in glob.glob(raw+".*") if not f.endswith(".part")]
    if not c: return False
    try:
        subprocess.run(["ffmpeg","-y","-i",c[0],"-vn","-acodec","pcm_s16le","-ar","16000","-ac","1",wav],
            env=ENV,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=30)
        return os.path.exists(wav) and os.path.getsize(wav)>25000
    except Exception: return False

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
    except Exception:
        return cid,"","?",0.0

def distractors(txt):
    w=txt.split(); out=[]
    d=w.copy()
    if len(d)>3: d[random.randint(1,len(d)-2)]=random.choice(["Haus","Zeit","Leute","Wasser","Tag","Welt"])
    else: d.insert(0,"Guten")
    out.append(" ".join(d))
    d=w.copy()
    if len(d)>2: d[-1]=random.choice(["kommt.","sieht.","macht.","bleibt."])
    else: d.append("heute.")
    out.append(" ".join(d))
    d=w.copy()
    if len(d)>4: d[0]=random.choice(["Aber","Doch","Dann","Jetzt"])
    else: d.insert(0,"Na")
    s=" ".join(d); out.append(s if s!=txt else " ".join(w[:-1]+["heute."]))
    return out

def main():
    p=os.path.join(APP,"clips_modern.json")
    clips=json.load(open(p))
    todo=[c for c in clips if not c.get("v5")]
    print(f"to upgrade: {len(todo)} of {len(clips)}")

    arch=[(c,c["start_time"],os.path.join(W5,f"{c['clip_id']}.wav")) for c in todo if c.get("video_url")]
    okru=[(c,c["start_time"],os.path.join(W5,f"{c['clip_id']}.wav")) for c in todo if not c.get("video_url")]
    print(f"archive jobs {len(arch)} | okru jobs {len(okru)}")

    def ga(j):
        c,ts,wav=j; return c["clip_id"], f_archive(c["video_url"],ts,wav)
    def go(j):
        c,ts,wav=j; return c["clip_id"], f_okru(c["video_id"],ts,wav,c["clip_id"])
    ok=set()
    with ThreadPoolExecutor(4) as ex:
        for cid,r in ex.map(ga,arch): 
            if r: ok.add(cid)
    print(f"archive ok {sum(1 for c,_,_ in arch if c['clip_id'] in ok)}/{len(arch)}")
    with ThreadPoolExecutor(2) as ex:
        for cid,r in ex.map(go,okru):
            if r: ok.add(cid)
    print(f"windows total ok: {len(ok)}")

    wavs=[(os.path.join(W5,f"{cid}.wav"),cid) for cid in sorted(ok)]
    res={}
    with ProcessPoolExecutor(3,initializer=wh_init) as px:
        for cid,txt,lang,pb in px.map(wh_one,wavs,chunksize=2):
            res[cid]=(txt,lang,pb)

    pool=list({x.strip(".,!?…:") for c in clips for x in c.get("dutch_text","").split()
               if 4<=len(x.strip(".,!?…:"))<=14} ) or ["Wasser","Zeit","Leute"]
    upgraded=keptold=0
    for c in clips:
        if c.get("v5"): continue
        cid=c["clip_id"]
        txt,lang,pb=res.get(cid,("",None,0.0))
        if lang=="de" and pb>=0.75 and sent_ok(txt):
            ts=c["start_time"]
            c["end_time"]=ts+5
            c["dutch_text"]=txt; c["correct_answer"]=txt
            c["english_translation"]="Translation: "+txt[:60]
            lvl=grade(txt); c["cefr"]=lvl; c["difficulty"]=LEVEL[lvl]
            c["wrong_answers"]=distractors(txt)
            cw=random.choice([x.strip(".,!?…:") for x in txt.split() if len(x.strip(".,!?…:"))>=4] or [w[-1]])
            opts=set()
            while len(opts)<3:
                cand=random.choice(pool)
                if cand.lower()!=cw.lower(): opts.add(cand)
            c["cloze"]={"word":cw,"options":list(opts)+[cw]}
            c["question_type"]=random.choice(["listening","cloze"])
            wav=os.path.join(W5,f"{cid}.wav"); mp3=wav.replace(".wav",".mp3")
            if not os.path.exists(mp3):
                subprocess.run(["ffmpeg","-y","-i",wav,"-codec:a","libmp3lame","-b:a","48k","-ac","1",mp3],
                    env=ENV,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=20)
            if os.path.exists(mp3):
                c["local_audio"]="data:audio/mpeg;base64,"+base64.b64encode(open(mp3,'rb').read()).decode()
            c["v5"]=True; upgraded+=1
        else:
            keptold+=1

    order=["A1","A2","B1","B2","C1","C2"]
    clips.sort(key=lambda c:(order.index(c["cefr"]) if c["cefr"] in order else 99,c["clip_id"]))
    jsd=json.dumps(clips,ensure_ascii=False)
    for name in ["app.js","standalone.html","index.html"]:
        fp=os.path.join(APP,name)
        t=open(fp).read()
        t=re.sub(r'let clips=\[.*?}\];',f'let clips={jsd};',t,flags=re.DOTALL)
        open(fp,'w').write(t)
    json.dump(clips,open(p,"w"),ensure_ascii=False,indent=2)
    from collections import Counter
    print(f"\nupgraded {upgraded} | still old {keptold} | TOTAL {len(clips)}",
          dict(Counter(c['cefr'] for c in clips)))

if __name__=="__main__": main()
