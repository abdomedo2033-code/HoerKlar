"""Render inline worker: fetch subtitles + build quizzes IN the API process.

Why: makes the website button work even with the Deck off (subtitled videos,
the actual use case). Heavy/slow work still falls through to the Deck:
  - NoSubtitles -> job requeued with deck_only=true (Whisper runs on Deck CPU)
  - any exception  -> same requeue (Deck retries with full pipeline)
  - Deck's claim_next() takes any queued job, so nothing gets stuck.

Runs as one daemon thread beside the HTTP server (free tier = 1 instance).
Needs yt-dlp on PATH (server/requirements.txt) and HK_YTDLP env if elsewhere.
"""
import json, os, subprocess, tempfile, threading, time, traceback

YTDLP = os.environ.get("HK_YTDLP", "yt-dlp")
ENV = {k: v for k, v in os.environ.items()
       if k.lower() not in ("http_proxy", "https_proxy", "all_proxy")}


def load_vocab(data_dir):
    words = set()
    try:
        for fn in os.listdir(data_dir):
            if not (fn.startswith("clips_") and fn.endswith(".json")):
                continue
            try:
                clips = json.load(open(os.path.join(data_dir, fn), encoding="utf-8"))
            except Exception:
                continue
            for c in clips:
                for w in (c.get("dutch_text") or "").split():
                    b = w.strip(".,!?…:;«»()\"'")
                    if 3 <= len(b) <= 18:
                        words.add(b)
    except Exception:
        pass
    return sorted(words) or ["Wasser", "Zeit", "Leute"]


def title_of(video_id):
    try:
        return subprocess.run(
            [YTDLP, "--no-warnings", "--print", "%(title)s",
             f"https://www.youtube.com/watch?v={video_id}"],
            env=ENV, capture_output=True, text=True, timeout=60).stdout.strip()
    except Exception:
        return video_id


def process_one(data_dir, queue_store, job):
    import pipeline_fastpath as fp
    jid, vid = job["job_id"], job["video_id"]
    workdir = os.path.join(data_dir, "tmp_inline")
    os.makedirs(workdir, exist_ok=True)
    vocab = load_vocab(data_dir)

    def stream(clips):
        queue_store.update(data_dir, jid, status="translating",
                           stage="streaming", progress=0.9, clips_ready=clips)

    try:
        queue_store.update(data_dir, jid, status="fetching_subs",
                           stage="subs", progress=0.1)
        title = title_of(vid) or job.get("url", vid)
        clips = fp.run_fastpath(vid, title, workdir, vocab=vocab,
                                on_partial=stream)
        # persist like POST /complete (import here: api_server owns the file layout)
        import api_server_helpers as helpers
        added = helpers.append_myvideos(data_dir, clips)
        queue_store.update(data_dir, jid, status="done", stage="done",
                           progress=1.0, clips_ready=clips)
        print(f"[inline] job {jid}: +{added} clips (fast-path)", flush=True)
    except fp.NoSubtitles:
        queue_store.update(data_dir, jid, status="queued", stage="awaiting_deck",
                           progress=0.1, deck_only=True,
                           error="no subtitles — waiting for Deck Whisper")
        print(f"[inline] job {jid}: no subs, handed to Deck", flush=True)
    except Exception as e:
        traceback.print_exc()
        queue_store.update(data_dir, jid, status="queued", stage="awaiting_deck",
                           progress=0.0, deck_only=True,
                           error=f"inline failed ({e}) — waiting for Deck")


def loop_forever(data_dir, queue_store, interval=10):
    import time as _t
    while True:
        try:
            job = queue_store.claim_next(data_dir, worker="render-inline")
            if job:
                process_one(data_dir, queue_store, job)
            else:
                _t.sleep(interval)
        except Exception:
            traceback.print_exc()
            _t.sleep(interval)


def start(data_dir, queue_store):
    th = threading.Thread(target=loop_forever, args=(data_dir, queue_store),
                          daemon=True, name="inline-worker")
    th.start()
    return th
