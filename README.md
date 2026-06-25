# Newser
Newser is a Streamlit dashboard that ingests tech news and developer signals, stores them in SQLite, classifies trends with NLP, and uses Gemini to generate concise daily and historical insights.

## Run

Install dependencies:

```powershell
pip install -r requirements.txt
```

Run the existing Streamlit app:

```powershell
python -m streamlit run app.py
```

Run the plain HTML/CSS/JS web app:

```powershell
python -m uvicorn web_app:app --reload
```
