"""Phase 5 — abuse guards + rights flow (stdlib only).

Quotas (defaults, tunable via env):
  HK_MAX_JOBS_PER_DAY=5   per user id
  HK_MAX_ACTIVE_JOBS=2    per user id
  HK_MAX_VIDEO_MIN=30     reject longer videos at ingest time
  HK_ALLOWLIST=...        comma-separated host allowlist; default YouTube only

Rights: auto-ingested clips ALWAYS land flagged unverified in the user's
personal section ("myvideos", verified=false, rights_status EMBED_ONLY or
UNKNOWN). Promotion to shared sections (movies/series/songs) requires a
human glance — see docs/automation/README.md §Rights.
"""
import os, re, urllib.parse

YT_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
DEFAULT_ALLOW = ("youtube.com", "www.youtube.com", "youtu.be",
                 "www.youtu.be", "m.youtube.com")


def allowlist():
    raw = os.environ.get("HK_ALLOWLIST")
    if not raw:
        return DEFAULT_ALLOW
    return tuple(h.strip().lower() for h in raw.split(",") if h.strip())


def extract_video_id(url):
    """Return (video_id, canonical_url) or (None, error). YouTube only by default."""
    try:
        u = urllib.parse.urlparse(url.strip())
    except Exception:
        return None, "unparseable URL"
    host = (u.netloc or "").lower()
    if host not in allowlist():
        return None, f"host not allowed: {host or '?'}"
    vid = None
    if host in ("youtu.be", "www.youtu.be"):
        vid = u.path.strip("/").split("/")[0] if u.path.strip("/") else None
    else:
        qs = urllib.parse.parse_qs(u.query)
        vid = (qs.get("v") or [None])[0]
        if not vid and u.path.startswith("/shorts/"):
            vid = u.path.split("/")[2] if len(u.path.split("/")) > 2 else None
        if not vid and u.path.startswith("/embed/"):
            vid = u.path.split("/")[2] if len(u.path.split("/")) > 2 else None
    if not vid or not YT_ID.match(vid):
        return None, "could not extract a valid 11-char YouTube video id"
    return vid, f"https://www.youtube.com/watch?v={vid}"


def check_quota(queue_store, data_dir, user, max_day=None, max_active=None):
    max_day = int(os.environ.get("HK_MAX_JOBS_PER_DAY",
                                 max_day if max_day is not None else 5))
    max_active = int(os.environ.get("HK_MAX_ACTIVE_JOBS",
                                    max_active if max_active is not None else 2))
    if queue_store.user_today_count(data_dir, user) >= max_day:
        return False, f"daily quota reached ({max_day}/day)"
    if queue_store.user_active_count(data_dir, user) >= max_active:
        return False, f"too many active jobs ({max_active} max)"
    return True, "ok"


class RateLimit:
    """Trivial in-memory per-IP sliding window. Enough for free-tier scale."""

    def __init__(self, n=30, window_s=60):
        self.n, self.window = n, window_s
        self.hits = {}

    def allow(self, ip):
        import time
        now = time.time()
        lst = [t for t in self.hits.get(ip, []) if now - t < self.window]
        if len(lst) >= self.n:
            self.hits[ip] = lst
            return False
        lst.append(now)
        self.hits[ip] = lst
        return True
