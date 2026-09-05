#!/usr/bin/env python3
"""Phase 3 — Deck worker: poll the API over Tailscale, run the pipeline
with the Deck's residential IP + real CPU, post results back.

Why polling (not inbound): the Deck makes OUTBOUND HTTPS calls to the Render
URL (or Tailscale MagicDNS name), so no firewall holes, no inbound Tailscale
serve needed. Deck offline => jobs wait politely in `queued` state.

  API_BASE=https://<your-app>.onrender.com  (or http://deck:8788 for local dev)
  HK_WORKER_TOKEN=<same value as server env>  (required if server sets it)

Loop:
  GET /api/jobs/next?worker=deck   -> claimed job or {"job": null}
  fast-path: pipeline_fastpath.run_fastpath()   (30-60s, subtitled videos)
  on NoSubtitles -> whisper_fallback.run_whisper_fallback()  (slow path,
                    streams first 3 quizzes via POST progress)
  POST /api/jobs/<id>/complete {clips}

One job at a time. Systemd unit: worker/deck-worker.service.
"""
import json, os, sys, tempfile, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "server"))

API = os.environ.get("API_BASE", "http://127.0.0.1:8788").rstrip("/")
TOKEN = os.environ.get("HK_WORKER_TOKEN", "")
WORKDIR = os.environ.get("HK_WORKDIR", os.path.join(HERE, "..", "_clipcache_ingest"))
POLL_S = int(os.environ.get("HK_POLL_S", "15"))
CEFR = os.environ.get("HK_DEFAULT_CEFR", "A2")


def _req(method, path, payload=None):
    req = urllib.request.Request(
        API + path,
        data=json.dumps(payload or {}).encode() if payload is not None else None,
        method=method, headers={"Content-Type": "application/json"})
    if TOKEN:
        req.add_header("X-Worker-Token", TOKEN)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def post_progress(job_id, **fields):
    try:
        _req("POST", f"/api/jobs/{job_id}/progress", fields)
    except Exception as e:
        print(f"  progress post failed: {e}", flush=True)


def expand_playlist(playlist_id, max_items):
    """List video ids in a YouTube playlist (Deck network only)."""
    import subprocess
    yt = os.path.expanduser(os.environ.get("HK_YTDLP", "~/whisperenv/bin/yt-dlp"))
    env = {k: v for k, v in os.environ.items()
           if k.lower() not in ("http_proxy", "https_proxy", "all_proxy")}
    out = subprocess.run(
        [yt, "--no-warnings", "--flat-playlist", "--print", "%(id)s\t%(title)s",
         f"https://www.youtube.com/playlist?list={playlist_id}"],
        env=env, capture_output=True, text=True, timeout=120).stdout
    items = []
    for line in out.splitlines():
        if "\t" not in line:
            continue
        vid, title = line.split("\t", 1)
        if len(vid) == 11 and title and "[Private video]" not in title and "[Deleted video]" not in title:
            items.append((vid, title.strip()))
    return items[:max_items]


def handle_playlist(job):
    from pipeline_fastpath import run_fastpath, NoSubtitles
    from whisper_fallback import run_whisper_fallback
    jid = job["job_id"]
    section = (job.get("section") or "myvideos")[:24] or "myvideos"
    max_items = int(job.get("max_items") or os.environ.get("HK_MAX_PLAYLIST_ITEMS", "15"))
    post_progress(jid, status="fetching_subs", stage="playlist", progress=0.02,
                  title="listing playlist…")
    items = expand_playlist(job.get("playlist_id", ""), max_items)
    if not items:
        post_progress(jid, status="error", stage="error", progress=0.0,
                      error="playlist empty or unreadable")
        return
    os.makedirs(WORKDIR, exist_ok=True)
    vocab = load_vocab()
    all_clips, done_titles = [], []
    for n, (vid, title) in enumerate(items):
        post_progress(jid, status="fetching_subs", stage="playlist",
                      progress=0.05 + 0.85 * n / len(items), title=f"{n + 1}/{len(items)}: {title}"[:160],
                      clips_ready=list(all_clips))
        print(f"[worker] playlist {jid} [{n + 1}/{len(items)}] {vid} {title[:50]}", flush=True)

        def stream(clips, _n=n):
            post_progress(jid, status="translating", stage="streaming",
                          progress=0.05 + 0.85 * (_n + 0.5) / len(items),
                          clips_ready=list(all_clips) + list(clips))

        try:
            clips = run_fastpath(vid, title, WORKDIR, vocab=vocab,
                                 on_partial=stream, cefr=CEFR, section=section)
        except NoSubtitles:
            print("[worker] no subs -> Whisper", flush=True)
            post_progress(jid, status="transcribing", stage="whisper",
                          progress=0.05 + 0.85 * n / len(items),
                          title=f"{n + 1}/{len(items)}: {title}"[:160])
            clips = run_whisper_fallback(vid, title, WORKDIR, vocab=vocab,
                                         on_partial=stream, cefr=CEFR,
                                         section=section)
        all_clips.extend(clips)
        done_titles.append(title)
    res = _req("POST", f"/api/jobs/{jid}/complete", {"clips": all_clips[:180]})
    print(f"[worker] playlist completed: +{res.get('added', 0)} clips from {len(items)} videos", flush=True)


