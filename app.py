# =============================================================================
# app.py — News Trend Analyzer v2.1 — Command Center Edition
# =============================================================================
"""
Dashboard dual-tab construido exclusivamente con componentes nativos de Streamlit.

Arquitectura UI:
- Sin CSS custom ni unsafe_allow_html.
- Paleta gestionada por config.toml (Tech Blue #1A73E8 + dark base).
- Badges de área con sintaxis nativa :color-badge[label].

Pestañas:
  tab_hoy       — KPIs + MacroResumen + Feed agrupado por área + Panel de señales.
  tab_historico — Entidades 7d + tendencias NLP + explorador histórico.
"""

from __future__ import annotations

import json
import os
import re as _re
import threading
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st
import yaml
from dotenv import load_dotenv
from sqlalchemy import or_
from streamlit_autorefresh import st_autorefresh
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
import atexit

from src.database import (
    MacroResumen,
    Noticia,
    get_session,
    init_db,
    limpiar_datos_antiguos,
)
from src.ingestor import ejecutar_ingesta
from src.processor import ejecutar_procesamiento, generar_resumen_individual
from src.scoring import SCORE_VERSION, calculate_item_score, score_recent_items
from src.search_component import render_corpus_search

load_dotenv()

# ---------------------------------------------------------------------------
# Configuración de rutas
# ---------------------------------------------------------------------------
CONFIG_PATH = Path(__file__).parent / "config.yaml"
LOGO_PATH = Path(__file__).parent / "assets" / "newser-lockup.png"

# ---------------------------------------------------------------------------
# Catálogos (extensibles sin tocar lógica)
# ---------------------------------------------------------------------------

FUENTES_CATALOGO: list[str] = [
    "GitHub Trending",
    "Hacker News",
    "Reuters",
    "GitHub Blog",
    "OpenAI Blog",
]

AREAS_CATALOGO: dict[str, str] = {
    "AI & Agents":              "ai_agents",
    "Developer Tools":          "developer_tools",
    "Cybersecurity":            "cybersecurity",
    "Infrastructure & Cloud":   "infrastructure_cloud",
    "Chips & Hardware":         "chips_hardware",
}

AREA_COMPATIBILITY: dict[str, str] = {
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

AREA_DB_KEYS_BY_CORE: dict[str, list[str]] = {
    core: sorted([area for area, mapped in AREA_COMPATIBILITY.items() if mapped == core])
    for core in set(AREA_COMPATIBILITY.values())
}

AREA_LABEL_BY_KEY: dict[str, str] = {value: label for label, value in AREAS_CATALOGO.items()}

LEGACY_AREA_LABEL_KEYS: dict[str, str] = {
    "Inteligencia Artificial & MLOps": "ai_agents",
    "Data Engineering": "infrastructure_cloud",
    "Ciberseguridad": "cybersecurity",
    "Startups & Producto": "general",
    "Cloud Computing": "infrastructure_cloud",
    "Ciencias de la Computación": "developer_tools",
    "Arquitectura de Software": "developer_tools",
    "Hardware & Semiconductores": "chips_hardware",
}

FEED_REFRESH_INTERVAL = timedelta(minutes=30)
BRIEF_TIMEZONE = ZoneInfo("America/Argentina/Buenos_Aires")
FILTER_WINDOW_DAYS = 30

# Mapping área → color badge nativo de Streamlit
AREA_BADGE_COLOR: dict[str, str] = {
    "ai_agents":            "blue",
    "developer_tools":      "gray",
    "cybersecurity":        "red",
    "infrastructure_cloud": "violet",
    "chips_hardware":       "orange",
    "general":              "gray",
}

# Mapping área → emoji para headers del feed
AREA_EMOJIS: dict[str, str] = {
    "ai_agents":            "🤖",
    "developer_tools":      "🛠️",
    "cybersecurity":        "🛡️",
    "infrastructure_cloud": "☁️",
    "chips_hardware":       "💾",
    "general":              "📌",
}

CHART_COLOR_SEQUENCE: list[str] = [
    "#7BA7FF",
    "#38BDF8",
    "#34D399",
    "#FBBF24",
    "#F87171",
    "#A78BFA",
    "#F472B6",
    "#94A3B8",
]

# API Key de Gemini leída exclusivamente desde el entorno.
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "").strip()


# ===========================================================================
# Helpers de UI
# ===========================================================================

def _area_badge(area_key: str, area_label: str | None = None) -> str:
    """Retorna un badge nativo de Streamlit para el área dada."""
    core_key = _core_area_key(area_key)
    color = AREA_BADGE_COLOR.get(core_key, "gray")
    label = area_label or area_key.replace("_", " ").title()
    return f":{color}-badge[{label}]"


def _core_area_key(area_key: str | None) -> str:
    """Mapea claves antiguas y nuevas a las 5 areas principales."""
    return AREA_COMPATIBILITY.get(str(area_key or "general"), "general")


def _area_label(area_key: str | None) -> str:
    """Convierte claves internas de área en etiquetas legibles."""
    key = _core_area_key(area_key)
    return AREA_LABEL_BY_KEY.get(key, key.replace("_", " ").title())


def _area_filter_keys(area_keys: tuple[str, ...] | list[str]) -> list[str]:
    """Expande areas principales a claves nuevas y legadas persistidas."""
    expanded: list[str] = []
    for key in area_keys:
        core_key = _core_area_key(key)
        expanded.extend(AREA_DB_KEYS_BY_CORE.get(core_key, [core_key]))
    return sorted(set(expanded))


def _area_labels_from_query(values: list[str]) -> list[str]:
    labels: list[str] = []
    for value in values:
        if value in AREAS_CATALOGO:
            labels.append(value)
            continue
        label = AREA_LABEL_BY_KEY.get(LEGACY_AREA_LABEL_KEYS.get(value, _core_area_key(value)))
        if label and label not in labels:
            labels.append(label)
    return labels


