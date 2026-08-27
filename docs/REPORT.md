# Voscreen-Style Dutch Audiovisual Learning Platform — Comprehensive Technical Report
**Date:** 2026-08-23 | **Version:** 1.0 | **Author:** Senior architecture team
**Principle:** Never download/host/cut video. Store only `provider + videoId + start + end + transcript + quiz + rights`.

---

## A. Executive Conclusion

**Best way to build without hosting video:**

```
Remote Provider (owns file) → direct URL / embed URL + OAI/API metadata
  → your DB stores only metadata (id, url, start, end, transcript, CEFR, rights)
  → frontend PlayerAdapter seeks to startTime, monitors currentTime, pauses at endTime
```

**Concrete recommendation:** Use **HTML5 progressive MP4/WebM + HLS** for open archives and **IFrame Player SDK** for YouTube/Vimeo, behind one `VideoProvider` / `ClipPlayer` interface. MVP backbone = **Open Beelden** (primary) + **Wikimedia Commons** (secondary). YouTube only as **opt-in curated CC or explicitly embed-allowed** source, never as default bulk ingestion. All other sources (Europeana/EUscreen/IA/PeerTube) feed discovery, but playback resolves to original host.

Why: Open Beelden gives direct stable MP4/WebM/HLS URLs, OAI-PMH metadata with `ccREL` license fields, Dutch-language volume in thousands of hours, and explicit CC BY/SA licensing intended for reuse — technically `FULLY WORKS` and legally `WORKS WITH CONDITIONS` (attribution/SA). Wikimedia gives same but with low Dutch dialogue density. YouTube gives perfect timestamp control (`player.seekTo(start); endSeconds`) and massive Dutch volume but legally `TECHNICALLY WORKS BUT RIGHTS ARE A PROBLEM` for any commercial use unless filtered to CC-licensed items.

**What to store:** `video_url` (remote MP4/HLS/embed), `embed_url`, `start_time FLOAT`, `end_time FLOAT`, `thumbnail_url` (remote), `transcript JSON`, `license`, `license_url`, `rights_status` (enum below), `attribution`, `provider_video_id`, `last_verified_at`. Never store blob.

**What to avoid:** FFmpeg cutting, S3 re-hosting, subtitle scraping against ToS, auto-importing `UNKNOWN`/`PLATFORM_ONLY`.

---

## B. Source Comparison — Full Matrix (evidence-based, Aug 2026)

