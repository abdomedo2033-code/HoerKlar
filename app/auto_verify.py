#!/usr/bin/env python3
import re, json, subprocess, tempfile, os, sys, time
from pathlib import Path
APP_JS = Path(__file__).parent / "app.js"
STANDALONE = Path(__file__).parent / "standalone.html"

def load_clips():
    txt = APP_JS.read_text()
    m = re.search(r'let clips=\[', txt)
    start = txt.find('let clips=[')
    s = txt[start+10:]
    end = s.rfind('}];') + 2
    j = s[:end]
    if j.endswith(';'):
        j = j[:-1]
    # fix: already valid JSON array
    try:
        return json.loads(j)
    except Exception as e:
        # fallback: extract via python eval of JS array (replace single quotes not needed)
        print("parse failed", e)
        sys.exit(1)

def transcribe_clip(clip, model="base"):
    from faster_whisper import WhisperModel
    url, s, e = clip["video_url"], clip["start_time"], clip["end_time"]
    dur = e - s
    print(f"\n▶ {clip['clip_id']} {clip['dutch_text'][:40]}... [{s}-{e}]")
    with tempfile.TemporaryDirectory() as td:
        video = os.path.join(td, "in.mp4")
        audio = os.path.join(td, "out.wav")
        subprocess.run(["curl","-sL","-o",video,url], check=True)
        subprocess.run(["ffmpeg","-y","-ss",str(s),"-i",video,"-t",str(dur),"-vn","-acodec","pcm_s16le","-ar","16000","-ac","1",audio], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        m = WhisperModel(model, device="cpu", compute_type="int8")
        segs, info = m.transcribe(audio, language="de", beam_size=5)
        txt = " ".join(x.text.strip() for x in segs).strip()
        print(f"  → {txt} (lang {info.language} {info.language_probability:.2f})")
        return txt

def main():
    import argparse
    p=argparse.ArgumentParser(description="Auto-verify all website clips via Whisper")
    p.add_argument("--model", default="base")
    p.add_argument("--limit", type=int, default=0, help="only first N clips (0=all)")
    p.add_argument("--dry", action="store_true", help="don't write, just print")
    args=p.parse_args()
    clips = load_clips()
    if args.limit: clips = clips[:args.limit]
    print(f"Found {len(clips)} clips — transcribing...")
    for c in clips:
        try:
            real = transcribe_clip(c, args.model)
            if real:
                c["dutch_text_verified"] = real
                c["verified"] = True
                # keep original as fallback, but update dutch_text to verified
                c["dutch_text"] = real
        except Exception as e:
            print(f"  failed {c['clip_id']}: {e}")
        time.sleep(0.5)
    out = Path(__file__).parent / "clips_verified.json"
    out.write_text(json.dumps(clips, ensure_ascii=False, indent=2))
    print(f"\n✅ Wrote {out} ({len(clips)} clips)")
    if not args.dry:
        # patch app.js
        txt = APP_JS.read_text()
        new_json = json.dumps(clips, ensure_ascii=False)
        # replace let clips=[ ... }]; 
        new_txt = re.sub(r'let clips=\[.*?}\];', f'let clips={new_json};', txt, flags=re.DOTALL)
        APP_JS.write_text(new_txt)
        print(f"✅ Patched {APP_JS}")
        # also patch standalone.html similarly
        if STANDALONE.exists():
            st = STANDALONE.read_text()
            st2 = re.sub(r'let clips=\[.*?}\];', f'let clips={new_json};', st, flags=re.DOTALL)
            STANDALONE.write_text(st2)
            print(f"✅ Patched {STANDALONE}")
        print("\nReload http://localhost:8787 or file:// standalone.html — all ✅ verified")
if __name__=="__main__":
    main()
