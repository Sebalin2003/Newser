# Newser
Newser is a FastAPI web app that ingests tech news and developer signals, stores them in SQLite or Supabase Postgres, classifies trends with NLP, and uses Gemini to generate concise daily briefs and article summaries.

## Run

Install dependencies:

```powershell
pip install -r requirements.txt
```

Run the web app:

```powershell
python -m uvicorn web_app:app --reload
```

## Supabase migration

The app defaults to local SQLite at `news_analyzer.db`. To move the current data to Supabase on the free plan:

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
