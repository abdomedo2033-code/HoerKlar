# Dutch Voscreen-style App — MVP Skeleton

Remote-play only. No video hosted. See `docs/REPORT.md` for full architecture and source matrix.

## Quick start
```bash
supabase db push --file db/schema.sql
npm i && npm run dev           # Next.js frontend (player adapters in /player)
uvicorn api.main:app --reload  # FastAPI ingestion (OAI-PMH harvest)
python scripts/harvest_openbeelden.py --query "dutch" --limit 30
```

## Key files
- `providers/types.ts` — neutral VideoProvider interface + RightsStatus
- `providers/openbeelden.ts` — OAI-PMH implementation (backbone)
- `player/html5.ts` — exact start/end control via timeupdate
- `player/youtube.ts` — IFrame API startSeconds/endSeconds
- `db/schema.sql` — Supabase schema
- `docs/REPORT.md` — full report §A–P
```