def _area_keys_from_labels(labels: list[str]) -> list[str]:
    return [AREAS_CATALOGO[label] for label in labels if label in AREAS_CATALOGO]


# ===========================================================================
# Data helpers — cacheados para < 1s en la UI
# ===========================================================================

@st.cache_resource(show_spinner=False)
def _inicializar_db() -> None:
    init_db()
    limpiar_datos_antiguos(dias_retencion=30)


def _cargar_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _score_display_fields(n: Noticia, config: dict[str, Any]) -> dict[str, Any]:
    """Devuelve score/tags/reason persistidos o calculados localmente para display."""
    if n.selected_score is not None:
        return {
            "selected_score": n.selected_score,
            "tags_json": n.tags_json or "[]",
            "selection_reason": n.selection_reason or "",
            "score_version": n.score_version or "",
        }
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


@st.cache_data(ttl=60, show_spinner=False)
def _buscar_corpus(
    query: str,
    fuentes: tuple[str, ...] = (),
    areas_keys: tuple[str, ...] = (),
) -> pd.DataFrame:
    """
    Busca en el corpus local aplicando filtros directamente en SQLite.
    """
    config = _cargar_config()
    registros: list[dict] = []
    with get_session() as session:
        pattern = f"%{query.strip()}%"
        q = session.query(Noticia).filter(
            or_(
                Noticia.titulo.ilike(pattern),
                Noticia.descripcion_original.ilike(pattern),
                Noticia.resumen_ia.ilike(pattern),
            )
        )
        if fuentes:
            q = q.filter(Noticia.fuente.in_(list(fuentes)))
        if areas_keys:
            q = q.filter(Noticia.area_matcheada.in_(_area_filter_keys(list(areas_keys))))
        rows = q.order_by(
            Noticia.selected_score.desc(),
            Noticia.fecha_ingesta.desc(),
        ).limit(200).all()
        for n in rows:
            score_fields = _score_display_fields(n, config)
            registros.append({
                "id":             str(n.id or ""),
                "Título":         str(n.titulo or ""),
                "URL":            str(n.url or ""),
                "Comentarios URL": _discussion_url(n),
                "Fuente":         str(n.fuente or ""),
                "Área":           n.area_matcheada or "general",
                "Publicada":      n.fecha_publicacion.isoformat() if n.fecha_publicacion else None,
                "Resumen IA":     str(n.resumen_ia or ""),
                "Descripción":    str(n.descripcion_original or ""),
                "Ingestada":      n.fecha_ingesta.isoformat() if n.fecha_ingesta else None,
                "entidades_json": n.entidades_json or "[]",
                "Sentimiento":    n.sentimiento or "neutral",
                "Ranking":        n.ranking,
                "Comentarios":    n.num_comentarios,
                "Score":          n.score,
                "Selected Score":  score_fields["selected_score"],
                "Tags":            score_fields["tags_json"],
                "Motivo seleccion": score_fields["selection_reason"],
                "Score Version":   score_fields["score_version"],
            })
    if not registros:
        return pd.DataFrame()
    df = pd.DataFrame(registros)
    df["Publicada"] = pd.to_datetime(df["Publicada"], errors="coerce", utc=True)
    df["Ingestada"] = pd.to_datetime(df["Ingestada"], errors="coerce", utc=True)
    df["Métrica"] = df.apply(lambda r: _extraer_metrica(r["Título"], r["Fuente"]), axis=1)
    df["Label"] = df["Título"].apply(
        lambda t: _re.sub(r"^\[\w+\]\s*", "", t).split("⭐")[0].split("🔺")[0].split("(+")[0].strip()[:55]
    )
    return df.sort_values(
        ["Selected Score", "Ingestada"],
        ascending=[False, False],
        na_position="last",
        kind="stable",
    ).reset_index(drop=True)


def _relative_time(fecha: datetime | None) -> str:
    if fecha is None:
        return "Sin fecha"
    if fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=timezone.utc)
    elapsed = max(0, int((datetime.now(timezone.utc) - fecha).total_seconds()))
    if elapsed < 3600:
        return f"Hace {max(1, elapsed // 60)}m"
    if elapsed < 86400:
        return f"Hace {elapsed // 3600}h"
    return f"Hace {elapsed // 86400}d"


