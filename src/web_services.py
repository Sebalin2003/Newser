"""Backend-safe services for the HTML/JS Newser web app."""

from __future__ import annotations

import json
import os
import re
import threading
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import yaml
from dotenv import load_dotenv
from sqlalchemy import and_, func, or_, text
from sqlalchemy.orm import load_only

from src.database import MacroResumen, Noticia, get_session, init_db, limpiar_datos_antiguos
from src.media import fetch_media_preview

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
except Exception:  # pragma: no cover - dependency is optional at runtime
    TfidfVectorizer = None
    cosine_similarity = None

load_dotenv()

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"
BRIEF_TIMEZONE = ZoneInfo("America/Argentina/Buenos_Aires")
FILTER_WINDOW_DAYS = 30
FEED_REFRESH_INTERVAL = timedelta(hours=1)
DAILY_BRIEF_HOUR = 8
ENGLISH_ARCHIVE_BACKFILL_LIMIT = 3
HOT_TOPIC_MIN_SOURCES = 3
HOT_TOPIC_SUPPORT_LIMIT = 5
HOT_TOPIC_SIMILARITY_THRESHOLD = 0.42
HOT_TOPIC_MODEL_ANCHORED_SIMILARITY_THRESHOLD = 0.62
SOURCE_PRIORITY_SORT_BOOST = 4.0
FEED_QUERY_LIMIT = 220
HOT_TOPIC_QUERY_LIMIT = 250
MIN_FEED_SCORE = 50.0
HOT_TOPIC_MODEL_PATTERN = re.compile(
    r"\b(?:gpt|claude|gemini|llama|mistral|qwen|deepseek|grok|o)\s*[-\u2010-\u2015\u2212]?\s*\d+(?:\.\d+)*\b",
    re.IGNORECASE,
)
_refresh_lock = threading.Lock()
_refresh_state: dict[str, Any] = {
    "last_started_at": None,
    "last_finished_at": None,
    "last_error": None,
}
_daily_brief_lock = threading.Lock()
_daily_brief_state: dict[str, Any] = {
    "last_started_at": None,
    "last_finished_at": None,
    "last_error": None,
}
_summary_locks_guard = threading.Lock()
_summary_locks: dict[tuple[str, str], threading.Lock] = {}

SOURCES = [
    "GitHub Trending",
    "Hacker News",
    "Reuters",
    "GitHub Blog",
    "OpenAI Blog",
    "Hugging Face Blog",
]

AREAS = {
    "AI & Agents": "ai_agents",
    "Developer Tools": "developer_tools",
    "Cybersecurity": "cybersecurity",
    "Infrastructure & Cloud": "infrastructure_cloud",
    "Chips & Hardware": "chips_hardware",
}

AREA_LABELS_BY_LANG = {
    "es": {
        "ai_agents": "IA y agentes",
        "developer_tools": "Herramientas dev",
        "cybersecurity": "Ciberseguridad",
        "infrastructure_cloud": "Infraestructura y cloud",
        "chips_hardware": "Chips y hardware",
        "general": "General",
    },
    "en": {
        "ai_agents": "AI & Agents",
        "developer_tools": "Developer Tools",
        "cybersecurity": "Cybersecurity",
        "infrastructure_cloud": "Infrastructure & Cloud",
        "chips_hardware": "Chips & Hardware",
        "general": "General",
    },
}

MESSAGES = {
    "es": {
        "article_not_found": "Artículo no encontrado.",
        "missing_key": "Falta GEMINI_API_KEY. Agregala a .env y reiniciá la app.",
        "source": "Fuente",
        "untitled": "Sin título",
    },
    "en": {
        "article_not_found": "Article not found.",
        "missing_key": "GEMINI_API_KEY is missing. Add it to .env and restart the app.",
        "source": "Source",
        "untitled": "Untitled",
    },
}

AREA_COMPATIBILITY = {
    "inteligencia_artificial": "ai_agents",
    "ai_agents": "ai_agents",
    "arquitectura_software": "developer_tools",
    "ciencias_computacion": "developer_tools",
    "developer_tools": "developer_tools",
    "ciberseguridad": "cybersecurity",
    "cybersecurity": "cybersecurity",
    "cloud_computing": "infrastructure_cloud",
    "data_engineering": "infrastructure_cloud",
    "infrastructure_cloud": "infrastructure_cloud",
    "semiconductores": "chips_hardware",
    "chips_hardware": "chips_hardware",
    "startups_tecnologia": "general",
    "general": "general",
}

AREA_LABEL_BY_KEY = {value: label for label, value in AREAS.items()}
AREA_DB_KEYS_BY_CORE = {
    core: sorted(area for area, mapped in AREA_COMPATIBILITY.items() if mapped == core)
    for core in set(AREA_COMPATIBILITY.values())
}


def normalize_language(lang: str | None = None) -> str:
    return "en" if str(lang or "").strip().lower().startswith("en") else "es"


def t(key: str, lang: str | None = None) -> str:
    selected = normalize_language(lang)
    return MESSAGES[selected].get(key, MESSAGES["es"].get(key, key))


def area_options(lang: str | None = None) -> dict[str, str]:
    selected = normalize_language(lang)
    return {
        AREA_LABELS_BY_LANG[selected][key]: key
        for key in ["ai_agents", "developer_tools", "cybersecurity", "infrastructure_cloud", "chips_hardware"]
    }


