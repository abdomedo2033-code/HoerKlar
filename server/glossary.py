"""German->Arabic single-word glossary via translation memory (MyMemory).

Why not local MT: OPUS-MT degenerates on lone words (repetition loops).
MyMemory returns dictionary-grade short glosses, perfect for word-level
trap meanings: Tische->طاولات, Teppich->سجاد, Tasche->حقيبة.

Deck-network only (build time). Persistent JSON cache -> repeats are free.
Tiny volumes (a few words per video). Never raises.
"""
import json, os, re, time, urllib.parse, urllib.request

_caches = {}
_last_hit = 0.0


def _path(pair):
    tag = pair.replace("|", "_")
    d = os.environ.get("HK_WORKDIR",
                       os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "..", "_clipcache_ingest"))
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"glossary_{tag}.json")


def _load(pair):
    if pair not in _caches:
        try:
            _caches[pair] = json.load(open(_path(pair), encoding="utf-8"))
        except Exception:
            _caches[pair] = {}
    return _caches[pair]


def _save(pair):
    try:
        tmp = _path(pair) + ".tmp"
        json.dump(_caches[pair], open(tmp, "w", encoding="utf-8"),
                  ensure_ascii=False)
        os.rename(tmp, _path(pair))
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


def _ok_en(s):
    s = (s or "").strip().rstrip(",;")
    return bool(re.match(r"^[A-Za-z][A-Za-z '’\-]*$", s)) and 1 <= len(s) <= 40


def lookup(word, pair="de|ar"):
    """German word -> short gloss in target lang, or None.
    Cached per pair, throttled, safe."""
    global _last_hit
    w = (word or "").strip().strip(".,!?…:;«»()\"'")
    if len(w) < 3:
        return None
    cache = _load(pair)
    key = w.lower()
    if key in cache:
        return cache[key] or None
    # throttle: be polite to the free API
    dt = time.time() - _last_hit
    if dt < 1.0:
        time.sleep(1.0 - dt)
    _last_hit = time.time()
    best = None
    transport_ok = False
    try:
        url = ("https://api.mymemory.translated.net/get?q="
               + urllib.parse.quote(w) + "&langpair=" + pair)
        _mm_email = os.environ.get("HK_MYMEMORY_EMAIL", "")
        if _mm_email and "@" in _mm_email:
            url += "&de=" + urllib.parse.quote(_mm_email)
        req = urllib.request.Request(url, headers={"User-Agent": "HoerKlar/1.0"})
        d = json.load(urllib.request.urlopen(req, timeout=20))
        transport_ok = True
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
        check = _ok_ar if pair.endswith("|ar") else _ok_en
        for c in cands:
            c = _clean(c)
            if pair.endswith("|en"):
                c = c.rstrip(",;").strip()
            if check(c) and c.lower() != key:
                best = c
                break
    except Exception:
        best = None
    if transport_ok:
        cache[key] = best or ""
        _save(pair)
    return best