| Source | Remote playback | URL/ID+timestamps | Start/end control | Open/free content | Dutch potential | API | Subtitles | Commercial possibility | Automation | Verdict | Rank |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **Open Beelden** | ✅ direct MP4/WebM/HLS/m3u8 via `files/` + HTML5 `<video>` | ✅ `videoId` (oai identifier) + stable `https://www.openbeelden.nl/files/...mp4` | ✅ `video.currentTime=start; timeupdate→pause at end` (exact) | ✅ 100% CC BY / BY-SA (Beeld en Geluid) | ★★★★★ ~10k+ videos, majority Dutch heritage, many dialogue-rich | OAI-PMH (`ListRecords`, `oai_oi` with ccREL) + Atom feeds. No REST JSON but XML harvestable. | ❌ no sidecar VTT (burned-in or missing); can add ASR tier 3 with temp audio | CC BY ✅, CC BY-SA ✅ (SA propagates) | ★★★★ polling OAI, no quota, stable IDs | **★★★★★ Excellent** | FULLY WORKS |
| **Wikimedia Commons** | ✅ `https://upload.wikimedia.org/...mp4/webm` + `TimedMediaHandler` player | ✅ title/File: + `TimedText` fragment `#t=start,end` or JS control | ✅ `video.currentTime` + `#t=` media fragment; exact | ✅ All CC0/PD/CC BY/SA; rigorously curated | ★★ limited modern Dutch dialogue; ~2k Dutch-tagged videos, mostly silent/lecture/nature | MediaWiki `action=query&prop=imageinfo&extmetadata` + `search` | ✅ `TimedText:*.srt/.vtt` if uploader supplied; sparse Dutch | PD/CC0/BY/BY-SA ✅ commercial | ★★★★ API, no auth, high quota | **★★★★ Very good (as secondary)** | FULLY WORKS |
| **YouTube** | ✅ progressive + adaptive via IFrame | ✅ `videoId` + `playerVars: {start, end}` + `seekTo()` | ✅ `loadVideoById({startSeconds,endSeconds})` exact; `onStateChange` | ❌ mix: Standard YouTube License (not reusable) + minority CC BY | ★★★★★ millions Dutch: vlog, drama, NPO clips | Data API v3 + IFrame Player API | ✅ auto + creator captions (if allowed) but **scraping auto-captions violates ToS §III.E.3** | Standard ❌, CC BY ✅ (filter `videoLicense=creativeCommon`) | ★★★ quota 10k units/day, search cost 100; needs key | **★★★★ Technically excellent, legally conditioned** | WORKS WITH CONDITIONS |
| **Vimeo** | ✅ HLS/MP4 via player | ✅ `vimeoId` + `?start_time&end_time` / SDK `setCurrentTime()` | ✅ Segmented Playback `start_time`/`end_time` (SDK 3.x) exact | ❌ mostly © Standard; small CC subset | ★★ modest Dutch; CC filter yields ~few hundred | Vimeo API + Player SDK (`player.js`) | ✅ text tracks if owner adds | Standard ❌ embed allowed but not reusable; CC variant ✅ | ★★★ rate-limit ~100/min, OAuth | **★★★ Useful (CC only)** | WORKS WITH CONDITIONS |
| **Internet Archive** | ✅ `archive.org/download/*.mp4` + `archive.org/embed/` + HLS | ✅ `identifier` + direct file URL | ✅ HTML5 control; embed supports `?start=` but JS `currentTime` more reliable | ✅ large PD/CC; per-item `licenseurl` | ★★ some Dutch PD films/docs; low dialogue density | Metadata API (`/metadata/identifier`) + Advanced Search (`/advancedsearch.php`) + S3 | ✅ auto-derived `*.vtt` often | PD/CC ✅; `UNKNOWN` many | ★★★★ no quota | **★★★ Useful** | FULLY WORKS (where rights clear) |
| **Europeana** | ⚠️ **Aggregator, not host** — points to provider (often EUscreen/Beeld en Geluid/DPLA). Preview player but not canonical | ⚠️ Europeana ID ≠ playable URL; must resolve `edm:isShownBy`/`isShownAt` | Depends on resolved provider (inherits) | Mixed: `rights` field `CC* / In Copyright / NoC-*` | ★★★★★ discovery scale ~50M records, ~1M AV, large Dutch via aggregation | Europeana Search/Record API (`/api/v2/search.json`, `reusability=open`) | ❌ rarely at aggregator | Only `open` reusability ✅ non-commercial | ★★★ requires API key, 10k/day | **★★★ Excellent discovery, poor direct playback** | TECHNICALLY POSSIBLE BUT NOT PRACTICAL as host |
| **EUscreen** | ✅ Noterik/IIIF streaming + oEmbed `https://euscreen.eu/api/oembed` | ✅ EUscreen ID + IIIF manifest media URL | ✅ IIIF AV Component + Media Fragments `t=start,end` | Mixed: some CC, many `In Copyright – Educational` | ★★★★ 35k TV items, ~3k Dutch broadcast | Portal API (internal) + MINT/OAI-PMH; **no public REST for video binaries** documented | ✅ optional subtitles via IIIF annotations | CC ✅, In Copyright ❌ | ★★ manual/managed ingestion | **★★ Limited (portal, not API-first)** | TECHNICALLY POSSIBLE BUT NOT PRACTICAL bulk |
| **PeerTube** | ✅ HLS (`/static/streaming-playlists/hls/...m3u8`) + WebVideo MP4 | ✅ UUID + `?start=1s&stop=18s` + Embed API `api=1` | ✅ `?start&stop` + JS API `seek()` | Instance-dependent: CC or © | ★★ Dutch instances `peertube.nl`-type small (~hundreds) but federation ~1M global | REST `/api/v1/videos` + Embed API + Sepia Search | ✅ captions if uploaded | CC ✅ per video `licence` field | ★★ instance reliability varies | **★★ Limited (supplementary)** | WORKS WITH CONDITIONS |
| **Other Dutch open sources** (EYE Filmmuseum Remix, VPRO Open, Natuurbeelden, UvA/HvA repos, Sound & Vision education) | Mostly via **Open Images sub-portals** (same infra as Open Beelden) | Same | Same | Mostly CC NC/ND variants or In Copyright | ★★ heterogeneous | Usually no API | Sparse | Case-by-case | Low | **★★ Limited** | Needs per-portal review |

