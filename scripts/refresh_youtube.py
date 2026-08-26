import json, subprocess, re, pathlib
APP="app/clips_modern.json"
clips=json.load(open(APP))
for c in clips:
    if c.get("section")=="nicos" and c.get("video_id"):
        vid=c["video_id"]
        try:
            url=subprocess.check_output(["yt-dlp","--no-warnings","-g","-f","bv*[height<=360]+ba/b[height<=360]/b",f"https://www.youtube.com/watch?v={vid}"], text=True, timeout=30).strip().splitlines()[0]
            c["video_url"]=url
        except: pass
jsd=json.dumps(clips,ensure_ascii=False)
for name in ['app/standalone.html','index.html']:
    p=pathlib.Path(name)
    if p.exists():
        t=p.read_text(encoding='utf-8')
        t=re.sub(r'let clips=\[.*?}\];',f'let clips={jsd};',t,flags=re.DOTALL)
        p.write_text(t)
json.dump(clips,open(APP,"w"),ensure_ascii=False,indent=2)
print(f"refreshed {sum(1 for c in clips if c.get('section')=='nicos')} Nicos clips")
