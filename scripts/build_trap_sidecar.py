#!/usr/bin/env python3
"""One-time (+repeatable): build web/trap-meanings.json for CURATED clips.

{clip_id: {ar: [...], en: [...]}} — true meanings of the German sound-alikes
swapped into each clip's wrong answers (Tische->Teppich/Tasche model).

Source: web/de-glossary.json (built by scripts/build_glossary.py).
Purely local & instant. Idempotent: rerun anytime to refresh/extend.
Copies output to app/web/ as well.
"""
import json, os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STRIP = ".,!?…:;«»()\"'"


def diff_words(correct, wrong):
    have = {x.strip(STRIP) for x in correct.lower().split()}
    out = []
    for w in wrong.split():
        b = w.strip(STRIP)
        if len(b) >= 3 and b.lower() not in have and b not in out:
            out.append(b)
    return sorted(out, key=len, reverse=True)


def main():
    gpath = os.path.join(HERE, "web", "de-glossary.json")
    if not os.path.exists(gpath):
        raise SystemExit("run scripts/build_glossary.py first (web/de-glossary.json missing)")
    gloss = json.load(open(gpath, encoding="utf-8"))
    print(f"glossary: {len(gloss)} words")
    clips = json.load(open(os.path.join(HERE, "app", "clips_modern_fixed.json"), encoding="utf-8"))
    side = {}
    for c in clips:
        tr = c.get("translations") or {}
        entry = {}
        for lang in ("ar", "en"):
            ok = tr.get(lang)
            if not ok:
                continue
            hol = []
            for w in c.get("wrong_answers", []):
                for dw in diff_words(c.get("correct_answer", ""), w)[:2]:
                    m = (gloss.get(dw.lower()) or {}).get(lang, "").strip()
                    if (m and m.lower() != ok.lower() and m not in hol
                            and abs(len(m) - len(ok)) <= 40):
                        hol.append(m)
                        break
                if len(hol) >= 3:
                    break
            if hol:
                entry[lang] = hol[:3]
        if entry:
            side[c["clip_id"]] = entry
    outs = [os.path.join(HERE, "web", "trap-meanings.json"),
            os.path.join(HERE, "app", "web", "trap-meanings.json")]
    for fp in outs:
        json.dump(side, open(fp, "w", encoding="utf-8"), ensure_ascii=False)
    ar_n = sum(1 for v in side.values() if "ar" in v)
    en_n = sum(1 for v in side.values() if "en" in v)
    kb = os.path.getsize(outs[0]) // 1024
    print(f"sidecar: {len(side)} clips ({ar_n} ar, {en_n} en), {kb} KB")


if __name__ == "__main__":
    main()
