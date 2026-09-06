#!/usr/bin/env python3
"""Parallel glossary builder: web/de-glossary.json {word: {ar, en}}.

Workers + polite shared rate limit, quota backoff (sleeps through 429s),
resumable (merges existing output). MyMemory email quota via
HK_MYMEMORY_EMAIL. Run detached:
  setsid nohup python3 scripts/build_glossary.py > /tmp/opencode/gloss.log 2>&1 < /dev/null &
"""
import json, os, re, sys, threading, time, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "server"))
from glossary import _load, _save, _clean, _ok_ar, _ok_en  # cache reuse

OUT = [os.path.join(HERE, "web", "de-glossary.json"),
       os.path.join(HERE, "app", "web", "de-glossary.json")]
WORKERS = int(os.environ.get("HK_GLOSS_WORKERS", "2"))
MIN_GAP = float(os.environ.get("HK_GLOSS_GAP", "1.0"))

_gap_lock = threading.Lock()
_last_req = 0.0
_cooldown_until = 0.0
_save_lock = threading.Lock()
result = {}
done_count = [0]
t0 = time.time()


class QuotaHit(Exception):
    pass


def _email_suffix():
    em = os.environ.get("HK_MYMEMORY_EMAIL", "")
    if em and "@" in em:
        return "&de=" + urllib.parse.quote(em)
    return ""


def raw_fetch(word, pair):
    """Single lookup with shared polite gap. Raises QuotaHit on 429/quota."""
    global _last_req
    with _gap_lock:
        now = time.time()
        if now < _cooldown_until:
            raise QuotaHit()
        wait = MIN_GAP - (now - _last_req)
        if wait > 0:
            time.sleep(wait)
        _last_req = time.time()
    url = ("https://api.mymemory.translated.net/get?q="
           + urllib.parse.quote(word) + "&langpair=" + pair + _email_suffix())
    req = urllib.request.Request(url, headers={"User-Agent": "HoerKlar/1.0"})
    try:
        d = json.load(urllib.request.urlopen(req, timeout=25))
    except Exception as e:
        if "429" in str(e) or "Too Many" in str(e):
            raise QuotaHit()
        return None
    r = (d.get("responseData") or {}).get("translatedText", "")
    if "MYMEMORY WARNING" in r or "QUERY LENGTH LIMIT" in r or "429" in r:
        raise QuotaHit()
    check = _ok_ar if pair.endswith("|ar") else _ok_en
    cands = [r] + [m.get("translation", "") for m in (d.get("matches") or [])[:3]]
    for c in cands:
        c = _clean(c)
        if pair.endswith("|en"):
            c = c.rstrip(",;").strip()
        if check(c) and c.lower() != word.lower():
            return c
    return None


def one(word):
    global _cooldown_until
    key = word.lower()
    entry = {}
    for pair, lang in (("de|ar", "ar"), ("de|en", "en")):
        cache = _load(pair)
        if key in cache and cache[key]:
            entry[lang] = cache[key]
            continue
        try:
            got = raw_fetch(word, pair)
        except QuotaHit:
            _cooldown_until = time.time() + 45 * 60
            print("QUOTA 429 — cooling down 45 min", flush=True)
            return None
        if got:
            entry[lang] = got
            with _save_lock:
                cache[key] = got
                _save(pair)
    with _save_lock:
        if entry:
            result[key] = entry
        done_count[0] += 1
        n = done_count[0]
    if n % 25 == 0:
        dump()
        print(f"{base_done + n}/{len(words)} ({(time.time() - t0) / 60:.1f} min)", flush=True)
    return True


def dump():
    with _save_lock:
        merged = {**existing, **result}
    for fp in OUT:
        tmp = fp + ".tmp"
        json.dump(merged, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
        os.rename(tmp, fp)


clips = json.load(open(os.path.join(HERE, "app", "clips_modern_fixed.json"), encoding="utf-8"))
words = sorted({w.strip(".,!?…:;«»()\"'") for c in clips for w in c.get("dutch_text", "").split()})
words = [w for w in words if len(w) >= 4]
existing = {}
for fp in OUT:
    if os.path.exists(fp):
        try:
            existing.update(json.load(open(fp, encoding="utf-8")))
        except Exception:
            pass
todo = [w for w in words if w.lower() not in existing]
base_done = len(existing)
print(f"{len(words)} words, {base_done} done, {len(todo)} to go", flush=True)
with ThreadPoolExecutor(max_workers=WORKERS) as ex:
    list(ex.map(one, todo))
dump()
print(f"DONE {len(existing) + len(result)} total in {(time.time() - t0) / 60:.1f} min", flush=True)
