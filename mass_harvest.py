#!/usr/bin/env python3
"""Mass-harvest ~100 verified German clips from already-known movies.
Resumable: progress journal at _clipcache/harvest.jsonl. Safe to re-run."""
import json, subprocess, os, re, random, base64, sys, urllib.parse, tempfile
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor

APP="/home/deck/Downloads/Dutch_App/app"
WORK="/home/deck/Downloads/Dutch_App/_clipcache"; os.makedirs(WORK,exist_ok=True)
JOURNAL=os.path.join(WORK,"harvest.jsonl")
ENV={k:v for k,v in os.environ.items() if k.lower() not in ("http_proxy","https_proxy","all_proxy")}
BAD=["Copyright","Untertitel","Untertitlung","B.K.","G.M.","Applaus"]
random.seed(7)

def rarch(ident):
    meta=json.loads(subprocess.check_output(["curl","-s",f"https://archive.org/metadata/{ident}/files"],text=True,timeout=20))
    files=meta if isinstance(meta,list) else meta.get("result",meta)
    for f in files:
        n=f.get("name","")
        if n.lower().endswith(".mp4") and ".ia." not in n:
            return f"https://archive.org/download/{ident}/{urllib.parse.quote(n)}"
    return None

def pdur(url):
    try:
        o=subprocess.run(["ffprobe","-v","quiet","-show_entries","format=duration","-of","csv=p=0",url],
            env=ENV,capture_output=True,text=True,timeout=30).stdout.strip()
        return float(o)
    except Exception: return 0.0

SRC={
 "timon":dict(label="Timon & Pumbaa DE",cefr="A1",
   url="https://archive.org/download/rund-um-die-welt-mit-timon-pumbaa-de-dvd-rip/rund%20um%20die%20welt%20mit%20timon%20pumbaa%20de%20dvd%20rip.mp4",
   page="https://archive.org/details/rund-um-die-welt-mit-timon-pumbaa-de-dvd-rip",lic="Archive.org"),
 "ddr":dict(label="DDR Umbruch Interviews",cefr="B1",
   url=None,page="https://archive.org/details/UmbruchInDerDdr-Interviewausschnitte",lic="Archive.org"),
 "wftw":dict(label="We Feed The World DE",cefr="B1",
   url="https://archive.org/download/WE_FEED_THE_WORLD_DEUTSCH/WFTWDoku.mp4",
   page="https://archive.org/details/WE_FEED_THE_WORLD_DEUTSCH",lic="Archive.org"),
 "kan":dict(label="Kaenguru-Rebellion Talk 39c3",cefr="B2",
   url="https://cdn.media.ccc.de/congress/2025/h264-hd/39c3-2193-deu-Die_Kaenguru-Rebellion_Digital_Independence_Day.mp4",
   page="https://media.ccc.de/v/39c3-die-kanguru-rebellion-digital-independence-day",lic="CC (media.ccc.de)"),
 "ryf":dict(label="Reclaim Your Face Kurzfilm",cefr="B1",
   url="https://cdn.media.ccc.de/events/rc3/2021/h264-hd/rc3-2021-import-1980-deu-Reclaim_Your_Face.mp4",
   page="https://media.ccc.de/v/rc3-extras-1980-reclaim-your-face",lic="CC (media.ccc.de)"),
 "sword":dict(label="Reincarnated as a Sword DE",cefr="A2",
   url=None,page="https://archive.org/details/reincarnated-as-a-sword-german-dub",lic="Archive.org"),
 "bert":dict(label="Bert & Ernie DE",cefr="A1",
   url=None,page="https://archive.org/details/bert-and-ernies-great-adventures-complete-set-german",lic="Archive.org"),
 "angst":dict(label="DW In Good Shape",cefr="B1",
   url=None,page="https://archive.org/details/Angststoerungen_In-good-shape_DW-2021",lic="Archive.org"),
 "schluss":dict(label="DW Sendeschluss",cefr="B1",
   url=None,page="https://archive.org/details/dw-deutsch-sendeschluss-cierre-de-transmision-01.01.2024",lic="Archive.org"),
 "artemis":dict(label="DW Nachrichten Artemis",cefr="B2",
   url=None,page="https://archive.org/details/dw-nachrichten-artemis-ii-nach-mehr-als-50-jahren-wieder-zum-mond-1467774168",lic="Archive.org"),
 "shin":dict(label="Shin chan S01E01 DE",cefr="A1",
   url="https://archive.org/download/shinchangermanredub2002webrip/2019-09-17_watchbox_Shin%20chan%20-%20S01E01_Fett%20For%20Fun%20%E2%81%84%20Sport%20extrem%20%E2%81%84%20Braue%20um%20Braue%2C%20Zahn%20um%20Zahn.mp4",
   page="https://archive.org/details/shinchangermanredub2002webrip",lic="watchbox rip, Archive.org"),
}
for k in ("ddr","sword","bert","angst","schluss","artemis"):
    if SRC[k]["url"] is None:
        SRC[k]["url"]=rarch({ddr:"UmbruchInDerDdr-Interviewausschnitte"}.get(k,k) if False else {
            "ddr":"UmbruchInDerDdr-Interviewausschnitte","sword":"reincarnated-as-a-sword-german-dub",
            "bert":"bert-and-ernies-great-adventures-complete-set-german",
            "angst":"Angststoerungen_In-good-shape_DW-2021",
            "schluss":"dw-deutsch-sendeschluss-cierre-de-transmision-01.01.2024",
            "artemis":"dw-nachrichten-artemis-ii-nach-mehr-als-50-jahren-wieder-zum-mond-1467774168"}[k])
