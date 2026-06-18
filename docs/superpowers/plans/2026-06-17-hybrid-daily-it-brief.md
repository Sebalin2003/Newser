# Hybrid Daily IT Brief Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Spanish hybrid daily IT brief that combines curated global IT news with local Developer Pulse signals and renders visible clickable citations.

**Architecture:** Add a focused global-news normalization module, store structured citation data on the existing `MacroResumen`, and update the macro brief generator to synthesize global news plus local GitHub/Hacker News signals through Gemini. The UI renders structured JSON when available and falls back to the legacy text field.

**Tech Stack:** Python 3.12, Streamlit, SQLite/SQLAlchemy, feedparser/requests, google-genai.

## Global Constraints

- Gemini remains the only AI provider.
- Gemini must never invent citations; the UI renders only URLs from source records produced before the Gemini call.
- Global sources are Reuters, GitHub Blog, OpenAI Blog, and WSJ-originated stories only when reported by Reuters.
- The visible brief is Spanish and includes clickable citations/links.
- The implementation must preserve existing local feed, filtering, and individual summary behavior.
- Reuters access should be resilient: support RSS/discovery where available and degrade gracefully if Reuters blocks or returns no feed.
- The project directory is not currently a git repo, so commit steps are skipped in this workspace.

---

### Task 1: Structured Brief Models And Persistence

**Files:**
- Modify: `src/database.py`
- Test: `tests/test_hybrid_brief.py`

**Interfaces:**
- Produces: `MacroResumen.brief_json: str | None`
- Produces: `migrar_schema()` adds nullable `brief_json TEXT` to existing `macro_resumenes`

- [ ] **Step 1: Write the failing test**

```python
from sqlalchemy import inspect

from src.database import engine, init_db


def test_macro_resumen_has_brief_json_column():
    init_db()
    columns = {column["name"] for column in inspect(engine).get_columns("macro_resumenes")}
    assert "brief_json" in columns
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_hybrid_brief.TestSchema.test_macro_resumen_has_brief_json_column`
Expected: FAIL because `brief_json` is not present.

- [ ] **Step 3: Write minimal implementation**

Add `brief_json = Column(Text, nullable=True)` to `MacroResumen`, and add migration DDL:

```python
if "macro_resumenes" in existing_tables:
    existing_cols_mr = {col["name"] for col in inspector.get_columns("macro_resumenes")}
    nuevas_columnas_mr = {
        "brief_json": "ALTER TABLE macro_resumenes ADD COLUMN brief_json TEXT",
    }
    with engine.begin() as conn:
        for col_name, ddl in nuevas_columnas_mr.items():
            if col_name not in existing_cols_mr:
                conn.execute(text(ddl))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_hybrid_brief.TestSchema.test_macro_resumen_has_brief_json_column`
Expected: PASS.

### Task 2: Global News Source Normalization

**Files:**
- Create: `src/global_news.py`
- Test: `tests/test_hybrid_brief.py`

**Interfaces:**
- Produces: `GlobalNewsItem` dataclass with `title`, `source`, `url`, `published_at`, `excerpt`, `category`, `score`
- Produces: `normalize_global_item(title, source, url, published_at=None, excerpt="", category="IT", score=0) -> GlobalNewsItem | None`
- Produces: `dedupe_global_items(items: list[GlobalNewsItem]) -> list[GlobalNewsItem]`
- Produces: `fetch_global_news(max_items: int = 10, timeout: int = 12) -> list[GlobalNewsItem]`

- [ ] **Step 1: Write the failing test**

```python
from src.global_news import dedupe_global_items, normalize_global_item


def test_normalize_global_item_rejects_untrusted_source_and_dedupes_urls():
    trusted = normalize_global_item(
        title="GitHub improves Copilot context handling",
        source="GitHub Blog",
        url="https://github.blog/ai-and-ml/example",
        excerpt="Copilot reduces context waste.",
        category="Developer Tools",
        score=5,
    )
    untrusted = normalize_global_item(
        title="Random rumor",
        source="Random Blog",
        url="https://example.com/rumor",
    )
    duplicate = normalize_global_item(
        title="Same story",
        source="GitHub Blog",
        url="https://github.blog/ai-and-ml/example",
        score=1,
    )

    assert untrusted is None
    assert trusted is not None
    assert [item.url for item in dedupe_global_items([trusted, duplicate])] == [
        "https://github.blog/ai-and-ml/example"
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_hybrid_brief.TestGlobalNews.test_normalize_global_item_rejects_untrusted_source_and_dedupes_urls`
Expected: FAIL because `src.global_news` does not exist.

- [ ] **Step 3: Write minimal implementation**

