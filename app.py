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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.express as px
import requests
import streamlit as st
import yaml
from dotenv import load_dotenv
from sqlalchemy import or_
from streamlit.runtime.scriptrunner import add_script_run_ctx
from streamlit_autorefresh import st_autorefresh
from apscheduler.schedulers.background import BackgroundScheduler
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
from src.scoring import SCORE_VERSION, calculate_item_score
from src.search_component import render_corpus_search

load_dotenv()

# ---------------------------------------------------------------------------
# Configuración de rutas
# ---------------------------------------------------------------------------
CONFIG_PATH = Path(__file__).parent / "config.yaml"

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
    "Inteligencia Artificial & MLOps": "inteligencia_artificial",
    "Data Engineering":                "data_engineering",
    "Ciberseguridad":                  "ciberseguridad",
    "Startups & Producto":             "startups_tecnologia",
    "Cloud Computing":                 "cloud_computing",
    "Ciencias de la Computación":      "ciencias_computacion",
    "Arquitectura de Software":        "arquitectura_software",
    "Hardware & Semiconductores":      "semiconductores",
}

PIPELINE_INTERVALO_HORAS: int = 6  # cada cuántas horas se ejecuta automáticamente

# Mapping área → color badge nativo de Streamlit
AREA_BADGE_COLOR: dict[str, str] = {
    "inteligencia_artificial": "blue",
    "data_engineering":        "violet",
    "ciberseguridad":          "red",
    "startups_tecnologia":     "green",
    "cloud_computing":         "blue",
    "ciencias_computacion":    "orange",
    "arquitectura_software":   "gray",
    "semiconductores":         "orange",
    "general":                 "gray",
}

