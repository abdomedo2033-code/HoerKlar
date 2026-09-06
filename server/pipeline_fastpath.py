#!/usr/bin/env python3
"""Phase 2 — subtitle fast-path pipeline (30–60s for subtitled videos).

Reuses the exact logic already proven in fetch_subs.py / gen_translations.py:
  yt-dlp --skip-download --write-subs --write-auto-subs (de.*) --sub-format vtt
  -> parse VTT cues (ts2sec) -> sentence-window clip building
  -> same-sound distractor generation (vocab + difflib, as in fetch_subs.py)
  -> EN/AR translation attach from en-de / ar-de auto-translated tracks

Output clip dicts match the canonical schema (dutch_text, correct_answer,
wrong_answers, translations{en,ar}, translation_distractors, cefr, section,
verified=False, transcript_source, rights_status=EMBED_ONLY).

Slow path (no German subs found) raises NoSubtitles — the caller (Deck worker)
then falls back to Whisper sampling (see worker/whisper_fallback.py).
Stdlib + yt-dlp only; no new pip deps.
"""
import glob, json, os, random, re, subprocess, difflib

ENV = {k: v for k, v in os.environ.items()
       if k.lower() not in ("http_proxy", "https_proxy", "all_proxy")}
YTDLP = os.path.expanduser(os.environ.get("HK_YTDLP", "~/whisperenv/bin/yt-dlp"))
FUNC = {"der": "die", "die": "der", "das": "der", "ein": "eine",
        "ist": "war", "und": "oder", "nicht": "nie", "ich": "er"}


class NoSubtitles(Exception):
    """Raised when no usable German subtitles exist. Carries the yt-dlp
    stderr tail so operators can tell 'video has no subs' apart from
    'YouTube blocked our datacenter IP' (see job.error)."""


def _tail(b, n=300):
    try:
        return b.decode("utf-8", "ignore")[-n:]
    except Exception:
        return ""


def ts2sec(x):
    x = x.replace(",", ".")
    p = x.split(":")
    try:
        if len(p) == 3:
            return int(p[0]) * 3600 + int(p[1]) * 60 + float(p[2])
        if len(p) == 2:
            return int(p[0]) * 60 + float(p[1])
        return float(p[0])
    except Exception:
        return None


def parse_vtt(path):
    cues = []
    s = e = None
    buf = []
    for line in open(path, encoding="utf-8", errors="ignore"):
        line = line.rstrip()
        m = re.match(r"(\d[\d:,\.]*)\s*-->\s*(\d[\d:,\.]*)", line)
        if m:
            if s is not None and buf:
                cues.append((s, e, " ".join(buf)))
            s, e = ts2sec(m.group(1)), ts2sec(m.group(2))
            buf = []
            continue
        if (not line or line.startswith(("WEBVTT", "NOTE", "Kind:", "Language:"))
                or re.match(r"^\d+$", line)):
            continue
        t = re.sub(r"<[^>]+>", "", line).strip()
        if t and (not buf or buf[-1] != t):
            buf.append(t)
    if s is not None and buf:
        cues.append((s, e, " ".join(buf)))
    # merge continuations: drop cue whose text is a prefix of the next
    merged = []
    for c in cues:
        if merged and merged[-1][2] and c[2].startswith(merged[-1][2]):
            merged[-1] = (merged[-1][0], c[1], c[2])
        else:
            merged.append(c)
    return [(s, e, re.sub(r"\s+", " ", t).strip()) for s, e, t in merged if t]