@st.cache_data(ttl=60, show_spinner=False)
def _sugerir_corpus(
    query: str,
    fuentes: tuple[str, ...] = (),
    areas_keys: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    query = query.strip()
    if len(query) < 2:
        return []

    config = _cargar_config()
    pattern = f"%{query}%"
    with get_session() as session:
        q = session.query(Noticia).filter(
            or_(
                Noticia.titulo.ilike(pattern),
                Noticia.descripcion_original.ilike(pattern),
                Noticia.resumen_ia.ilike(pattern),
            )
        )
        if fuentes:
            q = q.filter(Noticia.fuente.in_(list(fuentes)))
        if areas_keys:
            q = q.filter(Noticia.area_matcheada.in_(_area_filter_keys(list(areas_keys))))
        rows = q.order_by(
            Noticia.selected_score.desc(),
            Noticia.fecha_ingesta.desc(),
        ).limit(5).all()
        suggestions: list[dict[str, Any]] = []
        for noticia in rows:
            score_fields = _score_display_fields(noticia, config)
            suggestions.append({
                "id": str(noticia.id),
                "title": str(noticia.titulo or ""),
                "source": str(noticia.fuente or ""),
                "score": float(score_fields["selected_score"]),
                "freshness": _relative_time(noticia.fecha_ingesta),
            })
    return suggestions


def _render_corpus_search(filtros: dict) -> str | None:
    submitted = str(st.session_state.get("busqueda_enviada", "")).strip()
    draft = str(st.session_state.get("busqueda_borrador", submitted)).strip()
    suggestions = _sugerir_corpus(
        draft,
        tuple(filtros.get("fuentes", [])),
        tuple(filtros.get("areas_keys", [])),
    )
    result = render_corpus_search({
        "draft": draft,
        "suggestions": suggestions,
        "showSuggestions": len(draft) >= 2 and draft != submitted,
        "focusInput": bool(draft and draft != submitted),
    })
    cleared = bool(result.get("clear"))
    submitted_query = str(result.get("submit") or "").strip()
    next_draft = str(result.get("draft") or "").strip()

    if cleared:
        st.session_state["busqueda_borrador"] = ""
        st.session_state["busqueda_enviada"] = ""
        st.rerun()
    if submitted_query:
        st.session_state["busqueda_borrador"] = submitted_query
        st.session_state["busqueda_enviada"] = submitted_query
        st.rerun()
    if next_draft != draft:
        st.session_state["busqueda_borrador"] = next_draft
        st.rerun()
    return submitted or None


@st.cache_data(ttl=30, show_spinner=False)
def _obtener_macro_resumen_hoy() -> dict | None:
    """MacroResumen del día actual desde DB (sin llamada a API)."""
    hoy = datetime.now().date()  # hora local, no UTC — evita desfase en TZ negativas
    with get_session() as session:
        r = session.query(MacroResumen).filter(MacroResumen.fecha == hoy).first()
        if r:
            return {
                "texto":            r.texto,
                "n_noticias":       r.n_noticias,
                "n_clusters":       r.n_clusters,
                "modelo":           r.modelo or "N/A",
                "brief_json":       r.brief_json,
                "fecha_generacion": r.fecha_generacion,
            }
    return None


@st.cache_data(ttl=60, show_spinner=False)
def _obtener_stats_globales() -> dict:
    """
    Métricas de estado actuales de la DB para el overview del dashboard.
    Siempre visible — no depende de que el pipeline haya corrido en esta sesión.
    """
    cutoff_24h = datetime.now(timezone.utc) - timedelta(hours=24)
    registros: dict = {}
    with get_session() as session:
        registros["total_corpus"] = session.query(Noticia).count()
        registros["noticias_24h"] = (
            session.query(Noticia)
            .filter(Noticia.fecha_ingesta >= cutoff_24h)
            .count()
        )
        registros["con_resumen_ia"] = (
            session.query(Noticia)
            .filter(
                Noticia.resumen_ia.isnot(None),
                Noticia.resumen_ia != "",
                Noticia.resumen_ia != "Resumen no disponible",
            )
            .count()
        )
    return registros


# ===========================================================================
# Automatic feed refresh
# ===========================================================================

_feed_refresh_lock = threading.Lock()


def _is_feed_stale(latest_ingested_at: datetime | None, now: datetime | None = None) -> bool:
    if latest_ingested_at is None:
        return True
    if latest_ingested_at.tzinfo is None:
        latest_ingested_at = latest_ingested_at.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    return now - latest_ingested_at >= FEED_REFRESH_INTERVAL


def _latest_ingested_at() -> datetime | None:
    with get_session() as session:
        return (
            session.query(Noticia.fecha_ingesta)
            .order_by(Noticia.fecha_ingesta.desc())
            .limit(1)
            .scalar()
        )


def _has_today_feed() -> bool:
    latest_ingested_at = _latest_ingested_at()
    if latest_ingested_at is None:
        return False
    if latest_ingested_at.tzinfo is None:
        latest_ingested_at = latest_ingested_at.replace(tzinfo=timezone.utc)
    return latest_ingested_at >= datetime.now(timezone.utc) - timedelta(hours=24)


def _clear_data_caches() -> None:
    _buscar_corpus.clear()
    _sugerir_corpus.clear()
    _obtener_macro_resumen_hoy.clear()
    _obtener_stats_globales.clear()
    st.cache_data.clear()


def _refresh_feed_data() -> None:
    ejecutar_ingesta()
    score_recent_items(_cargar_config(), hours=24)
    _clear_data_caches()


def _run_entry_feed_refresh() -> None:
    try:
        _refresh_feed_data()
    except Exception as exc:
        print(f"[Feed refresh] Error: {exc}")
    finally:
        _feed_refresh_lock.release()


def _ensure_feed_refresh() -> bool:
    if not _is_feed_stale(_latest_ingested_at()):
        return False
    if not _feed_refresh_lock.acquire(blocking=False):
        return True
    try:
        thread = threading.Thread(target=_run_entry_feed_refresh, daemon=True)
        thread.start()
    except Exception:
        _feed_refresh_lock.release()
        raise
    return True


# ===========================================================================
# Sidebar — Command Center Edition
# ===========================================================================

def _filter_date_bounds(today: date | None = None) -> tuple[date, date]:
    end = today or datetime.now(BRIEF_TIMEZONE).date()
    return end - timedelta(days=FILTER_WINDOW_DAYS - 1), end


def _parse_filter_date(value: Any, today: date | None = None) -> date:
    minimum, maximum = _filter_date_bounds(today)
    try:
        parsed = date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return maximum
    return parsed if minimum <= parsed <= maximum else maximum


def _render_sidebar(config: dict) -> dict:
    """
    Sidebar de control rediseñada:
    - Filtros de negocio primero
    - Estado del sistema (Gemini detection autónoma)
    - Estado de actualización automática
    """
    with st.sidebar:
        version = config.get("app", {}).get("version", "2.0.0")

        if LOGO_PATH.exists():
            st.image(str(LOGO_PATH), width=150)
        else:
            st.markdown("### Newser")
        st.caption(f"v{version}")
        st.divider()

        st.markdown("**Filtros**")

        def on_fuentes_change():
            st.query_params["fuentes"] = st.session_state.fuentes_multi
            st.session_state["fuentes_sel"] = st.session_state.fuentes_multi

        fuentes_sel = st.multiselect(
            "Fuentes",
            options=FUENTES_CATALOGO,
            default=st.session_state.get("fuentes_sel", []),
            placeholder="Todas las fuentes",
            key="fuentes_multi",
            on_change=on_fuentes_change,
        )
        if fuentes_sel:
            st.caption(f"{len(fuentes_sel)} de {len(FUENTES_CATALOGO)} seleccionadas")

        def on_areas_change():
            st.query_params["areas"] = _area_keys_from_labels(st.session_state.areas_multi)
            st.session_state["areas_sel"] = st.session_state.areas_multi

        areas_sel = st.multiselect(
            "Áreas",
            options=list(AREAS_CATALOGO.keys()),
            default=st.session_state.get("areas_sel", []),
            placeholder="Todas las áreas",
            key="areas_multi",
            on_change=on_areas_change,
        )
        if areas_sel:
            st.caption(f"{len(areas_sel)} de {len(AREAS_CATALOGO)} seleccionadas")

        date_min, date_max = _filter_date_bounds()

        def on_fecha_change():
            selected = st.session_state.fecha_filtro
            st.query_params["fecha"] = selected.isoformat()
            st.session_state["fecha_sel"] = selected

        fecha_sel = st.date_input(
            "Fecha",
            value=st.session_state.get("fecha_sel", date_max),
            min_value=date_min,
            max_value=date_max,
            key="fecha_filtro",
            on_change=on_fecha_change,
        )

        def on_orden_change():
            selected = st.session_state.orden_filtro
            st.query_params["orden"] = selected
            st.session_state["orden_sel"] = selected

        orden_sel = st.segmented_control(
            "Ordenar por",
            options=["Puntaje", "Más reciente"],
            default=st.session_state.get("orden_sel", "Puntaje"),
            selection_mode="single",
            key="orden_filtro",
            on_change=on_orden_change,
        )

        if st.query_params.get("fecha") != fecha_sel.isoformat():
            st.query_params["fecha"] = fecha_sel.isoformat()
        if orden_sel and st.query_params.get("orden") != orden_sel:
            st.query_params["orden"] = orden_sel
        area_query_keys = _area_keys_from_labels(areas_sel)
        if st.query_params.get_all("areas") != area_query_keys:
            st.query_params["areas"] = area_query_keys

        # --- Estado ---
        st.divider()
        st.markdown("**Estado**")

        stats = _obtener_stats_globales()
        pct_ia = (
            stats["con_resumen_ia"] / stats["total_corpus"] * 100
            if stats["total_corpus"]
            else 0
        )

        stat_1, stat_2, stat_3 = st.columns(3)
        stat_1.metric("Corpus", f"{stats['total_corpus']:,}")
        stat_2.metric(
            "24h",
            f"{stats['noticias_24h']:,}",
            delta=f"+{stats['noticias_24h']}" if stats["noticias_24h"] else None,
        )
        stat_3.metric("IA", f"{stats['con_resumen_ia']:,}")

        st.caption(f"Cobertura IA: {pct_ia:.1f}% del corpus")

        macro = _obtener_macro_resumen_hoy()
        if macro and macro.get("fecha_generacion"):
            gen = macro["fecha_generacion"]
            ts_str = gen.strftime("%d/%m %H:%M") if isinstance(gen, datetime) else "—"
            st.caption(f"Último análisis: {ts_str}")
        else:
            st.caption("Último análisis: —")

        scheduler = st.session_state.get("scheduler")
        if scheduler:
            brief_job = scheduler.get_job("daily_brief")
            if _feed_refresh_lock.locked():
                st.caption("Actualizando fuentes...")
            elif brief_job and brief_job.next_run_time:
                proxima = brief_job.next_run_time.astimezone(BRIEF_TIMEZONE).strftime("%H:%M ART")
                st.caption(f"Próximo brief: {proxima}")
            else:
                st.caption("Scheduler no activo")
        else:
            st.caption("Próximo brief: —")

    filtros: dict[str, Any] = {
        "fuentes":    fuentes_sel,
        "areas_keys": area_query_keys,
        "fecha":      fecha_sel,
        "orden":      orden_sel or "Puntaje",
    }
    return filtros


# ===========================================================================
# Componentes de la pestaña Operativa
# ===========================================================================

def _normalizar_citas_brief(item: dict[str, Any], allowed_urls: set[str]) -> dict[str, Any]:
    """Filtra citas para que la UI solo renderice URLs verificadas por el backend."""
    normalized = dict(item)
    sources = []
    for source in item.get("sources", []):
        if not isinstance(source, dict):
            continue
        url = str(source.get("url", "")).strip()
        if url in allowed_urls:
            sources.append({
                "name": str(source.get("name") or "Fuente"),
                "url": url,
            })
    normalized["sources"] = sources
    return normalized


def _render_brief_json(brief: dict[str, Any]) -> None:
    allowed_urls = {
        str(record.get("url", "")).strip()
        for record in brief.get("source_records", [])
        if isinstance(record, dict)
    }

    intro = str(brief.get("intro") or "").strip()
    if intro:
        st.write(intro)

    for index, raw_item in enumerate(brief.get("items", []), start=1):
        if not isinstance(raw_item, dict):
            continue
        item = _normalizar_citas_brief(raw_item, allowed_urls)
        title = str(item.get("title") or "").strip()
        summary = str(item.get("summary") or "").strip()
        why = str(item.get("why_it_matters") or "").strip()
        category = str(item.get("category") or "IT").strip()

        if title:
            st.markdown(f"##### {index}. {title}")
        if category:
            st.caption(category)
        if summary:
            st.write(summary)
        if why:
            st.markdown(f"**Por qué importa:** {why}")
        if item.get("sources"):
            links = " · ".join(f"[{src['name']}]({src['url']})" for src in item["sources"])
            st.markdown(f"Fuente: {links}")

    trend = str(brief.get("trend_reading") or "").strip()
    if trend:
        st.markdown("#### Lectura de tendencias del día")
        st.write(trend)


def _render_macro_resumen_card() -> None:
    """MacroResumen del día — card informativa."""
    macro = _obtener_macro_resumen_hoy()

    if macro:
        gen = macro["fecha_generacion"]
        hora_str = gen.strftime("%H:%M UTC") if isinstance(gen, datetime) else "—"
        with st.container(border=True):
            st.markdown("#### Brief ejecutivo")
            if macro.get("modelo") == "gemini_error":
                st.error(macro["texto"])
                st.info("El contenido fue recolectado correctamente, pero Gemini no pudo generar el brief. Reintentá cuando haya cuota disponible.")
                meta_1, meta_2, meta_3 = st.columns(3)
                meta_1.metric("Actualizado", hora_str)
                meta_2.metric("Artículos", f"{macro['n_noticias']:,}")
                meta_3.metric("Estado", "Gemini")
                return
            brief = None
            if macro.get("brief_json"):
                try:
                    brief = json.loads(macro["brief_json"])
                except json.JSONDecodeError:
                    brief = None
            if isinstance(brief, dict):
                _render_brief_json(brief)
            else:
                st.write(macro["texto"])
            meta_1, meta_2, meta_3 = st.columns(3)
            meta_1.metric("Actualizado", hora_str)
            meta_2.metric("Artículos", f"{macro['n_noticias']:,}")
            meta_3.metric("Modelo", macro["modelo"])
    else:
        st.warning(
            "El brief del día todavía no está disponible. Se generará automáticamente a las 08:00 ART.",
            icon="⏳",
        )


def _extraer_metrica(titulo: str, fuente: str) -> int:
    """Extrae la métrica numérica principal de un artículo según su fuente."""
    if fuente == "GitHub Trending":
        # Título: "[GitHub] owner/repo ⭐35,055 (+4,721 stars today)"
        m = _re.search(r"\(\+(\d[\d,]*)", titulo)
        if m:
            try:
                return int(m.group(1).replace(",", ""))
            except ValueError:
                pass
    # HN: "[HN] title 🔺1,234"
    m = _re.search(r"🔺(\d[\d,]*)", titulo)
    if m:
        try:
            return int(m.group(1).replace(",", ""))
        except ValueError:
            pass
    return 0


def _obtener_noticias_hoy() -> pd.DataFrame:
    """Carga la ventana local de siete días para los filtros del feed."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=FILTER_WINDOW_DAYS)
    config = _cargar_config()
    registros: list[dict] = []
    with get_session() as session:
        rows = (
            session.query(Noticia)
            .filter(Noticia.fecha_ingesta >= cutoff)
            .order_by(Noticia.fecha_ingesta.desc())
            .all()
        )
        for n in rows:
            score_fields = _score_display_fields(n, config)
            registros.append({
                "id":          str(n.id),
                "Título":      str(n.titulo or ""),
                "URL":         str(n.url or ""),
                "Comentarios URL": _discussion_url(n),
                "Fuente":      str(n.fuente or ""),
                "Área":        str(n.area_matcheada or "general"),
                "Ingestada":   n.fecha_ingesta,
                "Publicada":   n.fecha_publicacion,
                "Resumen IA":  str(n.resumen_ia or ""),
                "Descripción": str(n.descripcion_original or ""),
                "Sentimiento": str(n.sentimiento or "neutral") if hasattr(n, "sentimiento") else "neutral",
                "Ranking":     n.ranking,
                "Comentarios": n.num_comentarios,
                "Score":       n.score,
                "Selected Score": score_fields["selected_score"],
                "Tags":        score_fields["tags_json"],
                "Motivo seleccion": score_fields["selection_reason"],
                "Score Version": score_fields["score_version"],
            })
    if not registros:
        return pd.DataFrame()
    df = pd.DataFrame(registros)
    df["Ingestada"] = pd.to_datetime(df["Ingestada"], errors="coerce", utc=True)
    df["Publicada"] = pd.to_datetime(df["Publicada"], errors="coerce", utc=True)
    # Calcular métrica por fila
    df["Métrica"] = df.apply(lambda r: _extraer_metrica(r["Título"], r["Fuente"]), axis=1)
    # Etiqueta corta para la tarjeta (sin el prefijo [GitHub]/[HN] ni los números)
    df["Label"] = df["Título"].apply(
        lambda t: _re.sub(r"^\[\w+\]\s*", "", t).split("⭐")[0].split("🔺")[0].split("(+")[0].strip()[:55]
    )
    return df


def _feed_card_metric_text(fuente: str, metrica: int, points_val: Any = None) -> str | None:
    if fuente == "Hacker News":
        points = metrica if points_val is None or pd.isna(points_val) else int(points_val)
        return f"⬆️ {points:,} points"
    if fuente == "GitHub Trending":
        return f"⭐ {metrica:,} stars today"
    return None


def _parse_tags(value: Any) -> list[str]:
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


def _selected_score_value(row: dict | pd.Series) -> float:
    try:
        value = row.get("Selected Score", 0)
    except AttributeError:
        value = 0
    if value is None or pd.isna(value):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _comment_count(row: dict | pd.Series) -> int:
    try:
        return int(row.get("Comentarios", 0) or 0)
    except (TypeError, ValueError):
        return 0


def _format_publication_time(value: Any) -> str:
    try:
        published_at = pd.Timestamp(value)
        if pd.isna(published_at):
            return ""
        if published_at.tzinfo is None:
            published_at = published_at.tz_localize("UTC")
        else:
            published_at = published_at.tz_convert("UTC")
        return published_at.strftime("%d/%m/%Y %H:%M UTC")
    except (TypeError, ValueError):
        return ""


def _feed_time_display(row: dict | pd.Series) -> tuple[str, str] | None:
    if row.get("Fuente") == "GitHub Trending":
        label = "Detectado en tendencias"
        value = row.get("Ingestada")
    else:
        label = "Publicado"
        value = row.get("Publicada")
    timestamp = _format_publication_time(value)
    return (label, timestamp) if timestamp else None


def _effective_feed_timestamp(row: dict | pd.Series) -> pd.Timestamp:
    """Timestamp usado para filtrar y ordenar según la semántica de la fuente."""
    source = row.get("Fuente")
    value = row.get("Ingestada") if source == "GitHub Trending" else row.get("Publicada")
    if value is None or pd.isna(value):
        value = row.get("Ingestada")
    timestamp = pd.Timestamp(value)
    if pd.isna(timestamp):
        return pd.NaT
    return timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")


def _filter_and_sort_feed(df: pd.DataFrame, filtros: dict[str, Any]) -> pd.DataFrame:
    """Aplica filtros comunes al feed, señales y resultados de búsqueda."""
    if df.empty:
        return df.copy()

    filtered = df.copy()
    if filtros.get("fuentes"):
        filtered = filtered[filtered["Fuente"].isin(filtros["fuentes"])]
    filtered["_area_core"] = filtered["Área"].apply(_core_area_key)
    if filtros.get("areas_keys"):
        filtered = filtered[filtered["_area_core"].isin(filtros["areas_keys"])]

    if filtered.empty:
        return filtered.drop(columns=["_area_core"], errors="ignore")

    filtered["_effective_time"] = pd.to_datetime(
        filtered.apply(_effective_feed_timestamp, axis=1),
        errors="coerce",
        utc=True,
    )
    selected_date = filtros.get("fecha")
    if isinstance(selected_date, date):
        local_dates = filtered["_effective_time"].dt.tz_convert(BRIEF_TIMEZONE).dt.date
        filtered = filtered[local_dates == selected_date]

    if filtered.empty:
        return filtered.drop(columns=["_area_core", "_effective_time"], errors="ignore")

    if filtros.get("orden") == "Más reciente":
        sort_columns = ["_effective_time", "Selected Score"]
        ascending = [False, False]
    else:
        sort_columns = ["Selected Score", "_effective_time"]
        ascending = [False, False]
    return filtered.sort_values(
        sort_columns,
        ascending=ascending,
        na_position="last",
        kind="stable",
    ).drop(columns=["_area_core", "_effective_time"])


def _render_feed_card(row: dict) -> None:
    """Renderiza una tarjeta individual estilo 'social media post' (componentes nativos)."""
    titulo_limpio = row.get("Label") or row.get("Título", "")
    fuente = row.get("Fuente", "")
    area_key = _core_area_key(row.get("Área", "general"))
    badge = _area_badge(area_key, _area_label(area_key))
    metrica = row.get("Métrica", 0)
    url = row.get("URL", "")
    selected_score = _selected_score_value(row)
    tags = _parse_tags(row.get("Tags"))

    icon = "⭐" if fuente == "GitHub Trending" else "🔺"
    label_metrica = "stars today" if fuente == "GitHub Trending" else "score HN"

    time_display = _feed_time_display(row)

    with st.container(border=True):
        # Header de la tarjeta
        col_meta, col_score = st.columns([4, 1])
        with col_meta:
            st.markdown(badge)
            st.caption(fuente)
            if time_display:
                st.caption(f"{time_display[0]}: {time_display[1]}")
            if tags:
                st.caption(" · ".join(tags[:3]))
        with col_score:
            st.metric("Score", f"{selected_score:.0f}")

        # Título principal
        st.markdown(f"##### {titulo_limpio}")

        # Cuerpo (Resumen IA o descripción)
        resumen_col = next((c for c in row.keys() if "resumen" in str(c).lower()), None)
        desc_col = next((c for c in row.keys() if "descrip" in str(c).lower()), None)

        resumen_val = row.get(resumen_col) if resumen_col else None
        descripcion_val = row.get(desc_col) if desc_col else None
        tiene_resumen = (
            resumen_val
            and str(resumen_val).strip()
            and str(resumen_val) != "nan"
            and str(resumen_val) != "Resumen no disponible"
        )
        tiene_descripcion = (
            descripcion_val
            and str(descripcion_val).strip()
            and str(descripcion_val) != "nan"
        )
        es_github = fuente == "GitHub Trending"

        if es_github and tiene_descripcion:
            desc_str = str(descripcion_val)
            st.caption(desc_str[:220] + "..." if len(desc_str) > 220 else desc_str)

        if tiene_resumen:
            st.caption(f"🤖 {str(resumen_val)[:300]}")
        elif not es_github and tiene_descripcion:
            desc_str = str(descripcion_val)
            st.caption(desc_str[:220] + "..." if len(desc_str) > 220 else desc_str)
                
            err_key = f"err_resumen_{row['id']}"
            if not GEMINI_API_KEY:
                if err_key in st.session_state:
                    del st.session_state[err_key]
                st.warning("Para generar resúmenes, agregá `GEMINI_API_KEY` en `.env` y reiniciá la app.")
            elif st.button("Generar resumen", key=f"resumen_{row['id']}"):
                with st.spinner("Redactando resumen con Gemini..."):
                    resultado = generar_resumen_individual(row['id'], titulo_limpio)

                if resultado.get("ok"):
                    if err_key in st.session_state:
                        del st.session_state[err_key]
                    st.rerun()
                else:
                    st.session_state[err_key] = resultado.get(
                        "reason",
                        "No se pudo generar el resumen con Gemini.",
                    )

            if st.session_state.get(err_key):
                st.error(st.session_state[err_key])

        # Footer
        st.divider()
        col_f1, col_f2, col_f3 = st.columns([1.2, 1.2, 3])
        points_col = next((c for c in row.keys() if "score" in str(c).lower()), None)
        ranking = row.get("Ranking")

        with col_f1:
            if fuente == "Hacker News":
                points_val = row.get(points_col) if points_col else metrica
                points = 0 if pd.isna(points_val) else int(points_val)
                st.caption(f"⬆️ {points:,} points")
            elif fuente == "GitHub Trending":
                st.markdown(f"**{icon} {metrica:,}** {label_metrica}")

        with col_f2:
            if fuente == "Hacker News":
                comments = _comment_count(row)
                comments_url = str(row.get("Comentarios URL") or "")
                if comments_url.startswith("https://news.ycombinator.com/item?"):
                    st.markdown(f"[💬 {comments:,} comentarios]({comments_url})")
                else:
                    st.caption(f"💬 {comments:,} comentarios")
            elif ranking and not pd.isna(ranking):
                st.caption(f"Ranking #{int(ranking)}")
            else:
                st.caption("Trending")

        with col_f3:
            if url and str(url).startswith("http"):
                st.link_button("Leer original", url, use_container_width=True)


def _render_feed_agrupado(
    df_hoy: pd.DataFrame,
    filtros: dict,
    search_active: bool = False,
) -> None:
    """
    Feed de noticias agrupado por Área temática.
    Muestra máximo 10 tarjetas por área con expander 'Ver más'.
    """
    df_hoy = _filter_and_sort_feed(df_hoy, filtros)

    if df_hoy.empty:
        message = (
            "Sin resultados en el corpus para esta búsqueda."
            if search_active
            else "Sin publicaciones para los filtros activos."
        )
        st.info(message, icon="ℹ️")
        return

    df_sorted = df_hoy
    order_label = "Puntaje" if filtros.get("orden") != "Más reciente" else "Más reciente"

    # Header
    gh_count = int((df_hoy["Fuente"] == "GitHub Trending").sum())
    hn_count = int((df_hoy["Fuente"] == "Hacker News").sum())
    global_count = int(df_hoy["Fuente"].isin(["Reuters", "GitHub Blog", "OpenAI Blog"]).sum())
    if search_active:
        st.subheader(f"Resultados de búsqueda · {len(df_sorted)} publicaciones")
        st.caption(f"Resultados ordenados por {order_label.lower()}.")
    else:
        st.subheader(f"Tendencias · {len(df_sorted)} publicaciones")
        st.caption(
            f"**{gh_count}** repositorios GitHub · **{hn_count}** debates HN. "
            f"Todas las publicaciones se ordenan por {order_label.lower()}."
        )
        if global_count:
            st.caption(f"**{global_count}** noticias IT globales desde Reuters, GitHub Blog y OpenAI Blog.")

    # Renderizar la lista plana
    CARDS_TOTALES = 50
    st.divider()
    
    for idx, row in df_sorted.head(CARDS_TOTALES).iterrows():
        _render_feed_card(row.to_dict())

    restantes = len(df_sorted) - CARDS_TOTALES
    if restantes > 0:
        with st.expander(f"Ver {restantes} publicaciones más"):
            for idx, row in df_sorted.iloc[CARDS_TOTALES:].iterrows():
                _render_feed_card(row.to_dict())

def _topic_terms(title: Any) -> set[str]:
    stopwords = {
        "about", "after", "again", "against", "with", "from", "into", "over",
        "that", "this", "what", "when", "where", "will", "your", "their",
        "para", "como", "sobre", "desde", "entre", "esta", "este", "news",
        "show", "hacker", "github", "openai", "blog", "reuters",
    }
    words = _re.findall(r"[A-Za-z][A-Za-z0-9-]{3,}", str(title).lower())
    return {word for word in words if word not in stopwords}


def _build_hot_topic_clusters(df_visible: pd.DataFrame) -> list[dict[str, Any]]:
    clusters: list[dict[str, Any]] = []
    if df_visible.empty:
        return clusters

    rows = df_visible.sort_values(
        ["Selected Score", "Ingestada"],
        ascending=[False, False],
        na_position="last",
        kind="stable",
    )

    for _, row in rows.iterrows():
        title = str(row.get("Label") or row.get("Título") or "").strip()
        tags = _parse_tags(row.get("Tags"))
        topic = tags[0] if tags else _area_label(row.get("Área"))
        terms = _topic_terms(title)
        timestamp = _effective_feed_timestamp(row)
        score = max(_selected_score_value(row), 1.0)

        match = None
        for cluster in clusters:
            overlap = len(cluster["terms"] & terms)
            if cluster["topic"] == topic and overlap >= 1:
                match = cluster
                break
            if overlap >= 2:
                match = cluster
                break

        if match is None:
            match = {
                "title": title,
                "topic": topic,
                "terms": set(terms),
                "sources": set(),
                "items": 0,
                "score": 0.0,
                "newest": pd.NaT,
            }
            clusters.append(match)

        match["terms"].update(terms)
        match["sources"].add(str(row.get("Fuente") or "Fuente"))
        match["items"] += 1
        match["score"] += score
        if not pd.isna(timestamp) and (pd.isna(match["newest"]) or timestamp > match["newest"]):
            match["newest"] = timestamp

    for cluster in clusters:
        freshness_boost = 0
        newest = cluster["newest"]
        if not pd.isna(newest):
            age_hours = max(0, (datetime.now(timezone.utc) - newest.to_pydatetime()).total_seconds() / 3600)
            freshness_boost = max(0, 24 - age_hours)
        cluster["rank_score"] = cluster["score"] + cluster["items"] * 5 + len(cluster["sources"]) * 10 + freshness_boost

    return sorted(clusters, key=lambda c: c["rank_score"], reverse=True)[:3]


def _render_hot_topics_panel(df_visible: pd.DataFrame) -> None:
    clusters = _build_hot_topic_clusters(df_visible)
    with st.container(border=True):
        st.markdown("**🔥 Hot topics**")
        if not clusters:
            st.caption("Sin tendencias para los filtros actuales.")
            return

        for index, cluster in enumerate(clusters, 1):
            col_rank, col_main, col_meta = st.columns([0.3, 3.7, 1.2])
            with col_rank:
                st.markdown(f"**{index}**")
            with col_main:
                st.markdown(f"**{cluster['title']}**")
                st.caption(str(cluster["topic"]))
            with col_meta:
                source_count = len(cluster["sources"])
                source_label = "fuente" if source_count == 1 else "fuentes"
                freshness = "Sin fecha"
                if not pd.isna(cluster["newest"]):
                    freshness = _relative_time(cluster["newest"].to_pydatetime())
                st.caption(f"{source_count} {source_label} · {freshness}")


# ===========================================================================
# Vista principal
# ===========================================================================

def _render_tab_hoy(filtros: dict, df_feed: pd.DataFrame | None = None) -> None:
    """
    Pestaña Operativa — Command Center layout:
    MacroResumen colapsable → Hot topics → Feed agrupado
    """
    # MacroResumen colapsable
    with st.expander("Brief del día", expanded=True):
        _render_macro_resumen_card()

    st.divider()

    df_hoy = _obtener_noticias_hoy()
    df_visible = df_feed if df_feed is not None else df_hoy
    df_hot_topics = _filter_and_sort_feed(df_visible, filtros)
    _render_hot_topics_panel(df_hot_topics)

    st.divider()

    _render_feed_agrupado(
        df_visible.copy(),
        filtros,
        search_active=df_feed is not None,
    )


# ===========================================================================
# APScheduler - Background Jobs
# ===========================================================================

_scheduler_global: BackgroundScheduler | None = None

def _job_feed_refresh() -> None:
    """Actualiza el feed sin usar Gemini."""
    if not _feed_refresh_lock.acquire(blocking=False):
        return
    try:
        _refresh_feed_data()
    except Exception as exc:
        print(f"[Feed refresh] Error: {exc}")
    finally:
        _feed_refresh_lock.release()


def _job_daily_brief() -> None:
    """Actualiza las fuentes y genera un único brief diario a las 08:00 ART."""
    with _feed_refresh_lock:
        try:
            _refresh_feed_data()
        except Exception as exc:
            print(f"[Daily brief refresh] Error: {exc}")
            return
    try:
        ejecutar_procesamiento()
        _clear_data_caches()
    except Exception as exc:
        print(f"[Daily brief] Error: {exc}")

def _get_or_create_scheduler() -> BackgroundScheduler:
    global _scheduler_global
    if _scheduler_global is None or not _scheduler_global.running:
        _scheduler_global = BackgroundScheduler(
            job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 300},
            timezone=BRIEF_TIMEZONE,
        )
        _scheduler_global.add_job(
            func=_job_feed_refresh,
            trigger=IntervalTrigger(minutes=30),
            id="feed_refresh",
            name="Actualización automática del feed",
            replace_existing=True,
        )
        _scheduler_global.add_job(
            func=_job_daily_brief,
            trigger=CronTrigger(hour=8, minute=0, timezone=BRIEF_TIMEZONE),
            id="daily_brief",
            name="Brief diario",
            misfire_grace_time=3600,
            replace_existing=True,
        )
        _scheduler_global.start()
        atexit.register(lambda: _scheduler_global.shutdown(wait=False))
    return _scheduler_global

# ===========================================================================
# Main
# ===========================================================================

def main() -> None:
    st.set_page_config(
        page_title="Newser",
        page_icon="📡",
        layout="wide",
        initial_sidebar_state="auto",
        menu_items={
            "About": "**News Trend Analyzer v2.1** · Pipeline ETL + Enriquecimiento IA generativa.",
        },
    )

    # Bootstrap DB (cacheado — solo corre una vez por sesión)
    _inicializar_db()
    config = _cargar_config()

    # Scheduler automático (singleton real)
    scheduler = _get_or_create_scheduler()
    st.session_state["scheduler"] = scheduler

    # Session state de filtros (leyendo desde query params si existe)
    qp_fuentes = st.query_params.get_all("fuentes")
    qp_areas = st.query_params.get_all("areas")
    qp_fecha = st.query_params.get("fecha")
    qp_orden = st.query_params.get("orden")

    if "fuentes_sel" not in st.session_state:
        st.session_state["fuentes_sel"] = qp_fuentes if qp_fuentes else []

    if "areas_sel" not in st.session_state:
        st.session_state["areas_sel"] = _area_labels_from_query(qp_areas) if qp_areas else []

    if "fecha_sel" not in st.session_state:
        st.session_state["fecha_sel"] = _parse_filter_date(qp_fecha)

    if "orden_sel" not in st.session_state:
        st.session_state["orden_sel"] = (
            qp_orden if qp_orden in {"Puntaje", "Más reciente"} else "Puntaje"
        )

    # Sidebar
    filtros = _render_sidebar(config)

    # Header
    st.title("IT News Trend Analyzer")
    busqueda_enviada = _render_corpus_search(filtros)

    refresh_started = _ensure_feed_refresh()
    if refresh_started and not _has_today_feed() and not busqueda_enviada:
        st.info("Actualizando noticias de hoy...", icon="⏳")
        st_autorefresh(interval=2000, key="feed_refresh")
        return

    if busqueda_enviada:
        df_busqueda = _buscar_corpus(
            busqueda_enviada,
            tuple(filtros.get("fuentes", [])),
            tuple(filtros.get("areas_keys", [])),
        )
        _render_feed_agrupado(df_busqueda, filtros, search_active=True)
    else:
        _render_tab_hoy(filtros)


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    main()