def initialize() -> None:
    init_db()
    limpiar_datos_antiguos(dias_retencion=30)


def check_database_connection() -> None:
    with get_session() as session:
        session.execute(text("SELECT 1")).scalar()


def latest_ingested_at() -> datetime | None:
    with get_session() as session:
        return (
            session.query(Noticia.fecha_ingesta)
            .order_by(Noticia.fecha_ingesta.desc())
            .limit(1)
            .scalar()
        )


def is_feed_stale(latest: datetime | None = None, now: datetime | None = None) -> bool:
    latest = latest_ingested_at() if latest is None else latest
    if latest is None:
        return True
    if latest.tzinfo is None:
        latest = latest.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    return now - latest >= FEED_REFRESH_INTERVAL


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def core_area_key(area_key: str | None) -> str:
    return AREA_COMPATIBILITY.get(str(area_key or "general"), "general")


def area_label(area_key: str | None, lang: str | None = None) -> str:
    key = core_area_key(area_key)
    return AREA_LABELS_BY_LANG[normalize_language(lang)].get(key, AREA_LABEL_BY_KEY.get(key, key.replace("_", " ").title()))


def area_filter_keys(area_keys: list[str] | tuple[str, ...]) -> list[str]:
    expanded: list[str] = []
    for key in area_keys:
        core_key = core_area_key(key)
        expanded.extend(AREA_DB_KEYS_BY_CORE.get(core_key, [core_key]))
    return sorted(set(expanded))


def date_bounds(today: date | None = None) -> tuple[date, date]:
    end = today or datetime.now(BRIEF_TIMEZONE).date()
    return end - timedelta(days=FILTER_WINDOW_DAYS - 1), end


def parse_filter_date(value: Any, today: date | None = None) -> date:
    minimum, maximum = date_bounds(today)
    try:
        parsed = date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return maximum
    return parsed if minimum <= parsed <= maximum else maximum


def is_all_dates_filter(value: Any) -> bool:
    return str(value or "").strip().lower() == "all"


def _score_display_fields(n: Noticia, config: dict[str, Any]) -> dict[str, Any]:
    if n.selected_score is not None:
        return {
            "selected_score": n.selected_score,
            "tags_json": n.tags_json or "[]",
            "selection_reason": n.selection_reason or "",
            "score_version": n.score_version or "",
        }
    from src.scoring import SCORE_VERSION, calculate_item_score

    result = calculate_item_score(n, config=config)
    return {
        "selected_score": result.selected_score,
        "tags_json": json.dumps(result.tags, ensure_ascii=False),
        "selection_reason": result.reason,
        "score_version": SCORE_VERSION,
    }


def _discussion_url(n: Noticia) -> str:
    if n.discussion_url:
        return str(n.discussion_url)
    url = str(n.url or "")
    if n.fuente == "Hacker News" and "news.ycombinator.com/item" in url:
        return url
    return ""


def parse_tags(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value if str(v).strip()]
    if not value or str(value) == "nan":
        return []
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(v) for v in parsed if str(v).strip()]


def _metric_from_title(title: str, source: str) -> int:
    if source == "GitHub Trending":
        match = re.search(r"\(\+(\d[\d,]*)", title)
        if match:
            return int(match.group(1).replace(",", ""))
    match = re.search(r"(\d[\d,]*)\s*(?:points|pts)", title, flags=re.IGNORECASE)
    if match:
        return int(match.group(1).replace(",", ""))
    return 0


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return str(value)


def _effective_datetime(item: dict[str, Any]) -> datetime | None:
    source = item.get("fuente")
    raw = item.get("fecha_ingesta") if source == "GitHub Trending" else item.get("fecha_publicacion")
    raw = raw or item.get("fecha_ingesta")
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _serialize_article(n: Noticia, config: dict[str, Any], lang: str | None = None) -> dict[str, Any]:
    selected_lang = normalize_language(lang)
    score = _score_display_fields(n, config)
    tags = parse_tags(score["tags_json"])
    title = str(n.titulo or "")
    label = re.sub(r"^\[\w+\]\s*", "", title).split("(+")[0].strip()[:80]
    summary = str(n.resumen_ia_en or "") if selected_lang == "en" else str(n.resumen_ia or "")
    return {
        "id": str(n.id or ""),
        "titulo": title,
        "label": label,
        "url": str(n.url or ""),
        "discussion_url": _discussion_url(n),
        "fuente": str(n.fuente or ""),
        "area": str(n.area_matcheada or "general"),
        "area_key": core_area_key(n.area_matcheada),
        "area_label": area_label(n.area_matcheada, selected_lang),
        "fecha_publicacion": _iso(n.fecha_publicacion),
        "fecha_ingesta": _iso(n.fecha_ingesta),
        "descripcion": str(n.descripcion_original or ""),
        "resumen_ia": summary,
        "selected_score": float(score["selected_score"] or 0),
        "tags": tags,
        "comments": int(n.num_comentarios or 0),
        "ranking": n.ranking,
        "metric": _metric_from_title(title, str(n.fuente or "")),
        "selection_reason": score["selection_reason"] if selected_lang == "es" else "",
        "is_favorite": bool(n.is_favorite),
        "favorited_at": _iso(n.favorited_at),
        "media_url": str(n.media_url or ""),
        "media_type": str(n.media_type or ""),
        "media_source_url": str(n.media_source_url or ""),
    }