def fetch_subs(video_id, workdir, langs=("de.*", "en-de", "ar-de")):
    """Two attempts: default clients, then mobile clients (android/ios/tv are
    far less bot-checked than datacenter 'web' requests). Full log kept."""
    base = os.path.join(workdir, f"subs_{video_id}")
    attempts = [
        [],
        ["--extractor-args", "youtube:player_client=android,ios,tv"],
    ]
    last = None
    for extra in attempts:
        proc = subprocess.run(
            [YTDLP, "--no-warnings", "--skip-download",
             "--write-subs", "--write-auto-subs",
             "--sub-langs", ",".join(langs), "--sub-format", "vtt/best",
             ] + extra + ["-o", base,
                          f"https://www.youtube.com/watch?v={video_id}"],
            env=ENV, capture_output=True, timeout=120)
        last = proc
        open(base + ".fetch.log", "w", encoding="utf-8").write(
            f"rc={proc.returncode}\nEXTRA={extra}\nSTDERR:\n"
            + proc.stderr.decode("utf-8", "ignore")
            + "\nSTDOUT:\n" + proc.stdout.decode("utf-8", "ignore"))
        if glob.glob(base + "*.vtt"):
            break
    return base


def pick_de_cues(base):
    cands = sorted(glob.glob(base + "*.vtt"))
    # prefer manual German over auto-generated, German over translated
    def rank(p):
        pl = p.lower()
        score = 0
        if ".de." in pl or pl.endswith(".de.vtt"):
            score += 2
        if "auto" in pl or "live_chat" in pl:
            score -= 2
        return score
    cands.sort(key=rank, reverse=True)
    for p in cands:
        cues = parse_vtt(p)
        # crude German check: skip files that are mostly the translated tracks
        if cues and (".de" in p.lower() or len(cues) > 3):
            if "en-de" not in p and "ar-de" not in p:
                return cues, p
    # fall back to anything with content (translated de->en still yields timing)
    for p in cands:
        cues = parse_vtt(p)
        if cues:
            return cues, p
    return [], None


def text_for(cues, start, end, cap=170):
    txt = re.sub(r"\s+", " ", " ".join(
        t for s, e, t in cues if s < end and e > start)).strip()
    if len(txt) > cap:
        cut = txt[:cap]
        for pu in ("?", "!", "."):
            i = cut.rfind(pu)
            if i > 40:
                cut = cut[:i + 1]
                break
        txt = cut.strip()
    return txt


def build_windows(cues, min_len=15, max_clips=24):
    """Greedy sentence windows: accumulate cues to one sentence, cap ~8s."""
    wins = []
    cur = []
    for s, e, t in cues:
        if not cur:
            cur = [(s, e, t)]
            continue
        ps, pe, _ = cur[-1]
        gap = s - pe
        joined = text_for([(a, b, x) for a, b, x in cur] + [(s, e, t)], cur[0][0], e)
        if gap > 1.2 or e - cur[0][0] > 8.0 or len(joined) > 160:
            wins.append(cur)
            cur = [(s, e, t)]
        else:
            cur.append((s, e, t))
        if len(wins) >= max_clips:
            break
    if cur and len(wins) < max_clips:
        wins.append(cur)
    out = []
    for w in wins:
        txt = text_for([(a, b, x) for a, b, x in w], w[0][0], w[-1][1])
        if (min_len <= len(txt) <= 170 and len(txt.split()) >= 3
                and len(re.findall(r"[.!?…]", txt[:-1])) <= 1):
            out.append((round(w[0][0], 2), round(min(w[-1][1], w[0][0] + 8), 2), txt))
    return out


