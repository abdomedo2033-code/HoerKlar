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

STOPWORDS = set("ich du er sie es wir ihr der die das ein eine einen einer und oder aber nicht kein keine keinen zu von auf an im in ist sind war waren werden wird habe hat haben mit für nach aus bei um als wie so auch noch nur schon immer nie jetzt dann dort hier mein dein sein unser euer mir mich dich dir uns ihm ihnen sich dem den man was wer wenn weil dass damit gern gerne mal bitte danke na ja nein doch denn am da den dann das des die ob".split())

# Large German distractors pool — same source as the browser's _dewords,
# so any swap looks like a plausible close word rather than "Haus/Zeit/Mann".
POOL = ("gestern heute morgen kommen gehen sehen sagen machen haben sein wollen können müssen wissen denken arbeiten spielen essen trinken schlafen sprechen lesen schreiben fahren fliegen laufen springen lachen weinen singen tanzen kaufen verkaufen finden geben nehmen bringen holen öffnen schließen wohnen lieben hassen helfen fragen antworten verstehen vergessen erinnern Geld Zeit Haus Buch Wasser Mann Frau Kind Freund Stadt Land Welt Arbeit Schule Lehrer Schüler Musik Film Tisch Stuhl Fenster Tür Straße Auto Zug Bahnhof Zimmer Küche sitzen stehen liegen schicken bekommen warten treffen besuchen reisen kochen backen schneiden legen stellen fühlen freuen sorgen rennen schwimmen wandern erzählen üben wiederholen hören sehen schauen gucken verlassen ankommen abfahren aufstehen aufwachen frühstücken klingeln läuten rufen melden erklären beschreiben berichten zeigen machen tun bringen holen nehmen geben schenken leihen bezahlen verkaufen kaufen bekommen finden suchen verlieren spielen gewinnen hoffen wünschen träumen studieren jobben verdienen sparen zahlen kosten rechnen feiern genießen dürfen sollen mögen bleiben fliegen reisen klettern Schein Glück Kleid Schuhe Jacke Mantel Hemd Hose Rock Pullover Socken Treppe Keller Dach Boden Wand Lampe Sessel Sofa Bett Schrank Regal Bild Uhr Heft Bleistift Tafel Apfel Banane Brot Käse Milch Wasser Saft Bier Wein Zucker Salz Pfeffer Suppe Salat Fleisch Wurst Brötchen Kuchen Torte Schokolade Eis Tomate Gurke Zwiebel Kartoffel Karotte Paprika Pilz Reis Nudeln Mehl Öl Eltern Mutter Vater Oma Opa Tante Onkel Bruder Schwester Familie Freunde Partner Nachbar Polizei Arzt Ärztin Apotheke Krankenhaus Flughafen Haltestelle Kreuzung Ampel Weg Richtung Platz Park Geschäft Laden Markt Bäckerei Supermarkt Kaufhaus".split())


def _sim_word(w, ex, pool=POOL):
    wl = w.lower()
    cand = [x for x in pool if x.lower() != wl and x.lower() not in ex and abs(len(x) - len(w)) <= 2 and x[0].lower() == wl[0].lower()]
    if not cand:
        cand = [x for x in pool if x.lower() != wl and x.lower() not in ex and abs(len(x) - len(w)) <= 2]
    if not cand:
        cand = [x for x in pool if x.lower() != wl and x.lower() not in ex]
    if not cand:
        return None
    cand.sort(key=lambda x: abs(len(x) - len(w)))
    import random as _r
    top = cand[:5]
    return _r.choice(top)


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
    """3 hard distractors: each swaps 2–3 close words at different positions,
    so you can't guess by majority — every option looks equally plausible."""
    import random as _r
    toks = correct.split()
    idxs = [i for i, w in enumerate(toks)
            if len(re.sub(r"[^\wäöüß]", "", w, flags=re.I)) >= 3
            and re.sub(r"[^\wäöüß]", "", w, flags=re.I).lower() not in STOPWORDS]
    if not idxs:
        idxs = [i for i, w in enumerate(toks)
                if len(re.sub(r"[^\wäöüß]", "", w, flags=re.I)) >= 3]
    if not idxs:
        return [correct + " ja", correct + " wohl", correct + " schon"][:3]
    n = len(toks)
    # user wants 3+ different words — so 3 swaps for normal sentences, 2 for tiny ones
    want = 3 if n >= 6 else 2
    want = min(want, len(idxs))
    outs, seen = [], {correct}
    used_per_pos = {i: set() for i in idxs}
    guard = 0
    while len(outs) < 3 and guard < 80:
        guard += 1
        chosen = _r.sample(idxs, want) if len(idxs) >= want else idxs[:]
        # shuffle to avoid always picking same positions together
        _r.shuffle(chosen)
        cand = toks[:]
        ok = True
        for i in chosen:
            m = re.match(r"^([\wäöüß]+)(.*)$", cand[i], flags=re.I)
            bare = m.group(1) if m else re.sub(r"[^\wäöüß]", "", cand[i], flags=re.I)
            suffix = m.group(2) if m else cand[i][len(bare):]
            if not bare:
                ok = False
                break
            ex = {bare.lower()} | used_per_pos[i]
            rep = _sim_word(bare, ex)
            if not rep:
                ok = False
                break
            cand[i] = rep + suffix
            used_per_pos[i].add(rep.lower())
        s = " ".join(cand)
        if not ok or s in seen:
            continue
        # keep distractors diverse — not sharing the exact same 2-word pattern
        too_close = False
        for o in outs:
            ot = o.split()
            diff = sum(1 for a, b in zip(cand, ot) if a != b)
            if diff < 2:
                too_close = True
                break
        if too_close:
            continue
        seen.add(s)
        outs.append(s)
    while len(outs) < 3:
        outs.append(correct + " " + ("ja", "wohl", "schon")[len(outs)])
    return outs


