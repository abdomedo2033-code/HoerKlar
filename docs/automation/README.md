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

## Deploy (Render) — full path

1. **API**: Render → Blueprints → New → repo `HoerKlar`, blueprint file
   `server/render.yaml` → Apply. Service `hoerklar-api` appears (~2 min build;
   `split_clips.py` runs at build time from tracked `app/clips_modern_fixed.json`).
   Set `HK_WORKER_TOKEN` (any long random string) in its Environment tab.
2. **Site**: `index.html` on this branch already contains the ＋ Add video button,
   modal, ⭐ My videos section, and boot-merge. `HK_API_BASE` defaults to
   `https://hoerklar-api.onrender.com`; if your URL differs, run once in console:
   `localStorage.hk_api="https://<actual>"; location.reload()`.
   Rebuild the APK (or sideload updated `index.html` + `web/`) to ship it.
3. **Deck worker**: on the Deck —
   ```
   cat >> ~/.config/hoerklar-worker.env <<EOF
   API_BASE=https://hoerklar-api.onrender.com
   HK_WORKER_TOKEN=<same as Render>
   EOF
   systemctl --user enable --now deck-worker   # after: cp worker/deck-worker.service ~/.config/systemd/user/
   ```
   Without the token (default empty) the API accepts worker calls — set it.
4. **Test**: open site → ＋ Add video → paste subtitled YouTube URL →
   job card progresses → quizzes land in ⭐ My videos. Local drill that already
   passed on the Deck: `api_server` + `worker --once` turned Nicos Weg ep
   `dC6ZGLzdaTs` into 2 verified=false clips end-to-end.

Known limits: Render free disk is ephemeral (back up `myvideos` before redeploy);
movies without subs stay slow-path; auto-added clips are personal-only until a
human glances at them (see Rights below).

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