def _matches_date(item: dict[str, Any], selected_date: date) -> bool:
    effective = _effective_datetime(item)
    if effective is None:
        return False
    return effective.astimezone(BRIEF_TIMEZONE).date() == selected_date


def _sort_items(items: list[dict[str, Any]], order: str) -> list[dict[str, Any]]:
    def key(item: dict[str, Any]) -> tuple[float, float]:
        effective = _effective_datetime(item)
        ts = effective.timestamp() if effective else 0
        score = float(item.get("selected_score") or 0)
        if order != "Mas reciente" and item.get("source_preference") == "prioritized":
            score += SOURCE_PRIORITY_SORT_BOOST
        return (ts, score) if order == "Mas reciente" else (score, ts)

    return sorted(items, key=key, reverse=True)


def _canonical_feed_url(url: str) -> str:
    raw = str(url or "").strip()
    if not raw:
        return ""
    parsed = urlsplit(raw)
    query = urlencode(sorted(parse_qsl(parsed.query, keep_blank_values=True)))
    path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, query, ""))


def _canonical_feed_title(title: str) -> str:
    text = re.sub(r"^\[\w+\]\s*", "", str(title or ""))
    text = re.sub(r"⭐\s*[\d,]+", "", text)
    text = re.sub(r"🔺\s*[\d,]+", "", text)
    text = re.sub(r"\(\+[\d,]+\s+[^)]*\)", "", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def _feed_dedupe_key(item: dict[str, Any]) -> str:
    url = _canonical_feed_url(str(item.get("url") or ""))
    if url:
        return f"url:{url}"
    title = _canonical_feed_title(str(item.get("titulo") or item.get("label") or ""))
    return f"title:{str(item.get('fuente') or '').lower()}:{title}"


def _dedupe_feed_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        key = _feed_dedupe_key(item)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _search_condition(session: Any, query_text: str) -> Any:
    if session.bind and session.bind.dialect.name == "postgresql":
        terms = re.findall(r"[A-Za-z0-9]+", query_text.lower())
        if not terms:
            pattern = f"%{query_text}%"
            return or_(Noticia.titulo.ilike(pattern), Noticia.descripcion_original.ilike(pattern))
        document = (
            func.coalesce(Noticia.titulo, "")
            + " "
            + func.coalesce(Noticia.descripcion_original, "")
        )
        vector = func.to_tsvector(
            "simple",
            document,
        )
        return vector.op("@@")(
            func.to_tsquery("simple", " & ".join(f"{term}:*" for term in terms))
        )
    pattern = f"%{query_text}%"
    return or_(
        Noticia.titulo.ilike(pattern),
        Noticia.descripcion_original.ilike(pattern),
    )


def _date_condition(selected_date: date) -> Any:
    start = datetime(
        selected_date.year,
        selected_date.month,
        selected_date.day,
        tzinfo=BRIEF_TIMEZONE,
    ).astimezone(timezone.utc)
    end = start + timedelta(days=1)
    ingested_on_date = and_(Noticia.fecha_ingesta >= start, Noticia.fecha_ingesta < end)
    published_on_date = and_(Noticia.fecha_publicacion >= start, Noticia.fecha_publicacion < end)
    return or_(
        and_(Noticia.fuente == "GitHub Trending", ingested_on_date),
        and_(
            Noticia.fuente != "GitHub Trending",
            or_(published_on_date, and_(Noticia.fecha_publicacion.is_(None), ingested_on_date)),
        ),
    )


def get_feed(
    fecha: str | None = None,
    fuentes: list[str] | None = None,
    prioritized_fuentes: list[str] | None = None,
    areas: list[str] | None = None,
    orden: str = "Puntaje",
    q: str | None = None,
    limit: int = 80,
    lang: str | None = None,
) -> dict[str, Any]:
    selected_lang = normalize_language(lang)
    config = load_config()
    all_dates = is_all_dates_filter(fecha)
    selected_date = None if all_dates else parse_filter_date(fecha)
    source_filter = [source for source in (fuentes or []) if source]
    prioritized_sources = {source for source in (prioritized_fuentes or []) if source}
    area_filter = [area for area in (areas or []) if area]
    query_text = (q or "").strip()
    cutoff = datetime.now(timezone.utc) - timedelta(days=FILTER_WINDOW_DAYS)
    article_columns = (
        Noticia.id, Noticia.titulo, Noticia.url, Noticia.discussion_url, Noticia.fuente,
        Noticia.fecha_publicacion, Noticia.fecha_ingesta, Noticia.descripcion_original,
        Noticia.resumen_ia, Noticia.resumen_ia_en, Noticia.area_matcheada,
        Noticia.ranking, Noticia.num_comentarios, Noticia.score, Noticia.selected_score,
        Noticia.tags_json, Noticia.selection_reason, Noticia.score_version,
        Noticia.is_favorite, Noticia.favorited_at, Noticia.media_url, Noticia.media_type,
        Noticia.media_source_url,
    )

    with get_session() as session:
        query = session.query(Noticia).filter(Noticia.fecha_ingesta >= cutoff)
        query = query.filter(or_(Noticia.selected_score >= MIN_FEED_SCORE, Noticia.selected_score.is_(None)))
        if selected_date is not None:
            query = query.filter(_date_condition(selected_date))
        if query_text:
            query = query.filter(_search_condition(session, query_text))
        if source_filter:
            query = query.filter(Noticia.fuente.in_(source_filter))
        if area_filter:
            query = query.filter(Noticia.area_matcheada.in_(area_filter_keys(area_filter)))
        if orden == "Mas reciente" or selected_date is not None:
            query = query.order_by(Noticia.fecha_ingesta.desc())
        else:
            query = query.order_by(Noticia.selected_score.desc().nullslast(), Noticia.fecha_ingesta.desc())
        if query_text:
            row_limit = min(300, max(limit * 2, 80))
            ids = [row_id for (row_id,) in query.with_entities(Noticia.id).limit(row_limit).all()]
            if ids:
                row_order = {row_id: index for index, row_id in enumerate(ids)}
                rows = (
                    session.query(Noticia)
                    .options(load_only(*article_columns))
                    .filter(Noticia.id.in_(ids))
                    .all()
                )
                rows.sort(key=lambda row: row_order.get(row.id, len(row_order)))
            else:
                rows = []
        elif selected_date is not None:
            row_limit = 300
            rows = query.options(load_only(*article_columns)).limit(row_limit).all()
        else:
            row_limit = max(FEED_QUERY_LIMIT, limit)
            rows = query.options(load_only(*article_columns)).limit(row_limit).all()
        items = [_serialize_article(row, config, selected_lang) for row in rows]
    items = [item for item in items if float(item.get("selected_score") or 0) >= MIN_FEED_SCORE]
    for item in items:
        item["source_preference"] = "prioritized" if item.get("fuente") in prioritized_sources else "normal"
    if selected_date is not None:
        items = [item for item in items if _matches_date(item, selected_date)]
    items = _dedupe_feed_items(_sort_items(items, orden))[:limit]
    return {
        "items": items,
        "count": len(items),
        "fecha": "all" if all_dates else selected_date.isoformat(),
        "orden": orden,
        "hot_topics": [] if (all_dates or query_text) else get_hot_topics(selected_date, lang=selected_lang),
    }


def get_brief(fecha: str | None = None, lang: str | None = None) -> dict[str, Any]:
    selected_lang = normalize_language(lang)
    selected_date = parse_filter_date(fecha)
    with get_session() as session:
        brief = session.query(MacroResumen).filter(MacroResumen.fecha == selected_date).first()
        if not brief:
            current_date = datetime.now(BRIEF_TIMEZONE).date()
            catchup_started = False
            if selected_date == current_date:
                catchup_started = ensure_daily_brief_catchup(background=True)
            return {
                "available": False,
                "fecha": selected_date.isoformat(),
                "catchup_started": catchup_started,
                "catchup_running": _daily_brief_lock.locked(),
                "catchup_error": _daily_brief_state.get("last_error"),
            }
        if selected_lang == "en" and not (brief.texto_en or brief.brief_json_en):
            current_date = datetime.now(BRIEF_TIMEZONE).date()
            if selected_date == current_date:
                catchup_started = ensure_english_daily_brief(background=True)
                return {
                    "available": False,
                    "fecha": selected_date.isoformat(),
                    "catchup_started": catchup_started,
                    "catchup_running": _daily_brief_lock.locked(),
                    "catchup_error": _daily_brief_state.get("last_error"),
                }
            if not (brief and (brief.texto_en or brief.brief_json_en)):
                return {
                    "available": False,
                    "fecha": selected_date.isoformat(),
                    "catchup_started": False,
                    "catchup_running": False,
                    "catchup_error": None,
                }
        return {"available": True, **_serialize_brief(brief, selected_lang)}


def daily_brief_exists(brief_date: date | None = None) -> bool:
    selected_date = brief_date or datetime.now(BRIEF_TIMEZONE).date()
    with get_session() as session:
        return session.query(MacroResumen.id).filter(MacroResumen.fecha == selected_date).first() is not None


def should_catch_up_daily_brief(now: datetime | None = None) -> bool:
    current = now or datetime.now(BRIEF_TIMEZONE)
    if current.tzinfo is None:
        current = current.replace(tzinfo=BRIEF_TIMEZONE)
    else:
        current = current.astimezone(BRIEF_TIMEZONE)
    if current.hour < DAILY_BRIEF_HOUR:
        return False
    return not daily_brief_exists(current.date())


def _run_daily_brief_catchup() -> None:
    _daily_brief_state["last_started_at"] = datetime.now(timezone.utc)
    _daily_brief_state["last_error"] = None
    try:
        generate_daily_brief_catchup_job()
    except Exception as exc:
        _daily_brief_state["last_error"] = str(exc)
    finally:
        _daily_brief_state["last_finished_at"] = datetime.now(timezone.utc)
        _daily_brief_lock.release()


def _run_english_daily_brief(brief_date: date | None = None) -> None:
    _daily_brief_state["last_started_at"] = datetime.now(timezone.utc)
    _daily_brief_state["last_error"] = None
    try:
        generate_english_daily_brief_job(brief_date)
    except Exception as exc:
        _daily_brief_state["last_error"] = str(exc)
    finally:
        _daily_brief_state["last_finished_at"] = datetime.now(timezone.utc)
        _daily_brief_lock.release()


def ensure_daily_brief_catchup(background: bool = True) -> bool:
    if not should_catch_up_daily_brief():
        return False
    if not _daily_brief_lock.acquire(blocking=False):
        return False
    if background:
        threading.Thread(target=_run_daily_brief_catchup, daemon=True).start()
    else:
        _run_daily_brief_catchup()
    return True


def ensure_english_daily_brief(background: bool = True, brief_date: date | None = None) -> bool:
    if not _daily_brief_lock.acquire(blocking=False):
        return False
    if background:
        threading.Thread(target=_run_english_daily_brief, args=(brief_date,), daemon=True).start()
    else:
        _run_english_daily_brief(brief_date)
    return True


def _serialize_brief(brief: MacroResumen, lang: str | None = None) -> dict[str, Any]:
    selected_lang = normalize_language(lang)
    raw_json = brief.brief_json_en if selected_lang == "en" else brief.brief_json
    parsed = None
    if raw_json:
        try:
            parsed = json.loads(raw_json)
        except json.JSONDecodeError:
            parsed = None
    return {
        "fecha": brief.fecha.isoformat() if brief.fecha else "",
        "texto": brief.texto_en if selected_lang == "en" else brief.texto,
        "n_noticias": brief.n_noticias,
        "n_clusters": brief.n_clusters,
        "modelo": (brief.modelo_en if selected_lang == "en" else brief.modelo) or "N/A",
        "brief_json": parsed,
        "fecha_generacion": _iso(brief.fecha_generacion_en if selected_lang == "en" else brief.fecha_generacion),
    }


def get_past_daily_briefs(today: date | None = None, lang: str | None = None) -> dict[str, list[dict[str, Any]]]:
    selected_lang = normalize_language(lang)
    current = today or datetime.now(BRIEF_TIMEZONE).date()
    newest = current - timedelta(days=1)
    oldest = current - timedelta(days=30)
    with get_session() as session:
        rows = (
            session.query(MacroResumen)
            .filter(MacroResumen.fecha >= oldest, MacroResumen.fecha <= newest)
            .order_by(MacroResumen.fecha.desc())
            .all()
        )
        if selected_lang == "en":
            for row in rows[:ENGLISH_ARCHIVE_BACKFILL_LIMIT]:
                if not (row.texto_en or row.brief_json_en):
                    ensure_english_daily_brief(background=True, brief_date=row.fecha)
                    break
        items = [_serialize_brief(row, selected_lang) for row in rows]
    if selected_lang == "en":
        items = [item for item in items if item.get("texto") or item.get("brief_json")]
    return {"items": items}


def get_favorites(lang: str | None = None) -> dict[str, Any]:
    selected_lang = normalize_language(lang)
    config = load_config()
    with get_session() as session:
        rows = (
            session.query(Noticia)
            .filter(Noticia.is_favorite == 1)
            .order_by(Noticia.favorited_at.desc(), Noticia.fecha_ingesta.desc())
            .all()
        )
        items = [_serialize_article(row, config, selected_lang) for row in rows]
    return {"items": items, "count": len(items)}


def mark_favorite(article_id: str, lang: str | None = None) -> dict[str, Any]:
    selected_lang = normalize_language(lang)
    with get_session() as session:
        article = session.query(Noticia).filter(Noticia.id == article_id).first()
        if not article:
            return {"ok": False, "reason": t("article_not_found", selected_lang)}
        if not article.is_favorite:
            article.is_favorite = 1
            article.favorited_at = datetime.now(timezone.utc)
        return {
            "ok": True,
            "id": str(article.id),
            "is_favorite": bool(article.is_favorite),
            "favorited_at": _iso(article.favorited_at),
        }


def remove_favorite(article_id: str, lang: str | None = None) -> dict[str, Any]:
    selected_lang = normalize_language(lang)
    with get_session() as session:
        article = session.query(Noticia).filter(Noticia.id == article_id).first()
        if not article:
            return {"ok": False, "reason": t("article_not_found", selected_lang)}
        article.is_favorite = 0
        article.favorited_at = None
        return {"ok": True, "id": str(article.id), "is_favorite": False, "favorited_at": None}


def get_stats(lang: str | None = None) -> dict[str, Any]:
    selected_lang = normalize_language(lang)
    cutoff_24h = datetime.now(timezone.utc) - timedelta(hours=24)
    with get_session() as session:
        total = session.query(Noticia).count()
        recent = session.query(Noticia).filter(Noticia.fecha_ingesta >= cutoff_24h).count()
        summarized = (
            session.query(Noticia)
            .filter(
                Noticia.resumen_ia.isnot(None),
                Noticia.resumen_ia != "",
                Noticia.resumen_ia != "Resumen no disponible",
            )
            .count()
        )
        latest = (
            session.query(Noticia.fecha_ingesta)
            .order_by(Noticia.fecha_ingesta.desc())
            .limit(1)
            .scalar()
        )
        source_rows = session.query(Noticia.fuente).all()
    source_counts: dict[str, int] = {}
    for (source,) in source_rows:
        label = str(source or t("source", selected_lang))
        source_counts[label] = source_counts.get(label, 0) + 1
    return {
        "total_corpus": total,
        "noticias_24h": recent,
        "con_resumen_ia": summarized,
        "ai_coverage_pct": round((summarized / total * 100), 1) if total else 0,
        "latest_analysis": _iso(latest),
        "source_counts": source_counts,
        "global_news_count": sum(source_counts.get(source, 0) for source in ["Reuters", "GitHub Blog", "OpenAI Blog", "Hugging Face Blog"]),
    }


def get_suggestions(
    q: str,
    fecha: str | None = None,
    fuentes: list[str] | None = None,
    areas: list[str] | None = None,
    lang: str | None = None,
) -> list[dict[str, Any]]:
    query_text = q.strip()
    if len(query_text) < 2:
        return []
    all_dates = is_all_dates_filter(fecha)
    selected_date = None if all_dates else parse_filter_date(fecha)
    source_filter = [source for source in (fuentes or []) if source]
    area_filter = [area for area in (areas or []) if area]
    cutoff = datetime.now(timezone.utc) - timedelta(days=FILTER_WINDOW_DAYS)
    with get_session() as session:
        query = session.query(Noticia).filter(
            Noticia.fecha_ingesta >= cutoff,
            or_(Noticia.selected_score >= MIN_FEED_SCORE, Noticia.selected_score.is_(None)),
            _search_condition(session, query_text),
        )
        if selected_date is not None:
            query = query.filter(_date_condition(selected_date))
        if source_filter:
            query = query.filter(Noticia.fuente.in_(source_filter))
        if area_filter:
            query = query.filter(Noticia.area_matcheada.in_(area_filter_keys(area_filter)))
        rows = [
            {
                "id": str(row.id or ""),
                "title": str(row.titulo or ""),
                "source": str(row.fuente or ""),
                "score": float(row.selected_score or 0),
                "fecha_publicacion": _iso(row.fecha_publicacion),
                "fecha_ingesta": _iso(row.fecha_ingesta),
            }
            for row in (
                query.options(load_only(
                    Noticia.id, Noticia.titulo, Noticia.fuente, Noticia.fecha_publicacion,
                    Noticia.fecha_ingesta, Noticia.selected_score,
                ))
                .order_by(Noticia.selected_score.desc().nullslast(), Noticia.fecha_ingesta.desc())
                .limit(20)
                .all()
            )
        ]

    feed = [
        row for row in rows
        if row["score"] >= MIN_FEED_SCORE
        and (selected_date is None or _matches_date({
            "fuente": row["source"],
            "fecha_publicacion": row["fecha_publicacion"],
            "fecha_ingesta": row["fecha_ingesta"],
        }, selected_date))
    ][:5]
    return [
        {
            "id": item["id"],
            "title": item["title"],
            "source": item["source"],
            "score": item["score"],
        }
        for item in feed
    ]


def _cached_article_summary(article: Noticia, lang: str) -> str:
    existing = article.resumen_ia_en if lang == "en" else article.resumen_ia
    existing = str(existing or "").strip()
    return existing if existing and existing != "Resumen no disponible" else ""


def _get_summary_lock(article_id: str, lang: str) -> threading.Lock:
    key = (article_id, lang)
    with _summary_locks_guard:
        lock = _summary_locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _summary_locks[key] = lock
        return lock


def generate_summary(article_id: str, lang: str | None = None) -> dict[str, Any]:
    selected_lang = normalize_language(lang)
    with get_session() as session:
        article = session.query(Noticia).filter(Noticia.id == article_id).first()
        if not article:
            return {"ok": False, "reason": t("article_not_found", selected_lang)}
        existing = _cached_article_summary(article, selected_lang)
        if existing:
            return {"ok": True, "summary": existing, "cached": True}

    if not os.getenv("GEMINI_API_KEY", "").strip():
        return {"ok": False, "reason": t("missing_key", selected_lang)}
    from src.processor import generar_resumen_individual

    with _get_summary_lock(article_id, selected_lang):
        with get_session() as session:
            article = session.query(Noticia).filter(Noticia.id == article_id).first()
            if not article:
                return {"ok": False, "reason": t("article_not_found", selected_lang)}
            existing = _cached_article_summary(article, selected_lang)
            if existing:
                return {"ok": True, "summary": existing, "cached": True}
            title = str(article.titulo or "")
        return generar_resumen_individual(article_id, title, language=selected_lang)


def refresh_feed() -> dict[str, Any]:
    from src.ingestor import ejecutar_ingesta
    from src.scoring import score_recent_items
    from src.dynamic_keywords import discover_dynamic_keywords

    ejecutar_ingesta()
    dynamic_keywords = discover_dynamic_keywords()
    scored = score_recent_items(load_config(), hours=24)
    media_enriched = enrich_missing_media(limit=20)
    return {"ok": True, "scored": scored, "media_enriched": media_enriched, "dynamic_keywords": dynamic_keywords}


def get_dynamic_keywords() -> dict[str, list[dict[str, Any]]]:
    from src.dynamic_keywords import get_active_dynamic_keywords

    return {"items": get_active_dynamic_keywords()}


def generate_daily_brief_job() -> dict[str, Any]:
    """Refresh sources and generate today's daily brief for scheduled execution."""
    refresh_feed()
    from src.processor import ejecutar_procesamiento

    spanish = ejecutar_procesamiento()
    english = generate_english_daily_brief_job()
    return {"spanish": spanish, "english": english}


def generate_daily_brief_catchup_job() -> dict[str, Any]:
    """Generate a missing brief from already-ingested items for user-facing catch-up."""
    from src.processor import generar_macro_resumen_dia

    spanish = generar_macro_resumen_dia(load_config())
    english = generate_english_daily_brief_job()
    return {"spanish": spanish, "english": english}


def generate_english_daily_brief_job(brief_date: date | None = None) -> dict[str, Any]:
    """Generate the English version of a daily brief without blocking a request."""
    from src.processor import generar_macro_resumen_dia

    return generar_macro_resumen_dia(load_config(), language="en", target_date=brief_date)


def enrich_missing_media(limit: int = 20, timeout: int = 4) -> int:
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=FILTER_WINDOW_DAYS)
    enriched = 0
    with get_session() as session:
        rows = (
            session.query(Noticia)
            .filter(
                Noticia.url.isnot(None),
                Noticia.url != "",
                or_(Noticia.media_url.is_(None), Noticia.media_url == ""),
                Noticia.fecha_ingesta >= cutoff,
            )
            .order_by(Noticia.fecha_ingesta.desc())
            .limit(limit)
            .all()
        )
        for article in rows:
            try:
                preview = fetch_media_preview(str(article.url or ""), timeout=timeout)
            except Exception:
                continue
            if not preview:
                continue
            article.media_url = preview.media_url
            article.media_type = preview.media_type
            article.media_source_url = preview.media_source_url
            enriched += 1
    return enriched


