"""German->Arabic single-word glossary via translation memory (MyMemory).

Why not local MT: OPUS-MT degenerates on lone words (repetition loops).
MyMemory returns dictionary-grade short glosses, perfect for word-level
trap meanings: Tische->طاولات, Teppich->سجاد, Tasche->حقيبة.

Deck-network only (build time). Persistent JSON cache -> repeats are free.
Tiny volumes (a few words per video). Never raises.
"""
import json, os, re, time, urllib.parse, urllib.request

_CACHE_FILE = None
_cache = None
_last_hit = 0.0


def _path():
    global _CACHE_FILE
    if _CACHE_FILE:
        return _CACHE_FILE
    d = os.environ.get("HK_WORKDIR",
                       os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "..", "_clipcache_ingest"))
    os.makedirs(d, exist_ok=True)
    _CACHE_FILE = os.path.join(d, "glossary_ar.json")
    return _CACHE_FILE


def _load():
    global _cache
    if _cache is not None:
        return _cache
    try:
        _cache = json.load(open(_path(), encoding="utf-8"))
    except Exception:
        _cache = {}
    return _cache


def _save():
    try:
        tmp = _path() + ".tmp"
        json.dump(_cache, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
        os.rename(tmp, _path())
    except Exception:
        pass


def _clean(s):
    s = (s or "").strip()
    s = re.sub(r"\s*\(.*?\)\s*", " ", s)  # drop "(anatomy)" style notes
    s = re.sub(r"[.،;!؟?]+$", "", s).strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _ok_ar(s):
    return bool(s) and 1 <= len(s) <= 40 and any(
        "\u0600" <= ch <= "\u06ff" for ch in s)


def lookup(word):
    """German word -> short Arabic gloss, or None. Cached, throttled, safe."""
    global _last_hit
    w = (word or "").strip().strip(".,!?…:;«»()\"'")
    if len(w) < 3:
        return None
    cache = _load()
    key = w.lower()
    if key in cache:
        return cache[key] or None
    # throttle: be polite to the free API
    dt = time.time() - _last_hit
    if dt < 1.0:
        time.sleep(1.0 - dt)
    _last_hit = time.time()
    best = None
    try:
        url = ("https://api.mymemory.translated.net/get?q="
               + urllib.parse.quote(w) + "&langpair=de|ar")
        req = urllib.request.Request(url, headers={"User-Agent": "HoerKlar/1.0"})
        d = json.load(urllib.request.urlopen(req, timeout=20))
        cands = []
        r = (d.get("responseData") or {}).get("translatedText", "")
        if r and "MYMEMORY WARNING" not in r and "QUERY LENGTH LIMIT" not in r:
            cands.append(r)
        for m in (d.get("matches") or [])[:4]:
            try:
                if float(m.get("quality", 0) or 0) >= 40:
                    cands.append(m.get("translation", ""))
            except Exception:
                pass
        for c in cands:
            c = _clean(c)
            if _ok_ar(c) and c.lower() != key:
                best = c
                break
    except Exception:
        best = None
    cache[key] = best or ""
    _save()
    return best