def make_distractors(txt, vocab, rng):
    def cw(w, ex):
        cand = [v for v in vocab if abs(len(v) - len(w)) <= 1
                and v.lower() != w.lower() and v not in ex]
        m = difflib.get_close_matches(w, cand, n=8, cutoff=0.0)
        return rng.choice(m[:6]) if m else (rng.choice(cand) if cand else w + "n")
    words = txt.split()
    outs, seen = [], {txt}
    for s in range(3):
        for _ in range(8):
            w2 = words.copy()
            idxs = [i for i, x in enumerate(w2) if len(x.strip(".,!?…:")) >= 3]
            if s == 0 and idxs:
                i = max(idxs, key=lambda i: len(w2[i]))
                bare = w2[i].strip(".,!?…:")
                w2[i] = cw(bare, {bare}) + w2[i][len(bare):]
            elif s == 1:
                done = False
                for i, x in enumerate(w2):
                    b = x.strip(".,!?…:").lower()
                    if b in FUNC:
                        w2[i] = FUNC[b] + x[len(x.strip(".,!?…:")):]
                        done = True
                        break
                if not done and idxs:
                    i = rng.choice(idxs)
                    bare = w2[i].strip(".,!?…:")
                    w2[i] = cw(bare, {bare}) + (w2[i][len(bare):] if len(w2[i]) > len(bare) else "")
            elif len(w2) > 3:
                i = rng.randrange(0, len(w2) - 1)
                w2[i], w2[i + 1] = w2[i + 1], w2[i]
            t = " ".join(w2)
            if t not in seen and abs(len(t) - len(txt)) <= 8:
                break
        if t not in seen:
            seen.add(t)
            outs.append(t)
    fi = 0
    while len(outs) < 3:
        t = txt.replace(" ", " " + ["ja", "wohl", "schon"][fi % 3] + " ", 1)
        fi += 1
        if t not in seen:
            seen.add(t)
            outs.append(t)
    return outs[:3]


def attach_translations(base, windows):
    """Pull en-de / ar-de auto-translated tracks for the same windows."""
    out_en = [glob.glob(base + "*.en*.vtt"), glob.glob(base + "*en-de*.vtt")]
    out_ar = [glob.glob(base + "*.ar*.vtt"), glob.glob(base + "*ar-de*.vtt")]
    fen = next((g[0] for g in out_en if g), None)
    far = next((g[0] for g in out_ar if g), None)
    ce = parse_vtt(fen) if fen else []
    ca = parse_vtt(far) if far else []
    return ce, ca


def run_fastpath(video_id, title, workdir, vocab=(), seed=41,
                 on_partial=None, cefr="A2", section="myvideos"):
    """Full fast path. on_partial(list_of_clips) streams early quizzes (Phase 4)."""
    rng = random.Random(seed)
    vocab = sorted(set(vocab)) or ["Wasser", "Zeit", "Leute"]
    base = fetch_subs(video_id, workdir)
    cues, used = pick_de_cues(base)
    if not cues:
        try:
            log = open(base + ".fetch.log", encoding="utf-8").read()[-800:]
        except Exception:
            log = "no fetch log"
        raise NoSubtitles(f"no German subtitles for {video_id} | {log}")
    ce, ca = attach_translations(base, cues)
    wins = build_windows(cues)
    clips = []
    for i, (s, e, txt) in enumerate(wins):
        c = {
            "clip_id": f"yt_{video_id}_{s}",
            "provider": "html5",
            "video_id": video_id,
            "video_url": f"https://taalflix.onrender.com/yt/{video_id}",
            "embed_url": f"https://www.youtube.com/watch?v={video_id}",
            "title": f"{title} — {s}-{e}s",
            "start_time": s, "end_time": e,
            "dutch_text": txt, "correct_answer": txt,
            "wrong_answers": make_distractors(txt, vocab, rng),
            "cefr": cefr, "difficulty": {"A1": 1, "A2": 2, "B1": 3}.get(cefr, 2),
            "verified": False, "section": section,
            "transcript_source": "youtube_subs",
            "rights_status": "EMBED_ONLY",
        }
        tr = {}
        if ce:
            en = text_for(ce, s, e, cap=200)
            if len(en) >= 6:
                tr["en"] = en
        if ca:
            ar = text_for(ca, s, e, cap=200)
            if len(ar) >= 4:
                tr["ar"] = ar
        if tr:
            c["translations"] = tr
        clips.append(c)
        if on_partial and len(clips) in (3, 6, 12):
            on_partial(list(clips))
    if on_partial and clips:
        on_partial(list(clips))
    # Arabic: fill whatever YouTube didn't ship (local OPUS-MT, may no-op).
    try:
        import mt_ar
        n_ar = mt_ar.fill_ar(clips)
        if n_ar:
            print(f"[fastpath] +{n_ar} local AR translations", flush=True)
    except Exception as e:
        print(f"[fastpath] mt_ar skipped ({e})", flush=True)
    return clips