def _run_refresh_job() -> None:
    _refresh_state["last_started_at"] = datetime.now(timezone.utc)
    _refresh_state["last_error"] = None
    try:
        refresh_feed()
    except Exception as exc:
        _refresh_state["last_error"] = str(exc)
    finally:
        _refresh_state["last_finished_at"] = datetime.now(timezone.utc)
        _refresh_lock.release()


def ensure_feed_refresh(background: bool = True) -> bool:
    if not is_feed_stale():
        return False
    if not _refresh_lock.acquire(blocking=False):
        return False
    if background:
        threading.Thread(target=_run_refresh_job, daemon=True).start()
    else:
        _run_refresh_job()
    return True


def get_refresh_status(next_check_at: datetime | None = None) -> dict[str, Any]:
    latest = latest_ingested_at()
    return {
        "updating": _refresh_lock.locked(),
        "latest_ingested_at": _iso(latest),
        "stale": is_feed_stale(latest),
        "interval_minutes": int(FEED_REFRESH_INTERVAL.total_seconds() // 60),
        "last_started_at": _iso(_refresh_state.get("last_started_at")),
        "last_finished_at": _iso(_refresh_state.get("last_finished_at")),
        "last_error": _refresh_state.get("last_error"),
        "next_check_at": _iso(next_check_at),
    }


TOPIC_STOPWORDS = {
    "about",
    "after",
    "agent",
    "agents",
    "analysis",
    "article",
    "blog",
    "build",
    "could",
    "data",
    "developer",
    "from",
    "global",
    "github",
    "hacker",
    "launch",
    "model",
    "news",
    "open",
    "release",
    "reuters",
    "says",
    "source",
    "story",
    "that",
    "this",
    "tools",
    "with",
}

TOPIC_LABELS = {
    "openai": "OpenAI",
    "github": "GitHub",
    "anthropic": "Anthropic",
    "nvidia": "Nvidia",
    "microsoft": "Microsoft",
    "google": "Google",
    "apple": "Apple",
    "meta": "Meta",
    "security": "Security",
    "cybersecurity": "Security",
    "breach": "Security",
}


def _topic_text(item: dict[str, Any]) -> str:
    return " ".join(
        str(value or "")
        for value in (
            item.get("label") or item.get("titulo"),
            item.get("descripcion"),
            " ".join(item.get("tags") or []),
        )
    )


def _topic_model_tokens(text: str) -> set[str]:
    return {
        re.sub(r"[\s\u2010-\u2015\u2212]+", "-", match.group(0).lower()).strip("-")
        for match in HOT_TOPIC_MODEL_PATTERN.finditer(text)
    }


def _topic_tokens(item: dict[str, Any]) -> set[str]:
    text = _topic_text(item).lower()
    tokens = set(re.findall(r"[a-z][a-z0-9\-]{2,}", text))
    return {token for token in tokens if token not in TOPIC_STOPWORDS} | _topic_model_tokens(text)


def _format_model_label(token: str) -> str | None:
    if not HOT_TOPIC_MODEL_PATTERN.fullmatch(token):
        return None
    prefix, version = re.match(r"([a-z]+)(.*)", token, re.IGNORECASE).groups()
    return f"{prefix.upper()}{version}"


def _topic_label(items: list[dict[str, Any]], representative: dict[str, Any]) -> str:
    counts: Counter[str] = Counter()
    for item in items:
        counts.update(_topic_tokens(item))
    for token, _count in counts.most_common():
        if model_label := _format_model_label(token):
            return model_label
        if token in TOPIC_LABELS:
            return TOPIC_LABELS[token]
    if counts:
        token = counts.most_common(1)[0][0]
        return token.replace("-", " ").title()
    tags = representative.get("tags") or []
    return str(tags[0] if tags else representative.get("area_label") or "General")


def _shared_topic_overlap(left: dict[str, Any], right: dict[str, Any]) -> int:
    return len(_topic_tokens(left) & _topic_tokens(right))


def _shared_model_overlap(left: dict[str, Any], right: dict[str, Any]) -> int:
    return len(_topic_model_tokens(_topic_text(left)) & _topic_model_tokens(_topic_text(right)))


def _cluster_unassigned_topics(items: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    if len(items) < 2:
        return [[item] for item in items]
    if TfidfVectorizer is None or cosine_similarity is None:
        clusters: dict[str, list[dict[str, Any]]] = {}
        for item in items:
            tokens = sorted(_topic_tokens(item))
            model_tokens = sorted(_topic_model_tokens(_topic_text(item)))
            key = " ".join(model_tokens[:1] or tokens[:2]) or str(item.get("id"))
            clusters.setdefault(key, []).append(item)
        return list(clusters.values())

    texts = [_topic_text(item) for item in items]
    try:
        vectors = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), min_df=1).fit_transform(texts)
        similarities = cosine_similarity(vectors)
    except ValueError:
        return [[item] for item in items]

    clusters: list[list[int]] = []
    assignments = [-1] * len(items)
    for index, item in enumerate(items):
        best_cluster = -1
        best_similarity = HOT_TOPIC_SIMILARITY_THRESHOLD
        item_models = _topic_model_tokens(_topic_text(item))
        for cluster_index, members in enumerate(clusters):
            cluster_models = set().union(*(_topic_model_tokens(_topic_text(items[member])) for member in members))
            average_similarity = sum(float(similarities[index][member]) for member in members) / len(members)
            overlap = max(_shared_topic_overlap(item, items[member]) for member in members)
            model_overlap = max(_shared_model_overlap(item, items[member]) for member in members)
            if item_models or cluster_models:
                if item_models and cluster_models and not (item_models & cluster_models):
                    continue
                if not model_overlap and (average_similarity < HOT_TOPIC_MODEL_ANCHORED_SIMILARITY_THRESHOLD or overlap < 3):
                    continue
            if average_similarity >= best_similarity or overlap >= 3 or model_overlap >= 1:
                best_similarity = average_similarity
                best_cluster = cluster_index
        if best_cluster >= 0:
            clusters[best_cluster].append(index)
            assignments[index] = best_cluster
        else:
            clusters.append([index])
            assignments[index] = len(clusters) - 1
    return [[items[index] for index in cluster] for cluster in clusters]