def handle(job):
    if job.get("kind") == "playlist":
        return handle_playlist(job)
    from pipeline_fastpath import run_fastpath, NoSubtitles
    jid, vid = job["job_id"], job["video_id"]
    section = (job.get("section") or "myvideos")[:24] or "myvideos"
    title = job.get("url", vid)
    os.makedirs(WORKDIR, exist_ok=True)
    print(f"[worker] job {jid} video {vid} section={section}", flush=True)
    try:
        import subprocess
        yt = os.path.expanduser(os.environ.get("HK_YTDLP", "~/whisperenv/bin/yt-dlp"))
        env = {k: v for k, v in os.environ.items()
               if k.lower() not in ("http_proxy", "https_proxy", "all_proxy")}
        real = subprocess.run(
            [yt, "--no-warnings", "--print", "%(title)s",
             f"https://www.youtube.com/watch?v={vid}"],
            env=env, capture_output=True, text=True, timeout=60).stdout.strip()
        if real:
            title = real
    except Exception as e:
        print(f"[worker] title lookup failed: {e}", flush=True)

    def stream(clips):
        post_progress(jid, status="translating", stage="streaming",
                      progress=0.5 + 0.4 * len(clips) / max(len(clips), 12),
                      clips_ready=clips)

    try:
        post_progress(jid, status="fetching_subs", stage="subs", progress=0.1,
                      title=title[:160])
        clips = run_fastpath(vid, title, WORKDIR, vocab=load_vocab(),
                             on_partial=stream, cefr=CEFR, section=section)
        print(f"[worker] fast-path done: {len(clips)} clips", flush=True)
    except NoSubtitles:
        from whisper_fallback import run_whisper_fallback
        print("[worker] no subs -> Whisper sampling fallback", flush=True)
        post_progress(jid, status="transcribing", stage="whisper", progress=0.2)
        clips = run_whisper_fallback(vid, title, WORKDIR, vocab=load_vocab(),
                                     on_partial=stream, cefr=CEFR,
                                     section=section)
        print(f"[worker] whisper done: {len(clips)} clips", flush=True)
    res = _req("POST", f"/api/jobs/{jid}/complete", {"clips": clips})
    print(f"[worker] completed: +{res.get('added', 0)} clips", flush=True)


def load_vocab():
    for fp in (os.path.join(HERE, "..", "app", "clips_modern_fixed.json"),
               os.path.join(HERE, "..", "app", "clips.json")):
        if os.path.exists(fp):
            try:
                clips = json.load(open(fp, encoding="utf-8"))
                return sorted({w.strip(".,!?…:;«»()\"'") for c in clips
                               for w in c.get("dutch_text", "").split()
                               if 3 <= len(w.strip(".,!?…:;«»()\"'")) <= 18})
            except Exception:
                pass
    return ["Wasser", "Zeit", "Leute"]


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true",
                    help="process a single queued job then exit (testing)")
    args = ap.parse_args()
    print(f"[worker] polling {API} every {POLL_S}s (workdir={WORKDIR})", flush=True)
    while True:
        try:
            nxt = _req("GET", "/api/jobs/next?worker=deck")
            job = (nxt or {}).get("job")
            if job:
                try:
                    handle(job)
                except Exception as e:
                    print(f"[worker] job {job.get('job_id')} failed: {e}", flush=True)
                    post_progress(job.get("job_id"), status="error",
                                  stage="error", progress=0.0)
                if args.once:
                    return
            else:
                if args.once:
                    print("[worker] queue empty, exiting (--once)", flush=True)
                    return
                time.sleep(POLL_S)
        except Exception as e:
            print(f"[worker] poll error: {e} (retry in {POLL_S}s)", flush=True)
            if args.once:
                raise SystemExit(1)
            time.sleep(POLL_S)


if __name__ == "__main__":
    main()
