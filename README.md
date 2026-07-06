# Newser
Newser is a FastAPI web app that ingests tech news and developer signals, stores them in SQLite, classifies trends with NLP, and uses Gemini to generate concise daily briefs and article summaries.

## Run

Install dependencies:

```powershell
pip install -r requirements.txt
```

Run the web app:

```powershell
python -m uvicorn web_app:app --reload
```