def _serialize_hot_topic(items: list[dict[str, Any]], lang: str | None = None) -> dict[str, Any] | None:
    selected_lang = normalize_language(lang)
    sources = sorted({str(item.get("fuente") or t("source", selected_lang)) for item in items})
    if len(sources) < HOT_TOPIC_MIN_SOURCES:
        return None
    sorted_items = sorted(
        items,
        key=lambda item: (float(item.get("selected_score") or 0), (_effective_datetime(item) or datetime.min.replace(tzinfo=timezone.utc)).timestamp()),
        reverse=True,
    )
    representative = sorted_items[0]
    title = representative.get("label") or representative.get("titulo") or t("untitled", selected_lang)
    return {
        "topic": _topic_label(items, representative),
        "title": title,
        "representative_id": representative.get("id"),
        "items": len(items),
        "source_count": len(sources),
        "sources": sources,
        "score": round(sum(float(item.get("selected_score") or 0) for item in items), 1),
        "supporting_items": [
            {
                "id": item.get("id"),
                "title": item.get("label") or item.get("titulo") or t("untitled", selected_lang),
                "source": item.get("fuente") or t("source", selected_lang),
                "score": float(item.get("selected_score") or 0),
                "url": item.get("url") or "",
            }
            for item in sorted_items[:HOT_TOPIC_SUPPORT_LIMIT]
        ],
        "_newest": max((_effective_datetime(item) for item in items), default=None),
    }


