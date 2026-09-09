#!/usr/bin/env python3
"""Build `server/data/clips_course.json` from a folder of course MP3s.

Covers the "course clips" request: the Menschen A1 audio shared via
Google Drive (https://drive.google.com/drive/folders/1rnUPDhwmGJlHjo7_Mjulp-ML0AoC2p10).

MP3s are copyrighted course material, so they are NOT committed to the
repo. Download them once, drop them in `course_audio/`, then run:

    python3 scripts/build_course_clips.py

Optional sidecars (same basename as the mp3):
    <name>.txt       German transcript  -> real listening/cloze quizzes
    <name>.en.txt    English translation -> translation quizzes
    <name>.ar.txt    Arabic translation  -> translation quizzes

Without a .txt the clip is still playable: the app shows a
"Listen and repeat / I listened (+5 XP)" self-check card
(`transcript_pending: true`) until you add the transcript and re-run.

Output: server/data/clips_course.json (+ manifest.json course entry).
Audio is played with the normal <video> element, so 0.75x slow,
autoplay loop, seek bar and the mobile layout all keep working.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(REPO, "server", "data")
AUDIO_EXTS = (".mp3", ".m4a", ".ogg", ".wav")

DRIVE_URL = "https://drive.google.com/drive/folders/1rnUPDhwmGJlHjo7_Mjulp-ML0AoC2p10"

# Small swap pool for single-word distractors (A1-ish German).
SWAP_POOL = ("Haus Zeit Mann Frau Kind Stadt Schule Lehrer Musik Film Tisch Fenster "
             "Straße Auto Zug Zimmer Küche Wasser Brot Milch Käse Apfel Suppe Fleisch "
             "Familie Freund Arbeit Morgen Abend Tag Woche Jahr Name Frage Antwort").split()


def slug(name):
    s = re.sub(r"[^a-z0-9 _-]", "", name.lower()).strip()
    s = s.replace(" ", "_").replace("-", "_")
    s = re.sub(r"_+", "_", s).strip("_")
    return s[:60] or "clip"


def duration_sec(path):
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=30)
        d = float((r.stdout or "").strip())
        if d > 0:
            return round(d, 2)
    except Exception:
        pass
    return 60.0


def read_sidecar(path):
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            return f.read().strip()
    except OSError:
        return ""


def distractors(correct):
    """3 single-word-swap variants of the correct sentence."""
    toks = correct.split()
    idxs = [i for i, w in enumerate(toks)
            if len(re.sub(r"[^\wäöüß]", "", w, flags=re.I)) >= 3]
    outs, seen = [], {correct}
    if not idxs:
        return [correct + " ja", correct + " wohl", correct + " schon"][:3]
    pool_i = 0
    guard = 0
    while len(outs) < 3 and guard < 60:
        guard += 1
        i = idxs[(pool_i // len(SWAP_POOL)) % len(idxs)]
        rep = SWAP_POOL[pool_i % len(SWAP_POOL)]
        pool_i += 1
        bare = re.sub(r"[^\wäöüß]", "", toks[i], flags=re.I)
        if not bare or rep.lower() == bare.lower():
            continue
        cand = toks[:i] + [rep + toks[i][len(bare):]] + toks[i + 1:]
        cand = " ".join(cand)
        if cand not in seen:
            seen.add(cand)
            outs.append(cand)
    while len(outs) < 3:
        outs.append(correct + " " + ("ja", "wohl", "schon")[len(outs)])
    return outs


def title_from_filename(base):
    t = re.sub(r"\.(mp3|m4a|ogg|wav)$", "", base, flags=re.I)
    t = t.replace("_", " ").strip()
    return t or base


def build(audio_dir, base_url, id_map=None, api_base=""):
    files = sorted(f for f in os.listdir(audio_dir)
                   if f.lower().endswith(AUDIO_EXTS))
    clips = []
    for fn in files:
        full = os.path.join(audio_dir, fn)
        base = os.path.splitext(fn)[0]
        dur = duration_sec(full)
        transcript = read_sidecar(os.path.join(audio_dir, base + ".txt"))
        en = read_sidecar(os.path.join(audio_dir, base + ".en.txt"))
        ar = read_sidecar(os.path.join(audio_dir, base + ".ar.txt"))
        local_url = base_url.rstrip("/") + "/" + fn
        # Stream from Drive when an ID map is given (nothing to host, nothing
        # in git); local_audio stays relative for offline/local use.
        if id_map and fn in id_map:
            if api_base:
                url = (api_base.rstrip("/") + "/api/course-audio?id="
                       + id_map[fn])
            else:
                url = ("https://drive.google.com/uc?export=download&id="
                       + id_map[fn])
        else:
            url = local_url
        cid = "course_" + slug(base)
        title = title_from_filename(fn)
        clip = {
            "clip_id": cid,
            "provider": "html5",
            "video_id": cid,
            "video_url": url,
            "audio_url": url,
            "local_audio": local_url,
            "embed_url": DRIVE_URL,
            "title": title,
            "start_time": 0.0,
            "end_time": dur,
            "cefr": "A1",
            "difficulty": 1,
            "verified": False,
            "section": "course",
            "license": "Course audio — personal study copy, not redistributed",
            "attribution": "Menschen A1 course audio (personal study copy)",
        }
        if transcript:
            clip.update({
                "dutch_text": transcript,
                "correct_answer": transcript,
                "wrong_answers": distractors(transcript),
                "transcript_source": os.path.join("course_audio", base + ".txt"),
            })
            tr = {}
            if en:
                tr["en"] = en
            if ar:
                tr["ar"] = ar
            if tr:
                clip["translations"] = tr
        else:
            clip.update({
                "dutch_text": "",
                "correct_answer": "",
                "wrong_answers": [],
                "transcript_pending": True,
                "transcript_source": "filename (needs transcription)",
            })
        clips.append(clip)
    return clips


def update_manifest(clips):
    mp = os.path.join(DATA, "manifest.json")
    try:
        man = json.load(open(mp, encoding="utf-8"))
    except (OSError, ValueError):
        man = {}
    blob = json.dumps(clips, ensure_ascii=False).encode("utf-8")
    man["course"] = {
        "count": len(clips),
        "sha1": hashlib.sha1(blob).hexdigest(),
        "bytes": len(blob),
    }
    json.dump(man, open(mp, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    return man.get("course")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--audio-dir", default=os.path.join(REPO, "course_audio"))
    ap.add_argument("--out", default=os.path.join(DATA, "clips_course.json"))
    ap.add_argument("--base-url", default="course_audio",
                    help="URL prefix for audio files as seen by the app")
    ap.add_argument("--id-map", default="",
                    help="JSON file mapping mp3 filename -> Google Drive file ID; "
                         "when set, video/audio URLs stream from Drive directly")
    ap.add_argument("--api-base", default="",
                    help="API base URL for the course-audio proxy "
                         "(e.g. https://hoerklar-api.onrender.com); when set, "
                         "clip URLs use <api>/api/course-audio?id=... which "
                         "re-serves Drive bytes as playable inline audio")
    ap.add_argument("--write-ids", default="",
                    help="write the allowlisted Drive IDs to this JSON file "
                         "(tracked server/course_ids.json feeds the proxy)")
    a = ap.parse_args()
    if not os.path.isdir(a.audio_dir):
        print(f"no audio dir yet: {a.audio_dir}")
        print(f"1. download the MP3s from {DRIVE_URL}")
        print("2. put them in course_audio/  (see course_audio/README.md)")
        print("3. re-run this script")
        return 1
    id_map = None
    if a.id_map:
        id_map = json.load(open(a.id_map, encoding="utf-8"))
        print(f"id map: {len(id_map)} entries (streaming from Drive)")
    clips = build(a.audio_dir, a.base_url, id_map, a.api_base)
    if not clips:
        print(f"no audio files in {a.audio_dir}")
        return 1
    if a.write_ids and id_map:
        ordered = sorted(set(id_map.values()))
        json.dump(ordered, open(a.write_ids, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print(f"wrote {a.write_ids}: {len(ordered)} allowlisted IDs")
    if os.path.exists(a.out):
        os.replace(a.out, a.out + ".bak")
    json.dump(clips, open(a.out, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    entry = update_manifest(clips)
    pending = sum(1 for c in clips if c.get("transcript_pending"))
    print(f"wrote {a.out}: {len(clips)} clips "
          f"({pending} transcript-pending, {len(clips) - pending} transcribed)")
    print(f"manifest course entry: {entry}")
    print("serve course_audio/ next to index.html (or copy into the APK "
          "assets) so the app can play the files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