Create source whitelisting for Reuters, GitHub Blog, and OpenAI Blog. Use `feedparser` for GitHub/OpenAI feeds. For Reuters, try configured RSS/search endpoints if reachable and return an empty list on failures.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_hybrid_brief.TestGlobalNews.test_normalize_global_item_rejects_untrusted_source_and_dedupes_urls`
Expected: PASS.

### Task 3: Hybrid Brief Assembly

**Files:**
- Modify: `src/processor.py`
- Test: `tests/test_hybrid_brief.py`

**Interfaces:**
- Produces: `build_hybrid_brief_payload(global_items: list[GlobalNewsItem], local_items: list[dict[str, Any]], fecha: date) -> dict[str, Any]`
- Produces: `_parsear_brief_json(raw: str, source_records: list[dict[str, str]]) -> dict[str, Any]`
- Updates: `generar_macro_resumen_dia()` uses global items plus local signals, sends compact evidence to Gemini, persists `brief_json`

- [ ] **Step 1: Write the failing test**

```python
from datetime import date

from src.global_news import normalize_global_item
from src.processor import build_hybrid_brief_payload


def test_build_hybrid_brief_payload_limits_sources_and_preserves_urls():
    global_items = [
        normalize_global_item(
            title=f"Reuters story {i}",
            source="Reuters",
            url=f"https://www.reuters.com/technology/story-{i}/",
            excerpt="A relevant IT story.",
            score=20 - i,
        )
        for i in range(12)
    ]
    local_items = [{"title": f"Repo {i}", "source": "GitHub Trending", "url": f"https://github.com/x/{i}", "score": i} for i in range(20)]

    payload = build_hybrid_brief_payload(global_items, local_items, date(2026, 6, 17))

    assert payload["date"] == "2026-06-17"
    assert len(payload["global_news"]) == 10
    assert len(payload["developer_signals"]) == 15
    assert payload["global_news"][0]["url"].startswith("https://www.reuters.com/")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_hybrid_brief.TestHybridPayload.test_build_hybrid_brief_payload_limits_sources_and_preserves_urls`
Expected: FAIL because `build_hybrid_brief_payload` does not exist.

- [ ] **Step 3: Write minimal implementation**

Add payload construction, prompt generation, structured JSON parsing, and fallback legacy text. Ensure citation URLs in parsed output are filtered against payload source URLs.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_hybrid_brief.TestHybridPayload.test_build_hybrid_brief_payload_limits_sources_and_preserves_urls`
Expected: PASS.

### Task 4: UI Rendering With Clickable Citations

**Files:**
- Modify: `app.py`
- Test: `tests/test_hybrid_brief.py`

**Interfaces:**
- Produces: `_render_brief_json(brief: dict[str, Any]) -> None`
- Updates: `_obtener_macro_resumen_hoy()` returns `brief_json`
- Updates: `_render_macro_resumen_card()` renders structured brief when available and falls back to `texto`

- [ ] **Step 1: Write the failing test**

```python
from app import _normalizar_citas_brief


def test_normalizar_citas_brief_keeps_only_source_urls():
    item = {
        "title": "Fortinet credential campaign",
        "summary": "Attackers abused leaked credentials.",
        "why_it_matters": "MFA and rotation matter.",
        "sources": [
            {"name": "Reuters", "url": "https://www.reuters.com/world/example/"},
            {"name": "Invented", "url": "https://fake.example/story"},
        ],
    }
    allowed = {"https://www.reuters.com/world/example/"}

    normalized = _normalizar_citas_brief(item, allowed)

    assert normalized["sources"] == [
        {"name": "Reuters", "url": "https://www.reuters.com/world/example/"}
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_hybrid_brief.TestBriefUi.test_normalizar_citas_brief_keeps_only_source_urls`
Expected: FAIL because `_normalizar_citas_brief` does not exist.

- [ ] **Step 3: Write minimal implementation**

Add helper normalization and renderer. Render citations as Markdown links: `[Reuters](https://...)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_hybrid_brief.TestBriefUi.test_normalizar_citas_brief_keeps_only_source_urls`
Expected: PASS.

### Task 5: End-To-End Verification

**Files:**
- Modify only if verification exposes a defect in previous tasks.

**Interfaces:**
- Verifies: `python -m unittest tests.test_hybrid_brief`
- Verifies: `python -m compileall app.py src tests`
- Verifies: `python -c "from src.processor import generar_macro_resumen_dia; print('import ok')"`
- Verifies: render `http://localhost:8501/` with Playwright and confirm no traceback.

- [ ] **Step 1: Run unit tests**
- [ ] **Step 2: Compile app and modules**
- [ ] **Step 3: Restart Streamlit**
- [ ] **Step 4: Browser-render the home page**
- [ ] **Step 5: Confirm the brief area renders legacy fallback or structured brief without traceback**
