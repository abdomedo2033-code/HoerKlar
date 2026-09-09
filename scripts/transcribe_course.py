#!/usr/bin/env python3
"""Transcribe course_audio/*.mp3 to German .txt sidecars with faster-whisper.

Run: ~/whisperenv/bin/python scripts/transcribe_course.py [--model small]
Output: course_audio/<basename>.txt (one per mp3, skipped if already present
unless --force). The clip builder (scripts/build_course_clips.py) then turns
transcripts into real listening/cloze quizzes.
"""

import argparse
import glob
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIO_DIR = os.path.join(REPO, "course_audio")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="small",
                    help="faster-whisper model (tiny/base/small/...)")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    from faster_whisper import WhisperModel
    print(f"loading model {a.model} (cpu, int8)...", flush=True)
    model = WhisperModel(a.model, device="cpu", compute_type="int8")
    files = sorted(glob.glob(os.path.join(AUDIO_DIR, "*.mp3")))
    print(f"{len(files)} files", flush=True)
    done, skipped = 0, 0
    for i, f in enumerate(files):
        base = os.path.splitext(f)[0]
        out = base + ".txt"
        if os.path.exists(out) and not a.force:
            skipped += 1
            continue
        print(f"[{i + 1}/{len(files)}] {os.path.basename(f)} ...", flush=True)
        try:
            segments, _info = model.transcribe(
                f, language="de", beam_size=5,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 500})
            text = " ".join(s.text.strip() for s in segments).strip()
            with open(out, "w", encoding="utf-8") as fh:
                fh.write(text + "\n")
            print(f"    -> {len(text)} chars", flush=True)
            done += 1
        except Exception as e:
            print(f"    ERROR: {e}", flush=True)
    print(f"done: {done} transcribed, {skipped} skipped (already had .txt)")


if __name__ == "__main__":
    sys.exit(main())
