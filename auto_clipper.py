#!/usr/bin/env python3
"""
Auto-clipper: harvest verified German listening clips from remote video sources.
Usage: edit SOURCES below (or pass nothing), then run:
  ~/whisperenv/bin/python auto_clipper.py
No manual timestamp picking: it probes duration, spreads sample points across
the runtime, transcribes 8s windows with Whisper, keeps only confident German,
and patches app.js / standalone.html / index.html automatically.
"""
import json, subprocess, os, re, glob, random, base64, sys, urllib.parse, tempfile
from concurrent.futures import ThreadPoolExecutor

APP = "/home/deck/Downloads/Dutch_App/app"
HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, "_clipcache")
os.makedirs(WORK, exist_ok=True)
YTDLP = os.path.expanduser("~/whisperenv/bin/yt-dlp")
ENV = {k: v for k, v in os.environ.items()
       if k.lower() not in ("http_proxy", "https_proxy", "all_proxy")}
BAD = ["Copyright", "Untertitel", "Untertitlung", "B.K.", "G.M.", "Applaus", "Untertitelung"]
LEVEL = {"A1": 1, "A2": 2, "B1": 3, "B2": 4}

# ---------------------------------------------------------------- sources ---
# type: archive | okru | ccc   count: how many GOOD clips you want from it
SOURCES = [
    # demo run: counts set above current holdings so it harvests NEW clips
    dict(type="archive", id="rund-um-die-welt-mit-timon-pumbaa-de-dvd-rip",
         title="Timon & Pumbaa DE", cefr="A1", count=9),
    dict(type="archive", id="WE_FEED_THE_WORLD_DEUTSCH",
         title="We Feed The World DE", cefr="B1", count=6),
    # add more lines like:
    # dict(type="okru", id="8734620519010", title="Solino (2002)", cefr="B2", count=2),
    # dict(type="ccc", id="<media.ccc.de slug>", title="...", cefr="B2", count=3),
]

# ---------------------------------------------------------------- helpers ---
def curl(url):
    return subprocess.run(["curl", "-sL", "--max-time", "20", "-A", "Mozilla/5.0", url],
                          env=ENV, capture_output=True, text=True).stdout

def resolve_archive(ident):
    meta = json.loads(subprocess.check_output(
        ["curl", "-s", f"https://archive.org/metadata/{ident}/files"], text=True, timeout=20))
    files = meta if isinstance(meta, list) else meta.get("result", meta)
    for f in files:
        n = f.get("name", "")
        if n.lower().endswith(".mp4") and ".ia." not in n:
            return f"https://archive.org/download/{ident}/{urllib.parse.quote(n)}"
    return None

def resolve_ccc(slug):
    m = re.findall(r"https://cdn\.media\.ccc\.de[^\"]*?-deu-[^\"]*?\.mp4", curl(f"https://media.ccc.de/v/{slug}"))
    return m[0] if m else None