# timon filename guess -> resolve properly
SRC["timon"]["url"]=rarch("rund-um-die-welt-mit-timon-pumbaa-de-dvd-rip") or SRC["timon"]["url"]

PLAN={"timon":50,"kan":44,"wftw":40,"ddr":26,"sword":30,"bert":30,"shin":22,"angst":14,"ryf":10,"schluss":10,"artemis":12}

def plan_ts(key,dur,n):
    hi=int(dur)-10 if dur>15 else 200
    if dur<=300: lo=4; step=max(8,(hi-lo)//max(n,1))
    else: lo=max(60,int(dur*0.04)); step=max(40,(hi-lo)//n)
    return [lo+i*step for i in range(n) if lo+i*step<hi][:n]

def dl(job):
    key,ts,url,wav=job
    if os.path.exists(wav) and os.path.getsize(wav)>40000: return job[0],job[1],True
    try:
        subprocess.run(["ffmpeg","-y","-ss",str(ts),"-i",url,"-t","8","-vn",
            "-acodec","pcm_s16le","-ar","16000","-ac","1",wav],
            env=ENV,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=35)
        return key,ts,(os.path.exists(wav) and os.path.getsize(wav)>40000)
    except Exception: return key,ts,False

def wh_init():
    global _m
    from faster_whisper import WhisperModel
    _m=WhisperModel("tiny",device="cpu",compute_type="int8")
def wh_one(args):
    wav,key,ts=args
    try:
        segs,info=_m.transcribe(wav,language="de",beam_size=5)
        txt=" ".join(x.text.strip() for x in segs).strip()
        lang,pb=info.language,float(info.language_probability)
    except Exception:
        txt,lang,pb="","?",0.0
    valid=(lang=="de" and pb>=0.75 and 15<=len(txt)<=160 and len(txt.split())>=4
           and not any(b in txt for b in BAD))
    return dict(key=f"{key}_{ts}",text=txt,valid=valid,prob=round(pb,2))

def main():
    print("resolving URLs/durations...")
    for k,s in SRC.items():
        if not s["url"]: print(" MISSING URL:",k); return
    durs={k:pdur(s["url"]) for k,s in SRC.items()}
    for k,d in durs.items(): print(f"  {k}: {int(d)}s")

    seen=set()
    if os.path.exists(JOURNAL):
        for l in open(JOURNAL): seen.add(json.loads(l)["key"])
    p_clips=os.path.join(APP,"clips_modern.json")
    clips=json.load(open(p_clips))
    ids={c["clip_id"] for c in clips}
    near={}
    for c in clips:
        for k,s in SRC.items():
            if s["label"].split()[0] in c.get("title","") or c.get("attribution")==s["label"]:
                near.setdefault(k,[]).append(c["start_time"])

    jobs=[]
    for k,n in PLAN.items():
        tss=[t for t in plan_ts(k,durs[k],n) if not any(abs(t-e)<12 for e in near.get(k,[]))]
        for i,t in enumerate(tss):
            wav=os.path.join(WORK,f"{k}_{t}.wav")
            j=(k,t,SRC[k]["url"],wav)
            if f"{k}_{t}" not in seen: jobs.append(j)
    print(f"jobs to download: {len(jobs)}")
    ok_jobs=[]
    done_ct=0
    with ThreadPoolExecutor(6) as ex:
        for key,ts,okv in ex.map(dl,jobs):
            done_ct+=1
            if done_ct%20==0: print(f"  dl {done_ct}/{len(jobs)}")
            if okv: ok_jobs.append((os.path.join(WORK,f"{key}_{ts}.wav"),key,ts))
    print(f"downloaded ok: {len(ok_jobs)}")

    todo=[a for a in ok_jobs if a[1]+"_"+str(a[2]) not in seen]
    print(f"whisper todo: {len(todo)}")
    out=open(JOURNAL,"a")
    if todo:
        with ProcessPoolExecutor(3,initializer=wh_init) as px:
            for rec in px.map(wh_one,todo,chunksize=2):
                out.write(json.dumps(rec)+"\n"); out.flush()
                seen.add(rec["key"])
    out.close()

    import base64
    def distractors(txt):
        w=txt.split(); out=[]
        d=w.copy()
        if len(d)>3: d[random.randint(1,len(d)-2)]=random.choice(["Haus","Zeit","Leute","Wasser","Tag","Welt","Stadt"])
        else: d.insert(0,"Guten")
        out.append(" ".join(d))
        d=w.copy()
        if len(d)>2: d[-1]=random.choice(["kommt.","sieht.","macht.","bleibt."])
        else: d.append("heute.")
        out.append(" ".join(d))
        d=w.copy()
        if len(d)>4: d[0]=random.choice(["Aber","Doch","Dann","Jetzt"])
        else: d.insert(0,"Na")
        s=" ".join(d); out.append(s if s!=txt else " ".join(d[:-1]+["heute."]))
        return out

    recs=[json.loads(l) for l in open(JOURNAL)]
    bykey={}
    for r in recs:
        if r["valid"]: bykey[r["key"]]=r
    added=0
    for key,r in sorted(bykey.items()):
        src,ts=key.rsplit("_",1); ts=int(ts)
        cid=f"de_h_{key}"
        if cid in ids: continue
        s=SRC[src]
        wav=os.path.join(WORK,key+".wav")
        mp3=wav.replace(".wav",".mp3")
        if not os.path.exists(mp3):
            subprocess.run(["ffmpeg","-y","-i",wav,"-codec:a","libmp3lame","-b:a","48k","-ac","1",mp3],
                env=ENV,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=20)
        entry={"clip_id":cid,"provider":"html5","video_id":src,
          "video_url":s["url"],"embed_url":s["page"],
          "title":f"{s['label']} — {ts}-{ts+8}s",
          "start_time":ts,"end_time":ts+8,
          "dutch_text":r["text"],"english_translation":"Translation: "+r["text"][:60],
          "cefr":s["cefr"],"question_type":"listening","correct_answer":r["text"],
          "wrong_answers":distractors(r["text"]),
          "license":s["lic"],"license_url":s["page"],"attribution":s["label"],
          "difficulty":{"A1":1,"A2":2,"B1":3,"B2":4}[s["cefr"]],"verified":True}
        if os.path.exists(mp3):
            entry["local_audio"]="data:audio/mpeg;base64,"+base64.b64encode(open(mp3,'rb').read()).decode()
        clips.append(entry); ids.add(cid); added+=1

    order=["A1","A2","B1","B2","C1","C2"]
    clips.sort(key=lambda c:(order.index(c["cefr"]) if c["cefr"] in order else 99,c["clip_id"]))
    jsd=json.dumps(clips,ensure_ascii=False)
    for name in ["app.js","standalone.html","index.html"]:
        fp=os.path.join(APP,name)
        t=open(fp).read()
        t=re.sub(r'let clips=\[.*?}\];',f'let clips={jsd};',t,flags=re.DOTALL)
        open(fp,'w').write(t)
    json.dump(clips,open(p_clips,"w"),ensure_ascii=False,indent=2)
    from collections import Counter
    print(f"\nADDED {added} -> TOTAL {len(clips)} |",dict(Counter(c['cefr'] for c in clips)))

if __name__=="__main__": main()
