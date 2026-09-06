"""On-Deck German->Arabic translation (OPUS-MT, local, private).

Model: Helsinki-NLP/opus-mt-de-ar, CPU, lazy singleton. Used to fill the
missing `translations.ar` on auto-built clips (YouTube almost never ships
Arabic tracks for German videos). Import-safe everywhere: if torch/model is
absent it degrades to None and clips simply stay EN-only.

Cache: _clipcache_ingest/mt_ar_cache.json maps de->ar so repeats are free.
"""
import json, os, re, threading

_MODEL_ID = "Helsinki-NLP/opus-mt-de-ar"
_lock = threading.Lock()
_mt = None  # (tokenizer, model)
_failed = False


def _cache_path():
    d = os.environ.get("HK_WORKDIR",
                       os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "..", "_clipcache_ingest"))
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "mt_ar_cache.json")


def _load_cache():
    try:
        return json.load(open(_cache_path(), encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(cache):
    try:
        tmp = _cache_path() + ".tmp"
        json.dump(cache, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
        os.rename(tmp, _cache_path())
    except Exception:
        pass


def available():
    """True if the model weights are on disk (no download attempted here)."""
    root = os.path.join(os.environ.get("HF_HOME", "/var/cache/huggingface"),
                        "hub", "models--Helsinki-NLP--opus-mt-de-ar")
    if not os.path.isdir(root):
        return False
    for dp, _, fns in os.walk(root):
        if any(fn in ("pytorch_model.bin", "model.safetensors") for fn in fns):
            return True
    return False


def _get_pipe():
    """Returns (tokenizer, model). Direct Marian API — stable across
    transformers versions (v5 dropped the translation pipeline task)."""
    global _mt, _failed
    if _mt is not None:
        return _mt
    if _failed:
        return None
    with _lock:
        if _mt is not None:
            return _mt
        if _failed:
            return None
        try:
            # Local files only: never stall a job on a download.
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
            from transformers import MarianMTModel, MarianTokenizer
            tok = MarianTokenizer.from_pretrained(_MODEL_ID, local_files_only=True)
            mdl = MarianMTModel.from_pretrained(_MODEL_ID, local_files_only=True)
            mdl.eval()
            _mt = (tok, mdl)
            return _mt
        except Exception as e:
            print(f"[mt_ar] unavailable ({e})", flush=True)
            _failed = True
            return None


def translate(texts):
    """Translate a list of German strings -> Arabic. Returns dict de->ar
    (only successful ones). Never raises."""
    texts = [t for t in dict.fromkeys(texts or []) if t and len(t.strip()) >= 3]
    if not texts:
        return {}
    cache = _load_cache()
    missing = [t for t in texts if t not in cache]
    if missing:
        mt = _get_pipe()
        if mt is None:
            return {t: cache[t] for t in texts if t in cache}
        tok, mdl = mt
        try:
            import torch
            for i in range(0, len(missing), 8):
                batch = missing[i:i + 8]
                enc = tok(batch, return_tensors="pt", padding=True,
                          truncation=True, max_length=128)
                with torch.no_grad():
                    gen = mdl.generate(**enc, max_length=128, num_beams=4)
                for src, g in zip(batch, gen):
                    tgt = tok.decode(g, skip_special_tokens=True).strip()
                    tgt = re.sub(r"^[\s\-–—«»\"'()\[\].,;!?:]+", "", tgt)
                    tgt = re.sub(r"[\s\-–—«»\"'()\[\]]+$", "", tgt)
                    tgt = re.sub(r"\s+", " ", tgt).strip()
                    # sanity: non-empty, Arabic-script, not a copy
                    if (tgt and tgt.lower() != src.lower()
                            and any("\u0600" <= ch <= "\u06ff" for ch in tgt)):
                        cache[src] = tgt
            _save_cache(cache)
        except Exception as e:
            print(f"[mt_ar] batch failed ({e})", flush=True)
    return {t: cache[t] for t in texts if t in cache}


def fill_ar_traps(clips):
    """Trap-meaning Arabic distractors: translate the clip's OWN German
    wrong answers (they carry full sentence context, unlike lone words).
    Result: each Arabic wrong option is literally what a similar-sounding
    German sentence would mean. Only for clips that already have a correct
    Arabic answer to contrast against. Returns number of clips enriched."""
    cands = [c for c in clips
             if (c.get("translations") or {}).get("ar")
             and not (c.get("translation_distractors") or {}).get("ar")
             and c.get("wrong_answers")]
    if not cands:
        return 0
    texts = [w for c in cands for w in c["wrong_answers"]]
    got = translate(texts)
    n = 0
    for c in cands:
        hol = []
        for w in c["wrong_answers"]:
            a = got.get(w)
            if (a and a != c["translations"]["ar"] and a not in hol
                    and abs(len(a) - len(c["translations"]["ar"])) <= 40):
                hol.append(a)
        if hol:
            c.setdefault("translation_distractors", {})["ar"] = hol[:3]
            n += 1
    return n


def fill_ar(clips):
    """Fill missing translations.ar in place. Returns number filled."""
    need = [c.get("dutch_text", "") for c in clips
            if not (c.get("translations") or {}).get("ar")]
    if not need:
        return 0
    got = translate(need)
    n = 0
    for c in clips:
        t = c.get("dutch_text", "")
        if t in got and not (c.get("translations") or {}).get("ar"):
            c.setdefault("translations", {})["ar"] = got[t]
            c["translation_source"] = c.get("translation_source",
                                            "opus-mt-local (de-ar)") + "+mt-ar"
            n += 1
    return n


def _diff_words(correct, wrong):
    """Words in the wrong sentence that aren't in the right one (the actual
    confusables the trap swapped in), longest first."""
    strip = ".,!?…:;«»()\"'"
    have = set(x.strip(strip) for x in correct.lower().split())
    out = [w.strip(strip) for w in wrong.split()
           if w.lower().strip(strip) not in have and len(w.strip(strip)) >= 3]
    return sorted(set(out), key=len, reverse=True)


def fill_ar_word_traps(clips, vocab=()):
    """Word-level trap meanings (the Tische/Teppich/Tasche model): for each
    German trap sentence, find the swapped-in similar-sounding word and look
    up its TRUE Arabic meaning for the Arabic wrong options. Falls back to
    phonetic neighbors of the longest word. Skips clips that already have
    Arabic distractors. Returns number of clips enriched."""
    import difflib
    from glossary import lookup
    n = 0
    for c in clips:
        if not (c.get("translations") or {}).get("ar"):
            continue
        if (c.get("translation_distractors") or {}).get("ar"):
            continue
        correct = c.get("correct_answer", "")
        ar_ok = c["translations"]["ar"]
        hol = []
        for w in c.get("wrong_answers", []):
            for dw in _diff_words(correct, w)[:2]:
                a = lookup(dw)
                if (a and a != ar_ok and a not in hol
                        and abs(len(a) - len(ar_ok)) <= 40):
                    hol.append(a)
                    break
            if len(hol) >= 3:
                break
        if len(hol) < 2 and vocab:
            key = max((x.strip(".,!?…:;«»()\"'") for x in correct.split()),
                      key=len, default="")
            if len(key) >= 4:
                cands = [v for v in vocab
                         if v.lower() != key.lower()
                         and abs(len(v) - len(key)) <= 2]
                for nb in difflib.get_close_matches(key, cands, n=8, cutoff=0.55):
                    a = lookup(nb)
                    if a and a != ar_ok and a not in hol:
                        hol.append(a)
                    if len(hol) >= 3:
                        break
        if hol:
            c.setdefault("translation_distractors", {})["ar"] = hol[:3]
            n += 1
    return n