def probe_duration(url):
    try:
        out = subprocess.run(["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                              "-of", "csv=p=0", url], env=ENV, capture_output=True,
                             text=True, timeout=30).stdout.strip()
        return float(out)
    except Exception:
        return 0.0

def fetch_wav(url, ts, wav):
    if os.path.exists(wav) and os.path.getsize(wav) > 40000:
        return True
    try:
        subprocess.run(["ffmpeg", "-y", "-ss", str(ts), "-i", url, "-t", "8", "-vn",
                        "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", wav],
                       env=ENV, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=50)
        return os.path.exists(wav) and os.path.getsize(wav) > 40000
    except Exception:
        return False

def fetch_okru_segment(vid, ts, wav):
    raw = os.path.join(WORK, f"raw_{vid}_{ts}")
    try:
        subprocess.run([YTDLP, "--no-warnings", "--download-sections", f"*{ts}-{ts+8}",
                        "-o", raw + ".%(ext)s", f"https://ok.ru/video/{vid}"],
                       env=ENV, capture_output=True, timeout=150)
    except Exception:
        pass
    cands = [f for f in glob.glob(raw + ".*") if not f.endswith(".part")]
    if not cands:
        return False
    try:
        subprocess.run(["ffmpeg", "-y", "-i", cands[0], "-vn", "-acodec", "pcm_s16le",
                        "-ar", "16000", "-ac", "1", wav],
                       env=ENV, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        return os.path.exists(wav) and os.path.getsize(wav) > 40000
    except Exception:
        return False

def plan_timestamps(duration, want, span_cap=2400):
    """Spread sample points over the runtime, skipping intro/credits zones."""
    if duration >= 10:
        lo, hi = max(60, int(duration * 0.05)), min(int(duration * 0.95), span_cap)
    else:
        lo, hi = 60, span_cap
    slots = max(want * 3, 9)
    step = max(45, (hi - lo) // slots)
    return list(range(lo, hi, step))[:slots]

# ------------------------------------------------------------------ main ----
def main():
    from faster_whisper import WhisperModel
    model = WhisperModel("tiny", device="cpu", compute_type="int8")

    p_clips = os.path.join(APP, "clips_modern.json")
    clips = json.load(open(p_clips))
    ids = {c["clip_id"] for c in clips}

    def distractors(txt):
        w = txt.split(); out = []
        d = w.copy()
        if len(d) > 3:
            d[random.randint(1, len(d) - 2)] = random.choice(
                ["Haus", "Zeit", "Leute", "Wasser", "Tag", "Welt", "Stadt", "Geld"])
        else:
            d.insert(0, "Guten")
        out.append(" ".join(d))
        d = w.copy()
        if len(d) > 2:
            d[-1] = random.choice(["kommt.", "sieht.", "macht.", "bleibt.", "sagt."])
        else:
            d.append("heute.")
        out.append(" ".join(d))
        d = w.copy()
        if len(d) > 4:
            d[0] = random.choice(["Aber", "Doch", "Dann", "Jetzt", "Also"])
        else:
            d.insert(0, "Na")
        s = " ".join(d)
        out.append(s if s != txt else txt.replace(" ", " dann ", 1))
        return out

    for src in SOURCES:
        styp, ident = src["type"], src["id"]
        title, cefr, want = src["title"], src["cefr"], src.get("count", 3)
        prefix = re.sub(r"[^a-z0-9]", "", title.lower())[:10]

        if styp == "archive":
            url = resolve_archive(ident); lic = "Archive.org"
            page = f"https://archive.org/details/{ident}"
        elif styp == "ccc":
            url = resolve_ccc(ident); lic = "CC (media.ccc.de)"
            page = f"https://media.ccc.de/v/{ident}"
        else:
            url = None; lic = "OK.ru third-party upload — RIGHTS UNVERIFIED"
            page = f"https://ok.ru/video/{ident}"

        have = sum(1 for c in clips if c.get("attribution") == title)
        need = max(0, want - have)
        print(f"\n== {title} [{styp}] have={have} need={need}")
        if need == 0:
            continue
        if styp != "okru" and not url:
            print("   no stream URL resolved, skip"); continue

        dur = probe_duration(url) if url else 0.0
        tss = plan_timestamps(dur, need)
        print(f"   duration={int(dur)}s sampling {len(tss)} points: {tss[:6]}...")

        segdir = tempfile.mkdtemp(dir=WORK)
        jobs = [(t, os.path.join(segdir, f"{t}.wav")) for t in tss]
        def grab(j):
            t, wav = j
            ok = fetch_okru_segment(ident, t, wav) if styp == "okru" else fetch_wav(url, t, wav)
            return t, wav, ok
        with ThreadPoolExecutor(3) as ex:
            got = [r for r in ex.map(grab, jobs) if r[2]]

        kept = 0
        for t, wav, _ in sorted(got):
            if kept >= need:
                break
            cid = f"de_auto_{prefix}_{t}"
            if cid in ids:
                continue
            try:
                segs, info = model.transcribe(wav, language="de", beam_size=5)
                txt = " ".join(x.text.strip() for x in segs).strip()
            except Exception:
                continue
            if not (info.language == "de" and info.language_probability >= 0.75
                    and 15 <= len(txt) <= 160 and len(txt.split()) >= 4
                    and not any(b in txt for b in BAD)):
                continue
            is_ok = styp == "okru"
            entry = {
                "clip_id": cid, "provider": "html5",
                "video_id": ident, "video_url": None if is_ok else url,
                "embed_url": page,
                "title": f"{title} — {t}-{t+8}s",
                "start_time": t, "end_time": t + 8,
                "dutch_text": txt,
                "english_translation": "Translation: " + txt[:60],
                "cefr": cefr, "question_type": "listening",
                "correct_answer": txt, "wrong_answers": distractors(txt),
                "license": lic, "license_url": page, "attribution": title,
                "difficulty": LEVEL.get(cefr, 3),
                "verified": not is_ok,
            }
            entry["local_audio"] = ("data:audio/mpeg;base64,"
                                    + base64.b64encode(open(wav, "rb").read()).decode())
            clips.append(entry); ids.add(cid); kept += 1
            print(f"   +{t}s  {txt[:60]}")

    order = ["A1", "A2", "B1", "B2", "C1", "C2"]
    clips.sort(key=lambda c: (order.index(c["cefr"]) if c["cefr"] in order else 99, c["clip_id"]))
    jsd = json.dumps(clips, ensure_ascii=False)
    for name in ["app.js", "standalone.html", "index.html"]:
        fp = os.path.join(APP, name)
        t = open(fp).read()
        t = re.sub(r"let clips=\[.*?}\];", f"let clips={jsd};", t, flags=re.DOTALL)
        open(fp, "w").write(t)
    json.dump(clips, open(p_clips, "w"), ensure_ascii=False, indent=2)

    from collections import Counter
    print(f"\nTOTAL {len(clips)} clips |", dict(Counter(c['cefr'] for c in clips)),
          "| patched app.js standalone.html index.html")

if __name__ == "__main__":
    main()