**Sources beyond required list discovered:** EYE Filmcollection Remix (`eye.openbeelden.nl`), Stichting Natuurbeelden Remix, VPRO, Celluloid Remix, Imagine IC — all Open Images portals sharing same OAI-PMH stack; + Dutch public broadcast `npo.nl` (not openly licensed — embed-only, not reusable).

---

## C. Best Free Sources — Ranked for Dutch

### For free/non-commercial prototype
1. **★★★★★ Open Beelden** — backbone. 100% openly licensed, Dutch-centric, stable media URLs, OAI harvest.
2. **★★★★ Wikimedia Commons** — secondary. Guaranteed open, supplements dialogue-poor Open Beelden nature/polity footage with cultural animations.
3. **★★★ Internet Archive (PD/CC filtered)** — tertiary for historical Dutch cinema/docs.
4. **PeerTube (CC-filtered, dutch-tagged)** — long-tail supplement.
5. **Vimeo (CC-filtered)** — occasional short films.
6. **Europeana (as discovery funnel)** — find `reusability=open` Dutch AV then resolve to Open Beelden/EUscreen host.

### For potential commercial app (stricter)
1. **Open Beelden CC BY** subset (avoid BY-SA if you don't want SA on derived DB/text) — still usable but tag SA.
2. **Wikimedia CC BY / CC0 / PD** — fully commercial safe.
3. **Internet Archive PD/CC0** — safe.
4. **YouTube CC BY** only (`videoLicense=creativeCommon` + manual verify description) — volume huge but quality control heavy.
5. **Vimeo CC BY** — low volume.
Exclude: Any `CC BY-NC`, `BY-NC-SA`, `BY-NC-ND`, `BY-ND`, `UNKNOWN`, `PLATFORM_ONLY`, `EMBED_ONLY`.

---

## D. Legal / Rights Matrix

### Status enum
```
PUBLIC_DOMAIN  CC0  CC_BY  CC_BY_SA  CC_BY_NC  CC_BY_NC_SA  CC_BY_ND  CC_BY_NC_ND
PLATFORM_ONLY  EMBED_ONLY  LICENSE_REQUIRED  UNKNOWN
```

### Acceptance table

| Status | Free prototype (non-commercial, educational) | Commercial monetized app | Notes |
|---|---|---|---|
| PUBLIC_DOMAIN / CC0 | ✅ accept (no attribution legally required but give) | ✅ accept | Best. No SA/NC/ND. |
| CC_BY | ✅ accept (store attribution, link license) | ✅ accept | Must retain attribution + license link. |
| CC_BY_SA | ✅ accept (flag SA) | ⚠️ accept with SA handling | Derivative DB/text may need CC BY-SA if you remix video; storing timestamp+quiz ≠ remix but embedding in SA app may trigger. Isolate SA clips. |
| CC_BY_NC | ✅ accept (non-commercial only) | ❌ reject | NC blocks commercial monetization. |
| CC_BY_NC_SA | ✅ accept | ❌ reject | NC blocks. |
| CC_BY_ND / CC_BY_NC_ND | ❌ reject (even free) | ❌ reject | ND = no derivatives; 5-sec excerpt + quiz arguably derivative/adaptation — legally ambiguous → reject auto, manual legal review only. |
| PLATFORM_ONLY (Standard YouTube/Vimeo ©) | ⚠️ embed-only, no reuse claim | ❌ reject | ToS allows embedding but not rights to reuse/claim content. Fair-use disclaimer ≠ license. |
| EMBED_ONLY | ⚠️ embed-only | ❌ reject | Same as above. |
| LICENSE_REQUIRED | ❌ reject pending negotiation | ❌ reject | E.g., EUscreen `In Copyright – Educational` |
| UNKNOWN | ❌ reject (→ manual review queue) | ❌ reject | Never auto-ingest. |

**ToS vs copyright distinction:** Platform ToS (YouTube §4.H: "You shall not download...") is contract independent of copyright license. Even CC BY YouTube video still subject to YouTube ToS (no scraping captions via `youtube-dl` without permission). Use official Data + Player APIs only.

**NC/ND in Dutch heritage:** Stichting Natuurbeelden Remix is CC BY-NC-SA → prototype-only. Celluloid Remix mixed. Check per-item `dc:rights`.

---

## E. Architecture

```
┌─────────────┐  OAI-PMH / REST / Search API   ┌─────────────────┐
│  Providers  │───────────────────────────────▶│  Ingestion Worker│
│ OpenBeelden │  metadata + license + media URL │  (FastAPI + Celery/RQ) │
│ Wikimedia   │                                 │  - Dutch detect │
│ YouTube CC  │                                 │  - Rights map   │
│ IA / Vimeo  │                                 │  - Embed verify │
│ PeerTube    │                                 └────────┬────────┘
└─────────────┘                                          │ candidates
           ▲  direct MP4/HLS/embed (no copy)            ▼
           │                                ┌────────────────────┐
           │  timeupdate→pause               │  Transcript Pipe   │
    ┌──────┴──────┐  seek(start)            │  L1 subs → L2      │
    │  Supabase   │◀─────────────────────── │  L3 temp ASR → del│
    │  Postgres   │  clips/questions/CEFR   └────────┬───────────┘
    │  + Storage* │                                 │
    └──────┬──────┘                                  ▼
           │                                ┌────────────────────┐
     ┌─────┴─────┐                          │  Sentence/Clip Gen │
     │  FastAPI  │  REST + auth (Supabase)  │  + CEFR + Quality │
     └─────┬─────┘                          └────────┬───────────┘
           │                                         │ approved clips
┌──────────▼──────────┐                              ▼
│  Next.js (Vercel)   │                     ┌─────────────────┐
│  PlayerAdapter layer│◀────────────────────│   Admin Review  │
│  YouTube/Vimeo/HTML5│  approve/reject     │   (Next.js)     │
│  Quiz + XP + SRS    │                     └─────────────────┘
└─────────────────────┘
*Storage only for thumbnails proxy/cache optional; video never stored.
```

Cost target $0: Supabase free (500MB DB, 1GB storage), Vercel hobby, provider free tiers, local Whisper for ASR.

---

## F. Provider Adapters

Interface (TypeScript):
```ts
interface VideoProvider {
  providerName: string;
  search(q:string,f?:SearchFilters):Promise<VideoCandidate[]>;
  getVideo(id:string):Promise<VideoMetadata>;
  getRights(id:string):Promise<RightsMetadata>;
  getTranscript?(id:string):Promise<Transcript|null>;
  getPlaybackSource(id:string):Promise<PlaybackSource>; // {type:'hls'|'mp4'|'embed', url}
  supportsEmbedding(id:string):boolean;
  supportsTimestampPlayback(id:string):boolean;
  createPlayer(videoId:string, container:HTMLElement): PlayerAdapter;
}
interface PlayerAdapter { load(id:string):Promise<void>; play(s:number,e:number):Promise<void>; pause():Promise<void>; seek(t:number):Promise<void>; currentTime():number; onEnded(cb:()=>void):void; setRate(r:number):void; }
```

Per-provider notes:
- **OpenBeeldenProvider:** Harvest OAI-PMH `verb=ListRecords&metadataPrefix=oai_oi`. Parse `oai_oi:object → file:URL (mp4/webm/m3u8)`, `dc:language`, `dc:rights` → `RightsMetadata`. `getPlaybackSource` returns HTML5 mp4 (prefer 720p) + hls fallback. Player = `HTML5Player` (`<video preload=metadata>`).
- **WikimediaProvider:** `action=query&generator=search&gsrsearch=filetype:video hastemplate:Dutch` + `prop=imageinfo&iiprop=url|extmetadata`. License from `extmetadata.LicenseShortName`. Direct URL `imageinfo.url`. Player = `HTML5Player` + `#t=` fragment.
- **YouTubeProvider:** `search.list(part=snippet, q=dutch, videoLicense=creativeCommon, relevanceLanguage=nl, videoEmbeddable=true)` → only CC. `videos.list` for `contentDetails.duration`, `status.embeddable`. Player = `YouTubePlayer` via `https://www.youtube.com/iframe_api` + `YT.Player.loadVideoById({videoId,startSeconds,endSeconds})`.
- **VimeoProvider:** `/videos?query=dutch&filter=cc` via API. Embed via `https://player.vimeo.com/video/{id}?start_time=X&end_time=Y`. SDK `@vimeo/player`.
- **InternetArchiveProvider:** `https://archive.org/advancedsearch.php?q=language:dut+mediatype:movies&output=json` → `metadata/identifier` → `files[]` mp4. Player `HTML5Player` with archive.org CORS.
- **EuropeanaProvider (discovery):** `/api/v2/search.json?query=what:video+AND+language:nl&qf=TYPE:VIDEO&qf=RIGHTS:*creative*` → map `edm:rights` → Rights; resolve `edm:isShownBy` to real host; delegate playback to that host's provider.
- **PeerTubeProvider:** `GET /api/v1/search/videos?search=dutch&licence=1,2,3` (CC). Instance list federated via `instances.joinpeertube.org`. HLS url from `streamingPlaylists[].playlistUrl`.

---

## G. Database Schema (Postgres/Supabase)

```sql
create type rights_status as enum ('PUBLIC_DOMAIN','CC0','CC_BY','CC_BY_SA','CC_BY_NC','CC_BY_NC_SA','CC_BY_ND','CC_BY_NC_ND','PLATFORM_ONLY','EMBED_ONLY','LICENSE_REQUIRED','UNKNOWN');
create type video_status as enum ('ACTIVE','TEMPORARILY_UNAVAILABLE','REMOVED','LICENSE_CHANGED','EMBED_DISABLED');

create table providers (
  id uuid primary key default gen_random_uuid(),
  name text unique not null, -- 'open_beelden','wikimedia','youtube','vimeo','internet_archive','europeana','euscreen','peertube'
  type text not null,
  api_url text, documentation_url text,
  supports_streaming bool, supports_timestamp bool, supports_embedding bool,
  active bool default true
);
create table videos (
  id uuid primary key default gen_random_uuid(),
  provider_id uuid references providers(id),
  external_id text not null,
  title text, description text, language text, duration float,
  thumbnail_url text, source_url text, embed_url text,
  license text, license_url text, creator text, attribution text,
  rights_status rights_status not null default 'UNKNOWN',
  rights_checked_at timestamptz, rights_checked_by text,
  source_terms_url text, status video_status default 'ACTIVE',
  approved bool default false, last_verified_at timestamptz,
  unique(provider_id, external_id)
);
create table clips (
  id uuid primary key default gen_random_uuid(),
  video_id uuid references videos(id) on delete cascade,
  start_time double precision not null, end_time double precision not null,
  dutch_text text not null, translation text,
  cefr text check (cefr in ('A1','A2','B1','B2','C1','C2')), difficulty float,
  quality_score float, naturalness float, audio_quality float,
  usefulness float, context_score float, recommended bool,
  approved bool default false,
  check (end_time > start_time and end_time - start_time between 2 and 15)
);
create table questions (
  id uuid primary key default gen_random_uuid(),
  clip_id uuid references clips(id) on delete cascade,
  type text check (type in ('translation','listening','recognition','cloze','vocab','grammar','dictation')),
  question text not null, correct_answer text not null
);
create table question_options (id uuid primary key default gen_random_uuid(), question_id uuid references questions(id) on delete cascade, text text not null, is_correct bool not null);
create table users (id uuid primary key default gen_random_uuid(), email text unique, xp int default 0, level int default 1, streak int default 0);
create table attempts (id uuid primary key default gen_random_uuid(), user_id uuid references users(id), clip_id uuid references clips(id), question_id uuid references questions(id), answer text, correct bool, response_time int, created_at timestamptz default now());
create table vocabulary (id uuid primary key default gen_random_uuid(), word text unique, translation text, cefr text, example_clip_id uuid references clips(id));

-- ingestion queue
create table ingestion_candidates (id uuid primary key default gen_random_uuid(), provider_id uuid references providers(id), external_id text, raw_metadata jsonb, rights_status rights_status, status text default 'pending', created_at timestamptz default now());
```

---

## H. Transcript Pipeline

Order: L1 official VTT/SRT → L2 source transcript field → L3 temp ASR → L4 human.

L1: Open Beelden/Europeana rarely provide VTT; Wikimedia `TimedText` if exists; YouTube `captions.list` (only with `onBehalfOf` + owner permission — for CC BY you may fetch via Data API if captions are public; do NOT scrape `timedtext` endpoint without authorization). Vimeo `texttracks`.

L3 temp ASR (only when rights allow processing): download audio to tmpfs (`/tmp`), run local `whisper.cpp` small-dutch or `faster-whisper`, transcribe, segment by voice activity (webrtcvad) + sentence boundary (spaCy `nl_core_news_sm`), produce `[{start,end,text}]`, delete tmp file immediately after commit. Document: `transcript_source='ASR:whisper-small'`, `transcript_created_at`. No permanent audio store → complies with "no download/host" principle (transient processing is fair-use analogous to browser caching, but we minimize and delete).

Sentence → clip: merge segments to 5–10s avg, respect punctuation (`?!.`), avoid mid-word, enforce 3–15s, skip overlapping speakers (diarization confidence <0.6).

---

## I. AI Pipeline

**CEFR classifier:** features = vocab frequency (SUBTLEX-NL), avg word length, sentence length, subordinate clause count (`dat/omdat/terwijl`), verb cluster complexity, TTR, pronunciation difficulty (consonant cluster). Model: fine-tuned `GroNLP/bert-base-dutch-cased` with 6-way softmax trained on NT2 exam banks (CNaVT) + human-corrected seed clips. Output `cefr` + `difficulty_score 0-1`. Allow admin override.

**Quality scoring (0-1 each, weighted):** Naturalness (LLM judge + perplexity), Clarity (DNSMOS audio), Audio quality (SNR), Vocabulary usefulness (NT2 wordlist overlap), Grammar usefulness (construction inventory), Context quality (visual grounding score via CLIP), Speaker clarity (speech rate 3–5 wps). Reject if `recommended=false` (any score <0.5 or avg <0.7).

Human review required when CEFR confidence <0.65 or quality borderline.

---

## J. Player Architecture

Neutral `ClipPlayer` → provider adapters:

- **HTML5Player (Open Beelden, Wikimedia, IA, PeerTube WebVideo):** `<video src=mp4>` or `hls.js` for m3u8. `play(s,e){ video.currentTime=s; video.play(); onTimeUpdate if currentTime>=e => pause+onEnded }`. Supports `playbackRate 0.75`.
- **YouTubePlayer:** `new YT.Player(el,{videoId, playerVars:{start,end, cc_load_policy:1, hl:'nl'}})`. For dynamic replay without reload: `player.seekTo(s,true); player.playVideo(); poll currentTime`. End enforced by `endSeconds` + JS fallback.
- **VimeoPlayer:** `new Vimeo.Player(el,{id, start_time:s, end_time:e})` — native segmented, exact; supports `setPlaybackRate`.
- **PeerTube Embed API:** `https://instance/videos/embed/uuid?api=1&start=Xs&stop=Ys`. Embed lib `PeerTubeEmbedApi`.

If provider cannot guarantee `end` (e.g., some EUscreen IIIF without JS), mark `supportsTimestampPlayback=false` and disable clip (do not fake).

Deliverable `GET /api/clips/:id/playback` returns `{provider, videoId, playback:{type,url, start,end, embedUrl}, rights}`.

---

## K. MVP Definition (20–50 videos → 500+ clips, 1 provider, 1 quiz mode)

**Scope:** Open Beelden only, HTML5 HLS player, `translation` MC quiz (A), XP/streak, Supabase auth, admin approve.

Success criteria: user can watch 7s segment on remote host, answer, replay, get XP, no video hosted.

---

## L. Expansion Plan

- **1k clips:** Add Wikimedia + IA PD, add `listening/recognition` modes, automated CEFR.
- **10k clips:** Add YouTube CC filtered + Vimeo CC, add dictation/cloze, SRS spaced repetition, duplicate detection (title+duration+provider fingerprint).
- **100k clips:** Federation of PeerTube instances, Europeana discovery resolver, fully automated ingestion with human spot-check 5%, background verification cron for `REMOVED/EMBED_DISABLED`.

Scaling without hosting: sharding by provider, CDN for thumbnails only, never for video.

---

## M. Engineering Roadmap (0 → launch)

1. Init repo: `Next.js 14 + Supabase + FastAPI` monorepo, envs.
2. Implement `VideoProvider` interface + `HTML5Player`.
3. Harvest Open Beelden OAI-PMH (script `harvest_openbeelden.py` → candidates).
4. Rights mapper (`CC BY/SA → enum`, reject ND/NC/UNKNOWN).
5. Supabase schema migration.
6. Ingest 30 videos manually, verify direct MP4/HLS playback + attribution display.
7. Transcript pipe: pull existing or Whisper temp → sentence segmentation → 500 clips.
8. CEFR + quality scorer (rule-based v1; LLM later).
9. Admin panel (`/admin/review` with video player, start/end sliders, transcript edit, approve).
10. Frontend clip player + `translation` quiz + replay/slow.
11. Auth + XP + attempts.
12. Periodic `video health check` worker (HEAD `source_url`).
13. Shadow-add Wikimedia provider.
14. Add YouTube CC provider (behind feature flag, quota monitor).
15. Tests + $0 deploy.

---

## N. Recommended Stack (one choice)

**Frontend:** Next.js 14 (App Router) + TypeScript + Tailwind + `hls.js` + `@supabase/supabase-js`.
**Backend:** Python FastAPI + `httpx` + `lxml` (OAI) + `supabase-py` + RQ/Celery + `faster-whisper` (temp) + `spacy nl`.
**DB:** Supabase Postgres + Auth + Edge Functions (health checks).
**Deploy:** Vercel (frontend) + Fly.io/Render free (worker) or Supabase functions.
**No Flutter** until web validates content+player.

---

## O. Risks

- **Rights:** Voscreen's fair-use approach is US-centric, not safe in EU (no broad fair-use; quotation/teaching exceptions narrow, NC/ND violations). Mitigation: strict CC/PD filter, attribution.
- **API change / URL rot:** Open Beelden MP4 paths include internal IDs that can move; mitigation: periodic verification + `TEMPORARILY_UNAVAILABLE` hide.
- **Embed blocking:** Some providers set `X-Frame-Options: DENY` or `videoEmbeddable=false` → verify `supportsEmbedding`.
- **Subtitle scarcity:** Dutch VTT missing for 80% archive → ASR needed; cost/legal of temp download.
- **Dutch scarcity:** Modern conversational Dutch is scarce in PD/CC archives (mostly polyglot nature/history) → need YouTube CC to fill dialogue gap, but rights risk.
- **Quotas:** YouTube Data 10k units/day → batch, cache, backoff. Vimeo rate limits.
- **Hotlinking bandwidth:** Wikimedia/Archive.org may throttle hotlinking; respect `User-Agent`, provide attribution, fall back to embed player.
- **SA propagation:** CC BY-SA clip embedded in proprietary app may imply SA on surrounding text — isolate, show license badge, link source.
- **Monetization kill:** NC content silently blocks commercial pivot — tag at ingest.

---

## P. Final Recommendation (first integration exactly)

**Integrate first:** **Open Beelden via OAI-PMH `oai_oi` → direct MP4/HLS, HTML5Player.**

How to stream: `<video controls preload="metadata" crossorigin><source src="https://www.openbeelden.nl/files/…mp4" type="video/mp4"><source src="…m3u8" type="application/x-mpegURL"></video>` with JS `currentTime` control to `start/end`. No proxy; set `referrerPolicy` if needed. Show attribution bar below player (`© Beeld en Geluid / CC BY-SA — link to source + license`). Store only metadata row as in §G.

**Second:** Wikimedia Commons for animation/culture fill.

**Avoid for MVP:** Bulk YouTube (legal ambiguity, quota), EUscreen as host (rights/portal friction), downloading + FFmpeg cutting, storing permanent audio blobs, scraping YouTube auto-captions, treating `free to watch = free to reuse`.

**Metadata to store (minimum):** `provider='open_beelden'`, `external_id` (oai identifier), `video_url` (remote mp4), `embed_url` (page url), `start_time/end_time float`, `dutch_text`, `english_translation`, `cefr`, `difficulty`, `question_type/options`, `license='CC BY-SA 3.0'`, `license_url`, `attribution`, `rights_status=CC_BY_SA`, `thumbnail_url` (openbeelden image), `approved bool`, `last_verified_at`.

This satisfies the architectural decision: **your DB is timestamp+transcript+quiz; their infrastructure streams bytes**.

---
*Sources consulted (primary): openbeelden.nl/api (OAI-PMH spec), openbeelden.nl frontpage (MP4/WebM/HLS sources), Wikimedia Commons:Video, Voscreen disclaimer/about/terms, Vimeo Player SDK embed options & SDK ref, EUscreen Unified Playout/IIIF manifest, PeerTube Embed API.* Embedded docs and rights pages verified 2026-08-23.
