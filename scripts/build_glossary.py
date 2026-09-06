#!/usr/bin/env python3
"""One-time: build web/de-glossary.json {word: {ar, en}} for vocab words.

Resumable (per-pair JSON caches + partial output). Throttled for the free
API. Run in background:
  nohup python3 scripts/build_glossary.py > /tmp/opencode/gloss.log 2>&1 &
"""
import json, os, sys, time
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "server"))
from glossary import lookup

OUT = [os.path.join(HERE, "web", "de-glossary.json"),
       os.path.join(HERE, "app", "web", "de-glossary.json")]

clips = json.load(open(os.path.join(HERE, "app", "clips_modern_fixed.json"), encoding="utf-8"))
words = sorted({w.strip(".,!?…:;«»()\"'") for c in clips for w in c.get("dutch_text", "").split()})
words = [w for w in words if len(w) >= 4]
print(f"{len(words)} words", flush=True)
existing = {}
for fp in OUT:
    if os.path.exists(fp):
        try:
            existing.update(json.load(open(fp, encoding="utf-8")))
        except Exception:
            pass
print(f"resuming with {len(existing)} already done", flush=True)
g = {}
t0 = time.time()
for i, w in enumerate(words):
    if w.lower() in existing:
        g[w.lower()] = existing[w.lower()]
        continue
    ar = lookup(w, "de|ar")
    en = lookup(w, "de|en")
    if ar or en:
        g[w.lower()] = {k: v for k, v in (("ar", ar), ("en", en)) if v}
    if (i + 1) % 25 == 0:
        for fp in OUT:
            json.dump({**existing, **g}, open(fp, "w", encoding="utf-8"), ensure_ascii=False)
        el = time.time() - t0
        print(f"{i + 1}/{len(words)} ({el / 60:.1f} min)", flush=True)
for fp in OUT:
    json.dump({**existing, **g}, open(fp, "w", encoding="utf-8"), ensure_ascii=False)
print(f"DONE {len(g)} new, {len(existing) + len(g)} total in {(time.time() - t0) / 60:.1f} min", flush=True)
