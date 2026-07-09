# Newser
Newser is a FastAPI web app that ingests tech news and developer signals, stores them in Supabase Postgres when `DATABASE_URL` is configured or local SQLite as the code fallback, classifies trends with NLP, and uses Gemini to generate concise daily briefs and article summaries.

## Run

Install dependencies:

```powershell
pip install -r requirements.txt
```

Run the web app:

```powershell
python -m uvicorn web_app:app --reload
```

## Safe verification

Run automated checks without touching Supabase data or using external API credentials:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify_safe.ps1
```

The script loads local dependencies from `.deps` when present, points `DATABASE_URL` at a temporary SQLite database, clears `GEMINI_API_KEY` and `GITHUB_TOKEN` for the process, then runs Python compilation and the existing `unittest` suite.

## Runtime scheduler health

Check the already-running app and scheduler state without triggering collection or writing to Supabase:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify_runtime_health.ps1 -BaseUrl http://127.0.0.1:8001
```

Use this after code changes, restarts, and deployments to catch runtime-only failures that unit tests cannot see, such as a stale process, an old `latest_ingested_at`, a missing `next_check_at`, or a non-empty scheduler `last_error`. The script also checks `GET /api/health`, a read-only readiness endpoint that verifies database connectivity and scheduler job registration.

## Production readiness

Before promoting a deployment, require both checks to pass:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify_safe.ps1
powershell -ExecutionPolicy Bypass -File scripts/verify_runtime_health.ps1 -BaseUrl https://your-newser-host
```

`/api/health` returns HTTP `200` only when the app can reach the configured database, the scheduler is running, the feed refresh job exists, the daily brief job exists, and the scheduler has no recorded `last_error`. It returns HTTP `503` when any readiness check fails.

## Supabase migration

The code falls back to local SQLite at `news_analyzer.db` only when `DATABASE_URL` is not set. To move local SQLite data to Supabase on the free plan:

1. Create a Supabase project.
2. In the Supabase dashboard, open `Connect` and copy the Session Pooler Postgres URI.
3. Add it to `.env`:

```powershell
DATABASE_URL=postgresql+psycopg://...
```

4. Install dependencies:

```powershell
pip install -r requirements.txt
```

5. Run the migration from this repo root:

```powershell
python scripts/migrate_sqlite_to_supabase.py
```

The script creates the Supabase tables, refuses to copy into non-empty app tables, copies all rows, resets Postgres sequences, and verifies row counts, primary keys, and existing `noticias.cluster_id` soft links.
