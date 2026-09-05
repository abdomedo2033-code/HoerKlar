#!/usr/bin/env python3
"""Split the baked `let clips=[...]` blob into per-section JSON files.

Canonical inputs (merge + dedupe by clip_id):
  app/clips_modern_fixed.json   (currently baked into index.html, 3360 clips)
  app/clips_new_sentences.json  (nicos-heavy variant, merged if present)

Outputs (generated, NOT committed — see .gitignore):
  server/data/clips_<section>.json   e.g. clips_movies.json, clips_series.json, ...
  server/data/manifest.json          {section: {count, sha1, bytes}, ...}

Usage:
  python3 scripts/split_clips.py [--check]
  python3 scripts/split_clips.py --out /tmp/clipsdata

--check: verify generated files match the baked blob (CI helper).
"""
import json, os, sys, hashlib, argparse
from collections import Counter

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUTS = [
    os.path.join(HERE, "app", "clips_modern_fixed.json"),
    os.path.join(HERE, "app", "clips_new_sentences.json"),
]
# Fallback: extract from baked index.html if JSON inputs are missing.
BAKED = [os.path.join(HERE, "index.html"), os.path.join(HERE, "app", "index.html")]


def load_inputs():
    clips = []
    for fp in INPUTS:
        if os.path.exists(fp):
            clips.extend(json.load(open(fp, encoding="utf-8")))
    if clips:
        return clips
    import re
    for fp in BAKED:
        if not os.path.exists(fp):
            continue
        t = open(fp, encoding="utf-8", errors="ignore").read()
        m = re.search(r"let clips=(\[.*?\]);", t, flags=re.DOTALL)
        if m:
            return json.loads(m.group(1))
    raise SystemExit("no clip source found (app/*.json or baked index.html)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(HERE, "server", "data"))
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    clips = load_inputs()
    # Dedupe by clip_id — BUT the two source files reuse the same de_nico_s*
    # id scheme for DIFFERENT content, so only drop exact duplicates. On id
    # collision with different content, re-key the later one.
    def fingerprint(c):
        return (c.get("video_id"), c.get("start_time"), c.get("dutch_text"))
    seen, merged = {}, []
    rekeyed = 0
    for c in clips:
        cid = c.get("clip_id")
        if not cid:
            continue
        if cid not in seen:
            seen[cid] = fingerprint(c)
            merged.append(c)
        elif seen[cid] == fingerprint(c):
            continue  # exact dupe (e.g. shared movies section)
        else:
            c = dict(c)
            base, n = cid, 2
            while f"{base}__v{n}" in seen:
                n += 1
            c["clip_id"] = f"{base}__v{n}"
            seen[c["clip_id"]] = fingerprint(c)
            merged.append(c)
            rekeyed += 1
    by_sec = {}
    for c in merged:
        by_sec.setdefault(c.get("section") or "movies", []).append(c)
    order = ["A1", "A2", "B1", "B2", "C1", "C2"]
    for sec in by_sec:
        by_sec[sec].sort(key=lambda c: (
            order.index(c["cefr"]) if c.get("cefr") in order else 99,
            c["clip_id"]))

    os.makedirs(args.out, exist_ok=True)
    manifest = {}
    for sec, items in sorted(by_sec.items()):
        blob = json.dumps(items, ensure_ascii=False, separators=(",", ":"))
        fp = os.path.join(args.out, f"clips_{sec}.json")
        if args.check:
            old = open(fp, encoding="utf-8").read() if os.path.exists(fp) else None
            status = "OK " if old == blob else "DIFF"
            print(f"{status} {fp} ({len(items)} clips)")
            continue
        open(fp, "w", encoding="utf-8").write(blob)
        manifest[sec] = {
            "count": len(items),
            "sha1": hashlib.sha1(blob.encode("utf-8")).hexdigest(),
            "bytes": len(blob.encode("utf-8")),
        }
    if args.check:
        return
    mfp = os.path.join(args.out, "manifest.json")
    json.dump(manifest, open(mfp, "w"), indent=2)
    total = sum(v["count"] for v in manifest.values())
    print(f"sections: {list(manifest)} | total {total} clips "
          f"| rekeyed {rekeyed} id-collisions (same id, different content)")
    print(f"wrote {args.out}/clips_<section>.json + manifest.json")


if __name__ == "__main__":
    main()
