"""Tiny JSON-file job queue (no Redis — fits Render free tier).

States: queued -> fetching_subs -> aligning -> distractors -> translating
        -> done | error
        Whisper path inserts: transcribing (+transcribed_count/total) instead of
        aligning, and streams partial clips via `clips_ready`.

Concurrency-safe enough for 1 API process + 1 Deck worker: atomic writes via
rename + per-job files (no single-file locking needed).
"""
import json, os, time, uuid

STATES = ("queued", "fetching_subs", "aligning", "transcribing", "distractors",
          "translating", "done", "error")


def _root(data_dir):
    qd = os.path.join(data_dir, "jobs")
    os.makedirs(qd, exist_ok=True)
    return qd


def _fp(data_dir, job_id):
    # job_id is hex uuid we mint ourselves — no path traversal possible.
    return os.path.join(_root(data_dir), job_id + ".json")


def _write(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    os.rename(tmp, path)


def create(data_dir, *, video_id, url, user="local", section="myvideos"):
    job = {
        "job_id": uuid.uuid4().hex[:12],
        "video_id": video_id, "url": url, "user": user,
        "section": section, "status": "queued",
        "progress": 0.0, "stage": "queued",
        "clips_ready": [], "error": None,
        "created_at": time.time(), "updated_at": time.time(),
    }
    _write(_fp(data_dir, job["job_id"]), job)
    return job


def get(data_dir, job_id):
    if not job_id or any(c not in "0123456789abcdef" for c in job_id):
        return None
    fp = _fp(data_dir, job_id)
    if not os.path.exists(fp):
        return None
    return json.load(open(fp, encoding="utf-8"))


def update(data_dir, job_id, **fields):
    job = get(data_dir, job_id)
    if not job:
        return None
    job.update(fields)
    job["updated_at"] = time.time()
    _write(_fp(data_dir, job_id), job)
    return job


def claim_next(data_dir, worker="deck"):
    """FIFO claim of oldest queued job. Deck-offline-safe: unclaimed jobs just wait."""
    qd = _root(data_dir)
    cands = []
    for fn in os.listdir(qd):
        if not fn.endswith(".json"):
            continue
        try:
            j = json.load(open(os.path.join(qd, fn), encoding="utf-8"))
        except Exception:
            continue
        if j.get("status") == "queued":
            cands.append(j)
    cands.sort(key=lambda j: j.get("created_at", 0))
    if not cands:
        return None
    job = cands[0]
    return update(data_dir, job["job_id"], status="fetching_subs",
                  stage="claimed", worker=worker)


def user_active_count(data_dir, user):
    n = 0
    qd = _root(data_dir)
    for fn in os.listdir(qd):
        if not fn.endswith(".json"):
            continue
        try:
            j = json.load(open(os.path.join(qd, fn), encoding="utf-8"))
        except Exception:
            continue
        if j.get("user") == user and j.get("status") not in ("done", "error"):
            n += 1
    return n


def user_today_count(data_dir, user):
    day = time.strftime("%Y-%m-%d")
    n = 0
    qd = _root(data_dir)
    for fn in os.listdir(qd):
        if not fn.endswith(".json"):
            continue
        try:
            j = json.load(open(os.path.join(qd, fn), encoding="utf-8"))
        except Exception:
            continue
        if j.get("user") == user and time.strftime("%Y-%m-%d",
                time.localtime(j.get("created_at", 0))) == day:
            n += 1
    return n
