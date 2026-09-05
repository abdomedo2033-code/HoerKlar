# Paste-URL-to-quizzes automation (all 5 phases)

One branch, five increments. Translation fixes stay on `main` — this branch only adds.

## What lands where

| Phase | Files | Status |
|---|---|---|
| 1 clips-as-server-JSON | `scripts/split_clips.py`, `web/clips-loader.js` | ✅ script + loader ready; `index.html` untouched (wiring = 6-line patch, see below) |
| 2 ingest + queue + subtitle fast-path | `server/api_server.py`, `server/queue_store.py`, `server/pipeline_fastpath.py` | ✅ stdlib-only, runs on Render free tier |
| 3 Deck worker | `worker/worker.py`, `worker/deck-worker.service` | ✅ outbound polling, no firewall holes |
| 4 Whisper fallback + progress UI | `worker/whisper_fallback.py`, `web/add-video.js`, `web/add-video.css` | ✅ streams first 3 quizzes early |
| 5 abuse guards + rights | `server/guards.py`, `db/migrations/001_my_videos.sql` | ✅ quotas, allowlist, unverified-by-default |

## Build order (as agreed)

1. **Phase 1 first** — run `python3 scripts/split_clips.py`, serve `server/data/` via
   `server/api_server.py`, then apply the 6-line `index.html` patch below. This is
   also just hygiene: kills the 6MB baked blob.
2. **Phase 2** — deploy `server/api_server.py` to Render (or mount its routes into
   `proxy/yt_proxy.py`; handlers are deliberately small).
3. **Phase 3** — `systemctl --user enable --now deck-worker` on the Deck.
4. **Phase 4** — paste the modal HTML from `web/add-video.js` header into `index.html`.
5. **Phase 5** — `supabase db push --file db/migrations/001_my_videos.sql`; set
   `HK_WORKER_TOKEN`, `HK_MAX_JOBS_PER_DAY`, `HK_ALLOWLIST` env vars.

## Phase 1 — index.html wiring patch (deliberately NOT applied yet)

```html
<script>window.HK_API_BASE = "";</script> <!-- same origin; set Render URL when split -->
<script src="web/clips-loader.js"></script>
<script>
ClipLoader.loadAll(['movies','series','songs','nicos','myvideos']).then(c => {
  clips = c; load();
});
</script>
```
Keep a tiny `window.__SEED_CLIPS` (~20 clips) baked for offline-first boot;
everything else comes from `/api/clips?section=…` with IndexedDB cache.

## API protocol (worker ↔ server)

- `POST /api/ingest {url, user}` → `{job_id, poll}` (guards: allowlist + quotas)
- `GET /api/jobs/next?worker=deck` (header `X-Worker-Token`) → oldest `queued`, claimed
- `POST /api/jobs/<id>/progress {status, stage, progress, clips_ready?}`
- `POST /api/jobs/<id>/complete {clips}` → appended to `clips_myvideos.json`, unverified
- Deck offline → jobs sit in `queued`; worker picks up on next poll. €0, no new hardware.

## Speeds (honest)

- **Subtitled videos**: ~30–60s (subs fetch + align + distractors + MT, all fast).
- **No subtitles**: Whisper-tiny sampling on Deck CPU with progress bar; first 3
  quizzes stream in as ready, rest follow in background.
- Movies without subs stay slow-path. Educational subtitled content (the actual
  use case) is fast-path.

## Rights (honest)

- Auto-added URLs → personal `myvideos`, `verified=false`, `rights_status=EMBED_ONLY`.
- Curated Movies/Series/Songs stay hand-approved; promotion = human glance
  (sample 2–3 clips, check translations, re-check licence).
- Standard YouTube licence ⇒ personal-only, never promoted to shared sections.
