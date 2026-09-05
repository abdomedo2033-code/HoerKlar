"""Shared persistence: append clips to the myvideos section file.

Used by both api_server.POST /complete (Deck worker) and inline_worker
(Render inline fast-path). Single place enforcing the rights rule:
auto-ingested clips are ALWAYS unverified + personal.
"""
import json, os


def append_myvideos(data_dir, clips, limit=40):
    if not isinstance(clips, list) or len(clips) > limit:
        raise ValueError("clips must be a list of <=" + str(limit))
    myp = os.path.join(data_dir, "clips_myvideos.json")
    mine = json.load(open(myp, encoding="utf-8")) if os.path.exists(myp) else []
    have = {c.get("clip_id") for c in mine}
    added = 0
    for c in clips:
        c = dict(c)
        c["verified"] = False
        c["section"] = "myvideos"
        c.setdefault("rights_status", "EMBED_ONLY")
        if c.get("clip_id") and c["clip_id"] not in have:
            mine.append(c)
            have.add(c["clip_id"])
            added += 1
    tmp = myp + ".tmp"
    json.dump(mine, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
    os.rename(tmp, myp)
    return added
