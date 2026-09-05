#!/usr/bin/env python3
"""HoerKlar clip + ingest API (stdlib only — runs on Render free tier as-is).

Endpoints:
  GET  /api/health
  GET  /api/manifest                        -> per-section {count,sha1,bytes}
  GET  /api/clips?section=movies            -> JSON array (Phase 1 server-JSON)
  POST /api/ingest  {url, user?}            -> {job_id, status} | {error}
  GET  /api/jobs/<id>                       -> job incl. clips_ready + progress
  GET  /api/jobs/next?worker=deck           -> oldest queued job, claimed (Deck poll)
  POST /api/jobs/<id>/progress {stage,progress,clips_ready?}
  POST /api/jobs/<id>/complete {clips}      -> appends to myvideos section file

Storage: flat files under DATA_DIR (default ./server/data):
  clips_<section>.json   (written by scripts/split_clips.py, NOT committed)
  jobs/<jobid>.json      (queue_store)
  clips_myvideos.json    (auto-ingested, unverified)

Run locally:  python3 server/api_server.py 8788
Render: set startCommand to `python server/api_server.py $PORT`
        (or mount these routes into the existing yt_proxy.py — same handlers).
"""
import json, os, re, sys, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import queue_store, guards  # noqa: E402

DATA = os.environ.get("HK_DATA_DIR", os.path.join(HERE, "data"))
WORKER_TOKEN = os.environ.get("HK_WORKER_TOKEN", "")
rate = guards.RateLimit()


def _send(h, code, obj, ctype="application/json"):
    body = obj if isinstance(obj, bytes) else json.dumps(
        obj, ensure_ascii=False).encode("utf-8")
    h.send_response(code)
    h.send_header("Content-Type", ctype + "; charset=utf-8")
    h.send_header("Access-Control-Allow-Origin", "*")
    h.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    h.send_header("Access-Control-Allow-Headers", "Content-Type, X-Worker-Token")
    h.send_header("Content-Length", str(len(body)))
    h.end_headers()
    h.wfile.write(body)


def _body(h):
    try:
        n = int(h.headers.get("Content-Length") or 0)
    except Exception:
        n = 0
    raw = h.rfile.read(n) if n else b"{}"
    try:
        return json.loads(raw.decode("utf-8") or "{}")
    except Exception:
        return {}


def _manifest():
    mp = os.path.join(DATA, "manifest.json")
    if os.path.exists(mp):
        return json.load(open(mp, encoding="utf-8"))
    # Fallback: scan clips_*.json on the fly.
    import hashlib
    man = {}
    if os.path.isdir(DATA):
        for fn in sorted(os.listdir(DATA)):
            m = re.fullmatch(r"clips_(\w+)\.json", fn)
            if not m:
                continue
            blob = open(os.path.join(DATA, fn), encoding="utf-8").read()
            man[m.group(1)] = {"count": blob.count('"clip_id"'),
                               "sha1": hashlib.sha1(blob.encode()).hexdigest(),
                               "bytes": len(blob.encode())}
    return man


class H(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        _send(self, 204, b"")

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(u.query)
        if u.path == "/api/health":
            return _send(self, 200, {"ok": True, "manifest": _manifest()})
        if u.path == "/api/manifest":
            return _send(self, 200, _manifest())
        if u.path == "/api/clips":
            sec = (qs.get("section") or ["movies"])[0]
            if not re.fullmatch(r"[a-z0-9_]{1,20}", sec):
                return _send(self, 400, {"error": "bad section"})
            fp = os.path.join(DATA, f"clips_{sec}.json")
            if not os.path.exists(fp):
                return _send(self, 404, {"error": f"no data for section {sec}"})
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "public, max-age=300")
            self.end_headers()
            with open(fp, "rb") as f:
                while True:
                    ch = f.read(65536)
                    if not ch:
                        break
                    self.wfile.write(ch)
            return
        m = re.fullmatch(r"/api/jobs/([0-9a-f]+)", u.path)
        if m:
            job = queue_store.get(DATA, m.group(1))
            if not job:
                return _send(self, 404, {"error": "unknown job"})
            return _send(self, 200, job)
        if u.path == "/api/jobs/next":
            if WORKER_TOKEN and self.headers.get("X-Worker-Token") != WORKER_TOKEN:
                return _send(self, 403, {"error": "bad worker token"})
            job = queue_store.claim_next(DATA, (qs.get("worker") or ["deck"])[0])
            return _send(self, 200, {"job": job})
        return _send(self, 404, {"error": "not found"})

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        if u.path == "/api/ingest":
            ip = self.client_address[0] if self.client_address else "?"
            if not rate.allow(ip):
                return _send(self, 429, {"error": "rate limited, try again soon"})
            payload = _body(self)
            url = (payload.get("url") or "").strip()
            user = (payload.get("user") or "local")[:64] or "local"
            section = re.sub(r"[^a-z0-9 _-]", "", (payload.get("section") or "").lower()).strip().replace(" ", "_").replace("-", "_")[:24] or "myvideos"
            vid, canon_or_err = guards.extract_video_id(url)
            if not vid:
                return _send(self, 400, {"error": canon_or_err})
            ok, msg = guards.check_quota(queue_store, DATA, user)
            if not ok:
                return _send(self, 429, {"error": msg})
            # Dedup: same video already queued/active for this user?
            job = queue_store.create(DATA, video_id=vid, url=canon_or_err, user=user, section=section)
            return _send(self, 200, {"job_id": job["job_id"], "status": "queued",
                                     "section": section,
                                     "poll": f"/api/jobs/{job['job_id']}"})
        m = re.fullmatch(r"/api/jobs/([0-9a-f]+)/(progress|complete)", u.path)
        if m:
            if WORKER_TOKEN and self.headers.get("X-Worker-Token") != WORKER_TOKEN:
                return _send(self, 403, {"error": "bad worker token"})
            job_id, action = m.group(1), m.group(2)
            payload = _body(self)
            if action == "progress":
                fields = dict(status=payload.get("status", "fetching_subs"),
                              stage=payload.get("stage", ""),
                              progress=float(payload.get("progress", 0) or 0),
                              clips_ready=payload.get("clips_ready", []) or
                              (queue_store.get(DATA, job_id) or {}).get("clips_ready", []))
                if payload.get("title"):
                    fields["title"] = str(payload["title"])[:160]
                job = queue_store.update(DATA, job_id, **fields)
                if not job:
                    return _send(self, 404, {"error": "unknown job"})
                return _send(self, 200, job)
            # complete: persist clips to myvideos section file (unverified)
            clips = payload.get("clips", [])
            try:
                import api_server_helpers as helpers
                added = helpers.append_myvideos(DATA, clips)
            except ValueError as e:
                return _send(self, 400, {"error": str(e)})
            job = queue_store.update(DATA, job_id, status="done", stage="done",
                                     progress=1.0, clips_ready=clips)
            return _send(self, 200, {"ok": True, "added": added, "job": job})
        return _send(self, 404, {"error": "not found"})

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    port = int(sys.argv[1] if len(sys.argv) > 1 else os.environ.get("PORT", 8788))
    os.makedirs(DATA, exist_ok=True)
    if os.environ.get("HK_INLINE", "1") == "1":
        try:
            import inline_worker
            inline_worker.start(DATA, queue_store)
            print("inline fast-path worker: on (Deck still covers Whisper/blocked)")
        except Exception as e:
            print(f"inline worker disabled: {e}")
    print(f"HoerKlar API on 0.0.0.0:{port} (data={DATA})")
    ThreadingHTTPServer(("0.0.0.0", port), H).serve_forever()