def title_from_filename(base):
    t = re.sub(r"\.(mp3|m4a|ogg|wav)$", "", base, flags=re.I)
    t = t.replace("_", " ").strip()
    return t or base


def course_order(fn):
    """Natural lesson order: '01 Lektion 10, ...' must come after Lektion 9,
    not after Lektion 1 (plain sorted() gets this wrong)."""
    m = re.search(r"lektion\s*(\d+)", fn, re.I)
    return (int(m.group(1)) if m else 999, fn.lower())


def build(audio_dir, base_url, id_map=None, api_base="",
          section="course", cefr="A1", title_prefix="", book_rank=0,
          book_tag=""):
    files = sorted((f for f in os.listdir(audio_dir)
                    if f.lower().endswith(AUDIO_EXTS)),
                   key=lambda fn: (book_rank,) + course_order(fn))
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
        # (Also tries with/without a leading "01 " — Drive listing names and
        # on-disk names don't always agree on the prefix.)
        fid = None
        if id_map:
            fid = (id_map.get(fn) or id_map.get("01 " + fn)
                   or id_map.get(fn[3:] if fn.startswith("01 ") else fn))
        if fid:
            if api_base:
                url = (api_base.rstrip("/") + "/api/course-audio?id=" + fid)
            else:
                url = ("https://drive.google.com/uc?export=download&id=" + fid)
        else:
            url = local_url
        tag = (re.sub(r"[^a-z0-9]+", "_", (book_tag or title_prefix or section).lower()).strip("_") + "_"
               if (book_tag or title_prefix or section) else "")
        cid = "course_" + tag + slug(base)
        title = title_from_filename(fn)
        if title_prefix:
            title = title_prefix + " · " + title
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
            "cefr": cefr,
            "difficulty": 1 if cefr == "A1" else 2,
            "verified": False,
            "section": section,
            "license": "Course audio — personal study copy, not redistributed",
            "attribution": "Menschen course audio (personal study copy)",
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


BOOK_ORDER = ["A1.1 AB", "A1.1 KB", "A1.2 AB", "B1.1 KB", "B1.2 KB"]


def merged_key(c):
    title = str(c.get("title") or "")
    rank = next((i for i, b in enumerate(BOOK_ORDER)
                 if title.startswith(b)), None)
    if rank is None:
        # legacy unprefixed A1.1 AB titles ("01 Lektion ...")
        rank = 0 if re.match(r"01 Lektion", title) else 99
    m = re.search(r"Lektion\s*(\d+)", title, re.I)
    lek = int(m.group(1)) if m else 999
    cefr_rank = {"A1": 0, "A2": 1, "B1": 2}.get(c.get("cefr"), 9)
    return (cefr_rank, rank, lek, title.lower())


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
    ap.add_argument("--section", default="course")
    ap.add_argument("--cefr", default="A1")
    ap.add_argument("--title-prefix", default="",
                    help="prefix shown before each clip title, e.g. 'A1.1 KB'")
    ap.add_argument("--book-rank", type=int, default=0,
                    help="orders books inside one section (0=A1.1 AB, ...)")
    ap.add_argument("--book-tag", default="",
                    help="namespaces clip_ids per book, e.g. a1_1_kb "
                         "(prevents Intro/Lektion collisions across books)")
    ap.add_argument("--merge-out", default="",
                    help="append built clips to this JSON file instead of "
                         "overwriting --out (keeps other books' clips)")
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
    clips = build(a.audio_dir, a.base_url, id_map, a.api_base,
                  a.section, a.cefr, a.title_prefix, a.book_rank,
                  a.book_tag)
    if not clips:
        print(f"no audio files in {a.audio_dir}")
        return 1
    if a.write_ids and id_map:
        ordered = set(sorted(set(id_map.values())))
        if os.path.exists(a.write_ids):
            try:
                ordered.update(json.load(open(a.write_ids, encoding="utf-8")))
            except (OSError, ValueError):
                pass
        ordered = sorted(ordered)
        json.dump(ordered, open(a.write_ids, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print(f"wrote {a.write_ids}: {len(ordered)} allowlisted IDs")
    out_path = a.merge_out or a.out
    if a.merge_out and os.path.exists(a.merge_out):
        old = json.load(open(a.merge_out, encoding="utf-8"))
        have = {c["clip_id"] for c in clips}
        clips = sorted([c for c in old if c.get("clip_id") not in have]
                       + clips, key=merged_key)
        print(f"merged with {a.merge_out}")
    if os.path.exists(out_path):
        os.replace(out_path, out_path + ".bak")
    json.dump(clips, open(out_path, "w", encoding="utf-8"),
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