# Mapping área → emoji para headers del feed
AREA_EMOJIS: dict[str, str] = {
    "inteligencia_artificial": "🤖",
    "data_engineering":        "🔧",
    "ciberseguridad":          "🛡️",
    "startups_tecnologia":     "🚀",
    "cloud_computing":         "☁️",
    "ciencias_computacion":    "🧬",
    "arquitectura_software":   "🏗️",
    "semiconductores":         "💾",
    "general":                 "📌",
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
    color = AREA_BADGE_COLOR.get(area_key.lower(), "gray")
    label = area_label or area_key.replace("_", " ").title()
    return f":{color}-badge[{label}]"


def _area_label(area_key: str | None) -> str:
    """Convierte claves internas de área en etiquetas legibles."""
    key = area_key or "general"
    for label, value in AREAS_CATALOGO.items():
        if value == key:
            return label
    return key.replace("_", " ").title()


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
            q = q.filter(Noticia.area_matcheada.in_(list(areas_keys)))
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
            q = q.filter(Noticia.area_matcheada.in_(list(areas_keys)))
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
# Pipeline (background thread)
# ===========================================================================

def _run_etl_thread(session_state):
    """Ejecuta el pipeline en background interactuando con el session_state."""
    def update_progress(msg: str):
        session_state.etl_logs.append(msg)

    try:
        session_state.etl_logs.append("**--- INGESTA ---**")
        m_ingesta = ejecutar_ingesta(progress_callback=update_progress)

        session_state.etl_logs.append("**--- ENRIQUECIMIENTO IA ---**")
        m_proc = ejecutar_procesamiento(progress_callback=update_progress)

        session_state.etl_metrics = {**m_ingesta, **m_proc}
        session_state.etl_logs.append("✅ Pipeline Analítico finalizado")
    except Exception as exc:
        session_state.etl_logs.append(f"🚨 Error durante el pipeline: {exc}")
    finally:
        session_state.etl_is_running = False


# ===========================================================================
# Sidebar — Command Center Edition
# ===========================================================================

def _render_sidebar(config: dict) -> tuple[bool, dict]:
    """
    Sidebar de control rediseñada:
    - Filtros de negocio primero
    - Estado del sistema (Gemini detection autónoma)
    - Config avanzada colapsable
    - CTA de pipeline
    """
    with st.sidebar:
        version = config.get("app", {}).get("version", "2.0.0")

        # --- Header ---
        st.markdown("### Newser")
        st.caption(f"Developer pulse · v{version}")
        st.divider()

        # --- Filtros ---
        st.markdown("**Signal scope**")

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
            st.query_params["areas"] = st.session_state.areas_multi
            st.session_state["areas_sel"] = st.session_state.areas_multi

        st.markdown("**Áreas de interés**")
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

        # --- Estado del sistema ---
        st.divider()
        st.markdown("**System state**")

        # Último análisis
        macro = _obtener_macro_resumen_hoy()
        if macro and macro.get("fecha_generacion"):
            gen = macro["fecha_generacion"]
            ts_str = gen.strftime("%d/%m %H:%M") if isinstance(gen, datetime) else "—"
            st.caption(f"Último análisis: {ts_str}")
        else:
            st.caption("Sin análisis hoy")

        # Próxima ejecución automática
        scheduler = st.session_state.get("scheduler")
        if scheduler:
            job = scheduler.get_job("pipeline_auto")
            if job and job.next_run_time:
                proxima = job.next_run_time.strftime("%H:%M UTC")
                st.caption(f"Próximo automático: {proxima}")
            elif not tiene_descripcion:
                st.caption("Scheduler no activo")

        # --- ETL Controls ---
        st.divider()

        if "etl_is_running" not in st.session_state:
            st.session_state.etl_is_running = False
            st.session_state.etl_logs = []
            st.session_state.etl_metrics = None
            st.session_state.etl_done_notified = False

        clicked = False

        if st.session_state.etl_is_running:
            st.info("⏳ Ejecutando Pipeline Analítico...")
            with st.container(height=200):
                for log in st.session_state.etl_logs[-20:]:
                    st.caption(log)
            st_autorefresh(interval=1500, key="etl_refresh")
        else:
            clicked = st.button(
                "Analizar período",
                type="primary",
                use_container_width=True,
                help="Ejecuta ingesta, clustering, tendencias y resúmenes IA.",
            )

    filtros: dict[str, Any] = {
        "fuentes":    fuentes_sel,
        "areas_keys": [AREAS_CATALOGO[a] for a in areas_sel],
    }
    return clicked, filtros


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
            "El brief del día todavía no está disponible. Ejecutá **Analizar período** para generarlo.",
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
    """Carga noticias de las últimas 24h desde DB (sin dependencia de Cluster)."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
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


def _render_feed_card(row: dict) -> None:
    """Renderiza una tarjeta individual estilo 'social media post' (componentes nativos)."""
    titulo_limpio = row.get("Label") or row.get("Título", "")
    fuente = row.get("Fuente", "")
    area_key = row.get("Área", "general")
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
    # Aplicar filtros
    if not df_hoy.empty:
        if filtros.get("fuentes"):
            df_hoy = df_hoy[df_hoy["Fuente"].isin(filtros["fuentes"])]
        if filtros.get("areas_keys"):
            df_hoy = df_hoy[df_hoy["Área"].isin(filtros["areas_keys"])]

    if df_hoy.empty:
        message = (
            "Sin resultados en el corpus para esta búsqueda."
            if search_active
            else "Sin artículos para los filtros activos. Ejecutá 'Analizar Período'."
        )
        st.info(message, icon="ℹ️")
        return

    df_sorted = df_hoy.sort_values(
        ["Selected Score", "Ingestada"],
        ascending=[False, False],
        na_position="last",
        kind="stable",
    )

    # Header
    gh_count = int((df_hoy["Fuente"] == "GitHub Trending").sum())
    hn_count = int((df_hoy["Fuente"] == "Hacker News").sum())
    global_count = int(df_hoy["Fuente"].isin(["Reuters", "GitHub Blog", "OpenAI Blog"]).sum())
    if search_active:
        st.subheader(f"Resultados de búsqueda · {len(df_sorted)} publicaciones")
        st.caption("Resultados ordenados por Score.")
    else:
        st.subheader(f"Feed de señales · {len(df_sorted)} publicaciones")
        st.caption(
            f"**{gh_count}** repositorios GitHub · **{hn_count}** debates HN. "
            "Todas las publicaciones se ordenan por Score."
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

def _render_panel_signals(df_hoy: pd.DataFrame) -> None:
    """
    Panel lateral de señales: distribución por área, sentimiento, top entidades.
    Se muestra como columna derecha en el tab Hoy.
    """
    st.markdown("### Señales del día")

    if df_hoy.empty:
        st.info("Sin datos para generar señales.", icon="ℹ️")
        return

    tag_scores: Counter = Counter()
    for _, row in df_hoy.iterrows():
        score = max(_selected_score_value(row), 1.0)
        for tag in _parse_tags(row.get("Tags")):
            tag_scores[tag] += score
    if tag_scores:
        with st.container(border=True):
            st.markdown("**Hot topics**")
            for tag, value in tag_scores.most_common(5):
                st.markdown(f"**{tag}** · {value:.0f}")

    # --- Distribución por área ---
    with st.container(border=True):
        st.markdown("**Distribución por área**")
        areas_counts = df_hoy["Área"].value_counts()
        df_areas = areas_counts.reset_index()
        df_areas.columns = ["Área", "N"]
        df_areas["Label"] = df_areas["Área"].apply(_area_label)
        df_areas = df_areas.sort_values("N", ascending=True)

        fig_areas = px.bar(
            df_areas,
            x="N",
            y="Label",
            orientation="h",
            color="N",
            color_continuous_scale=["#172033", "#2F6FED", "#7BA7FF"],
            labels={"N": "", "Label": ""},
        )
        fig_areas.update_layout(
            height=max(160, len(df_areas) * 30),
            margin=dict(l=0, r=0, t=0, b=0),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            coloraxis_showscale=False,
            xaxis=dict(showticklabels=False, showgrid=False, zeroline=False),
            yaxis=dict(tickfont=dict(size=11)),
            showlegend=False,
            font=dict(color="#E5E7EB"),
        )
        st.plotly_chart(fig_areas, use_container_width=True)

    # --- Top entidades/términos ---
    STOPWORDS_SIGNAL = {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "is", "it", "this", "that", "are", "was",
        "be", "as", "its", "not", "has", "have", "had", "de", "la", "el", "en",
        "y", "los", "las", "un", "una", "con", "por", "para", "se", "al",
        "github", "hacker", "news", "hn", "stars", "today", "week", "new",
    }
    counter: Counter = Counter()
    for titulo in df_hoy.get("Título", pd.Series(dtype=str)):
        titulo_limpio = _re.sub(r"\[.*?\]|⭐.*|🔺.*|\(\+.*\)", "", str(titulo))
        words = _re.findall(r"[a-zA-Z]{4,}", titulo_limpio.lower())
        for w in words:
            if w not in STOPWORDS_SIGNAL:
                counter[w] += 1

    with st.container(border=True):
        st.markdown("**Top términos**")
        top_5 = counter.most_common(5)
        if top_5:
            for i, (term, freq) in enumerate(top_5, 1):
                st.markdown(f"`{i}` **{term}** · {freq}×")
        else:
            st.caption("Insuficientes datos")


# ===========================================================================
# Resultados del pipeline
# ===========================================================================

def _render_pipeline_result(metrics: dict) -> None:
    """Muestra las métricas del último pipeline ejecutado."""
    if not metrics:
        return
    col1, col2, col3 = st.columns(3)
    col1.metric("✅ Nuevas persistidas",  metrics.get("nuevas_persistidas", 0))
    col2.metric("♻️ Duplicadas omitidas", metrics.get("duplicadas_omitidas", 0))
    col3.metric("⚠️ Fuentes fallidas",    metrics.get("fuentes_fallidas", 0))
    if metrics.get("nombres_fallidas"):
        st.caption(f"Fuentes con error: {', '.join(metrics['nombres_fallidas'])}")


# ===========================================================================
# Overview KPIs (con fila de contexto)
# ===========================================================================

def _render_overview_kpis() -> None:
    """Fila de 3 KPI cards + fila de contexto."""
    stats = _obtener_stats_globales()

    st.subheader("Estado operativo")
    st.caption("Lectura rápida del corpus local y la cobertura de análisis.")

    # Fila principal: 3 métricas
    col1, col2, col3 = st.columns(3)
    col1.metric(
        label="Corpus total",
        value=f"{stats['total_corpus']:,}",
        help="Total de artículos persistidos en la base de datos local.",
    )
    col2.metric(
        label="Ingestados 24h",
        value=f"{stats['noticias_24h']:,}",
        delta=f"+{stats['noticias_24h']}" if stats["noticias_24h"] else None,
        delta_color="normal",
        help="Artículos nuevos incorporados en las últimas 24 horas.",
    )
    col3.metric(
        label="Con resumen IA",
        value=f"{stats['con_resumen_ia']:,}",
        help="Artículos con resumen ejecutivo generado por IA.",
    )

    # Fila de contexto
    pct_ia = (
        stats["con_resumen_ia"] / stats["total_corpus"] * 100
        if stats["total_corpus"]
        else 0
    )
    macro = _obtener_macro_resumen_hoy()
    ultimo_ts = "—"
    if macro and macro.get("fecha_generacion"):
        gen = macro["fecha_generacion"]
        ultimo_ts = gen.strftime("%d/%m %H:%M") if isinstance(gen, datetime) else "—"

    ctx1, ctx2, ctx3 = st.columns(3)
    ctx1.caption("Fuentes activas: GitHub Trending · Hacker News · Reuters · GitHub Blog · OpenAI Blog")
    ctx2.caption(f"Cobertura IA: {pct_ia:.1f}% del corpus")
    ctx3.caption(f"Último análisis: {ultimo_ts}")


# ===========================================================================
# Vista principal
# ===========================================================================

def _render_tab_hoy(filtros: dict, df_feed: pd.DataFrame | None = None) -> None:
    """
    Pestaña Operativa — Command Center layout:
    KPIs → MacroResumen colapsable → [Feed agrupado | Panel señales]
    """
    # KPIs
    _render_overview_kpis()
    st.divider()

    # MacroResumen colapsable
    with st.expander("Brief del día", expanded=True):
        _render_macro_resumen_card()

    st.divider()

    # Layout 2 columnas: Feed (75%) + Señales (25%)
    df_hoy = _obtener_noticias_hoy()
    df_visible = df_feed if df_feed is not None else df_hoy
    col_feed, col_signals = st.columns([3, 1], gap="large")

    with col_feed:
        _render_feed_agrupado(
            df_visible.copy(),
            filtros,
            search_active=df_feed is not None,
        )

    with col_signals:
        # Aplicar filtros al df para las señales
        df_signals = df_visible.copy()
        if not df_signals.empty:
            if filtros.get("fuentes"):
                df_signals = df_signals[df_signals["Fuente"].isin(filtros["fuentes"])]
            if filtros.get("areas_keys"):
                df_signals = df_signals[df_signals["Área"].isin(filtros["areas_keys"])]
        _render_panel_signals(df_signals)


# ===========================================================================
# APScheduler - Background Jobs
# ===========================================================================

_scheduler_global: BackgroundScheduler | None = None

def _job_pipeline_automatico() -> None:
    """Job de APScheduler: ejecuta el pipeline ETL completo en background."""
    try:
        # Evitar ejecución concurrente con pipeline manual
        try:
            if st.session_state.get("etl_is_running", False):
                return
        except Exception:
            pass  # st.session_state no disponible en este thread
        
        from src.ingestor import ejecutar_ingesta
        from src.processor import ejecutar_procesamiento
        
        ejecutar_ingesta()
        ejecutar_procesamiento()
        
        # Invalidar cachés de Streamlit para que la próxima recarga muestre datos frescos
        st.cache_data.clear()
        
    except Exception as e:
        # Log silencioso — no propagar para no matar el scheduler
        print(f"[APScheduler] Error en pipeline automático: {e}")

def _get_or_create_scheduler() -> BackgroundScheduler:
    global _scheduler_global
    if _scheduler_global is None or not _scheduler_global.running:
        _scheduler_global = BackgroundScheduler(
            job_defaults={"misfire_grace_time": 300},
            timezone="UTC"
        )
        _scheduler_global.add_job(
            func=_job_pipeline_automatico,
            trigger=IntervalTrigger(hours=PIPELINE_INTERVALO_HORAS),
            id="pipeline_auto",
            name="Pipeline ETL automático",
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
        page_title="News Trend Analyzer",
        page_icon="📡",
        layout="wide",
        initial_sidebar_state="auto",
        menu_items={
            "About": "**News Trend Analyzer v2.1** · Pipeline ETL + Enriquecimiento IA generativa.",
        },
    )

    # ── Scheduler automático (singleton real) ──────────────
    scheduler = _get_or_create_scheduler()
    st.session_state["scheduler"] = scheduler

    # Bootstrap DB (cacheado — solo corre una vez por sesión)
    _inicializar_db()
    config = _cargar_config()

    # Session state de filtros (leyendo desde query params si existe)
    qp_fuentes = st.query_params.get_all("fuentes")
    qp_areas = st.query_params.get_all("areas")

    if "fuentes_sel" not in st.session_state:
        st.session_state["fuentes_sel"] = qp_fuentes if qp_fuentes else []

    if "areas_sel" not in st.session_state:
        st.session_state["areas_sel"] = qp_areas if qp_areas else []

    # Sidebar
    disparar, filtros = _render_sidebar(config)

    # Header
    st.title("IT News Trend Analyzer")
    busqueda_enviada = _render_corpus_search(filtros)

    # Ejecución del pipeline (background)
    if disparar and not st.session_state.etl_is_running:
        st.session_state.etl_is_running = True
        st.session_state.etl_logs = ["Iniciando ejecución en background..."]
        st.session_state.etl_metrics = None
        st.session_state.etl_done_notified = False

        t = threading.Thread(target=_run_etl_thread, args=(st.session_state,))
        add_script_run_ctx(t)
        t.start()
        st.rerun()

    # Resultados post-ejecución
    if st.session_state.get("etl_metrics") and not st.session_state.get("etl_is_running"):
        if not st.session_state.get("etl_done_notified"):
            # Invalidar cachés para forzar recarga de datos frescos
            _buscar_corpus.clear()
            _sugerir_corpus.clear()
            _obtener_macro_resumen_hoy.clear()
            _obtener_stats_globales.clear()
            st.session_state.etl_done_notified = True

        if not busqueda_enviada:
            st.success("Pipeline ETL completado.", icon="✅")
            st.subheader("Resultado de la ejecución")
            _render_pipeline_result(st.session_state.etl_metrics)
            if st.button("Cerrar resultados", key="close_metrics"):
                st.session_state.etl_metrics = None
                st.session_state.etl_done_notified = False
                st.rerun()
            st.divider()

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