def get_hot_topics(selected_date: date, lang: str | None = None) -> list[dict[str, Any]]:
    selected_lang = normalize_language(lang)
    config = load_config()
    cutoff = datetime.now(timezone.utc) - timedelta(days=FILTER_WINDOW_DAYS)
    with get_session() as session:
        query = session.query(Noticia).filter(
            Noticia.fecha_ingesta >= cutoff,
            _date_condition(selected_date),
            Noticia.fuente != "GitHub Trending",
        )
        rows = (
            query.options(load_only(
                Noticia.id, Noticia.titulo, Noticia.url, Noticia.discussion_url, Noticia.fuente,
                Noticia.fecha_publicacion, Noticia.fecha_ingesta, Noticia.descripcion_original,
                Noticia.resumen_ia, Noticia.resumen_ia_en, Noticia.area_matcheada,
                Noticia.cluster_id, Noticia.ranking, Noticia.num_comentarios, Noticia.score,
                Noticia.selected_score, Noticia.tags_json, Noticia.selection_reason,
                Noticia.score_version, Noticia.is_favorite, Noticia.favorited_at,
                Noticia.media_url, Noticia.media_type, Noticia.media_source_url,
            ))
            .order_by(Noticia.selected_score.desc().nullslast(), Noticia.fecha_ingesta.desc())
            .limit(HOT_TOPIC_QUERY_LIMIT)
            .all()
        )
        items = [_serialize_article(row, config, selected_lang) | {"cluster_id": row.cluster_id} for row in rows]

    day_items = [item for item in items if _matches_date(item, selected_date)]
    grouped: list[list[dict[str, Any]]] = []
    cluster_groups: dict[int, list[dict[str, Any]]] = {}
    unassigned: list[dict[str, Any]] = []
    for item in day_items:
        cluster_id = item.get("cluster_id")
        if cluster_id is None:
            unassigned.append(item)
        else:
            cluster_groups.setdefault(int(cluster_id), []).append(item)
    grouped.extend(cluster_groups.values())
    grouped.extend(_cluster_unassigned_topics(unassigned))

    topics = [topic for group in grouped if (topic := _serialize_hot_topic(group, selected_lang))]
    topics.sort(
        key=lambda topic: (
            topic["source_count"],
            float(topic["score"]),
            int(topic["items"]),
            topic["_newest"].timestamp() if topic.get("_newest") else 0,
        ),
        reverse=True,
    )
    for topic in topics:
        topic.pop("_newest", None)
    return topics[:3]
