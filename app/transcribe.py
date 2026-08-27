#!/usr/bin/env python3
import argparse, subprocess, tempfile, os, json, sys
from pathlib import Path

def transcribe_url(url, start, end, lang="nl", model="base"):
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("need faster-whisper: ~/whisperenv/bin/pip install faster-whisper"); sys.exit(1)
    print(f"Downloading {url} ...")
    with tempfile.TemporaryDirectory() as td:
        video = os.path.join(td, "in.mp4")
        audio = os.path.join(td, "out.wav")
        subprocess.run(["curl","-L","-o",video,url], check=True)
        dur = end - start
        subprocess.run(["ffmpeg","-y","-ss",str(start),"-i",video,"-t",str(dur),"-vn","-acodec","pcm_s16le","-ar","16000","-ac","1",audio], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"Transcribing {dur}s with {model} ({lang}) ...")
        model_obj = WhisperModel(model, device="cpu", compute_type="int8")
        segments, info = model_obj.transcribe(audio, language=lang, beam_size=5)
        text = " ".join(s.text.strip() for s in segments).strip()
        print(f"LANG {info.language} p={info.language_probability:.2f}")
        print(f"TEXT: {text}")
        return text

if __name__ == "__main__":
    p=argparse.ArgumentParser(description="Transcribe Dutch clip segment for website (temp download, then delete)")
    p.add_argument("--url", required=True, help="remote mp4 url")
    p.add_argument("--start", type=float, required=True)
    p.add_argument("--end", type=float, required=True)
    p.add_argument("--lang", default="nl")
    p.add_argument("--model", default="base")
    p.add_argument("--update", help="path to app.js to patch clip with same start/end")
    args=p.parse_args()
    txt=transcribe_url(args.url, args.start, args.end, args.lang, args.model)
    if args.update:
        print(f"Would update {args.update} with verified text: {txt}")
