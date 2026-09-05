#!/usr/bin/env python3
"""Phase 4 — Whisper sampling fallback for videos WITHOUT subtitles.

Strategy (mirrors auto_clipper.py, tuned for "first quizzes fast"):
  1. Probe duration via yt-dlp (no download) — reject > HK_MAX_VIDEO_MIN.
  2. Sample up to N=9 windows of 8s spread over runtime (skip first 5% / last 5%,
     skip intro/credits) — same plan_timestamps() shape as auto_clipper.
  3. Download audio-only per window (yt-dlp -x --audio-format wav via ffmpeg),
     transcribe with faster-whisper tiny (cpu, int8) — the Deck's proven setup.
  4. Keep confident German (lang==de, prob>=0.70, 15..160 chars, >=4 words,
     BAD-word + English-leakage filters from nico_all.py).
  5. Yield first 3 good clips ASAP via on_partial, then continue in background.

Runs on the Deck (residential IP + real CPU). Import-safe without
faster_whisper installed (only needed inside transcribe()).
"""
import os, re, subprocess, tempfile

ENV = {k: v for k, v in os.environ.items()
       if k.lower() not in ("http_proxy", "https_proxy", "all_proxy")}
YTDLP = os.path.expanduser(os.environ.get("HK_YTDLP", "~/whisperenv/bin/yt-dlp"))
BAD = ["Copyright", "Untertitel", "Untertitlung", "B.K.", "G.M.", "Applaus",
       "Untertitelung"]
ENG = {"the", "and", "lets", "let", "have", "look", "at", "next", "one",
       "with", "you", "for", "this", "is", "are", "subtitles", "subscribe",
       "like", "video"}


def ok_text(t):
    toks = t.split()
    if not toks:
        return False
    eng = sum(1 for x in toks if x.lower().strip(".,!?…'\"") in ENG)
    if eng / len(toks) > 0.4:
        return False
    inner = len(re.findall(r"[.!?…]", t[:-1]))
    return (15 <= len(t) <= 160 and len(toks) >= 4 and inner <= 1
            and not any(b in t for b in BAD))


def probe_duration(video_id):
    try:
        out = subprocess.run(
            [YTDLP, "--no-warnings", "--print", "%(duration)s",
             f"https://www.youtube.com/watch?v={video_id}"],
            env=ENV, capture_output=True, text=True, timeout=60).stdout.strip()
        return float(out)
    except Exception:
        return 0.0


def plan_timestamps(duration, want=9, span_cap=2400):
    if duration >= 10:
        lo, hi = max(30, int(duration * 0.05)), min(int(duration * 0.95), span_cap)
    else:
        lo, hi = 30, span_cap
    slots = max(want * 3, 9)
    step = max(45, (hi - lo) // max(slots, 1))
    return list(range(lo, hi, step))[:slots]


def fetch_wav(video_id, ts, dur, wav):
    if os.path.exists(wav) and os.path.getsize(wav) > 40000:
        return True
    try:
        subprocess.run(
            [YTDLP, "--no-warnings", "--download-sections", f"*{ts}-{ts + dur}",
             "-x", "--audio-format", "wav",
             "--postprocessor-args", "-ar 16000 -ac 1",
             "-o", wav.replace(".wav", ".%(ext)s"),
             f"https://www.youtube.com/watch?v={video_id}"],
            env=ENV, capture_output=True, timeout=150)
        got = wav if os.path.exists(wav) else wav.replace(".wav", ".wav.wav")
        if os.path.exists(got) and os.path.getsize(got) > 40000:
            if got != wav:
                os.rename(got, wav)
            return True
        # fallback: any downloaded audio -> convert
        import glob
        base = wav.replace(".wav", "")
        for cand in glob.glob(base + ".*"):
            if cand.endswith((".part", ".ytdl", ".wav")):
                continue
            subprocess.run(["ffmpeg", "-y", "-i", cand, "-acodec", "pcm_s16le",
                            "-ar", "16000", "-ac", "1", wav],
                           env=ENV, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=30)
            if os.path.exists(wav) and os.path.getsize(wav) > 40000:
                return True
        return False
    except Exception:
        return False


def transcribe_batch(wavs, lang="de"):
    from faster_whisper import WhisperModel
    import os as _os
    size = _os.environ.get("HK_WHISPER_MODEL", "tiny")  # base is more accurate, ~2x slower
    model = WhisperModel(size, device="cpu", compute_type="int8")
    out = {}
    for wav in wavs:
        try:
            segs, info = model.transcribe(wav, language=lang, beam_size=5)
            txt = " ".join(x.text.strip() for x in segs).strip()
            out[wav] = (txt, info.language, float(info.language_probability))
        except Exception:
            out[wav] = ("", "?", 0.0)
    return out


def run_whisper_fallback(video_id, title, workdir, vocab=(), seed=41,
                         on_partial=None, cefr="A2", max_new=12,
                         section="myvideos"):
    """Returns clips. Streams first quizzes via on_partial as soon as ready."""
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "..", "server"))
    from pipeline_fastpath import make_distractors
    import random
    rng = random.Random(seed)
    vocab = sorted(set(vocab)) or ["Wasser", "Zeit", "Leute"]

    dur = probe_duration(video_id)
    max_min = int(os.environ.get("HK_MAX_VIDEO_MIN", "30"))
    if dur and dur > max_min * 60:
        raise ValueError(f"video too long ({int(dur)}s > {max_min}min)")
    tss = plan_timestamps(dur or 600, want=max_new)
    segdir = tempfile.mkdtemp(prefix=f"wh_{video_id}_", dir=workdir)
    jobs = [(t, os.path.join(segdir, f"{t}.wav")) for t in tss]
    got = [(t, w) for t, w in jobs if fetch_wav(video_id, t, 8, w)]
    if on_partial == "count":
        return {"windows_downloaded": len(got), "windows_total": len(jobs)}
    res = transcribe_batch([w for _, w in got])
    clips = []
    for t, w in sorted(got):
        txt, lang, pb = res.get(w, ("", "?", 0))
        if not (lang == "de" and pb >= 0.70 and ok_text(txt)):
            continue
        clips.append({
            "clip_id": f"yt_{video_id}_{t}",
            "provider": "html5", "video_id": video_id,
            "video_url": f"https://taalflix.onrender.com/yt/{video_id}",
            "embed_url": f"https://www.youtube.com/watch?v={video_id}",
            "title": f"{title} — {t}-{t + 8}s",
            "start_time": t, "end_time": t + 8,
            "dutch_text": txt, "correct_answer": txt,
            "wrong_answers": make_distractors(txt, vocab, rng),
            "cefr": cefr, "difficulty": 2,
            "verified": False, "section": section,
            "transcript_source": "whisper_tiny_sample",
            "rights_status": "EMBED_ONLY",
        })
        if on_partial and len(clips) == 3:
            on_partial(list(clips))
        if len(clips) >= max_new:
            break
    if on_partial and clips:
        on_partial(list(clips))
    return clips
