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
