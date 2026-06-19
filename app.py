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
from streamlit.runtime.scriptrunner import add_script_run_ctx
from streamlit_autorefresh import st_autorefresh
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import atexit

from src.database import (
    MacroResumen,
    Noticia,
    Tendencia,
    get_session,
    init_db,
    limpiar_datos_antiguos,
)
from src.ingestor import ejecutar_ingesta
from src.processor import ejecutar_procesamiento, generar_resumen_individual

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

# Ventana fija de la pestaña analítica (días)
HISTORICO_DIAS: int = 7
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


@st.cache_data(ttl=60, show_spinner=False)
def _obtener_noticias(
    fuentes: tuple[str, ...] = (),
    areas_keys: tuple[str, ...] = (),
    dias: int = 30,
) -> pd.DataFrame:
    """
    Carga noticias desde DB aplicando filtros directamente en SQLAlchemy (DB pushdown).
    Evita cargar tablas completas en RAM (requerimiento de OOM protection del PRD).
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=dias)
    registros: list[dict] = []
    with get_session() as session:
        q = (
            session.query(Noticia)
            .filter(Noticia.fecha_ingesta >= cutoff)
            .order_by(Noticia.fecha_ingesta.desc())
        )
        if fuentes:
            q = q.filter(Noticia.fuente.in_(list(fuentes)))
        if areas_keys:
            q = q.filter(Noticia.area_matcheada.in_(list(areas_keys)))
        rows = q.limit(2000).all()  # hard cap OOM: max 2000 registros por query
        for n in rows:
            registros.append({
                "id":             str(n.id or ""),
                "Título":         str(n.titulo or ""),
                "URL":            str(n.url or ""),
                "Fuente":         str(n.fuente or ""),
                "Área":           n.area_matcheada or "general",
                "Publicada":      n.fecha_publicacion.isoformat() if n.fecha_publicacion else None,
                "Resumen IA":     str(n.resumen_ia or ""),
                "Ingestada":      n.fecha_ingesta.isoformat() if n.fecha_ingesta else None,
                "entidades_json": n.entidades_json or "[]",
                "Sentimiento":    n.sentimiento or "neutral",
                "Selected Score":  n.selected_score,
                "Tags":            n.tags_json or "[]",
                "Motivo seleccion": n.selection_reason or "",
                "Score Version":   n.score_version or "",
            })
    if not registros:
        return pd.DataFrame()
    df = pd.DataFrame(registros)
    df["Publicada"] = pd.to_datetime(df["Publicada"], errors="coerce", utc=True)
    df["Ingestada"] = pd.to_datetime(df["Ingestada"], errors="coerce", utc=True)
    return df


@st.cache_data(ttl=60, show_spinner=False)
def _obtener_tendencias() -> pd.DataFrame:
    registros: list[dict] = []
    with get_session() as session:
        rows = session.query(Tendencia).order_by(Tendencia.frecuencia.desc()).all()
        for t in rows:
            registros.append({"Término": t.palabra, "Frecuencia": t.frecuencia})
    return pd.DataFrame(registros) if registros else pd.DataFrame()


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
        st.markdown("### News Trend Analyzer")
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

        # Detección de Gemini (autónoma, sin import de processor)
        if GEMINI_API_KEY:
            st.success("Gemini configurado", icon="🤖")
        else:
            st.warning("Gemini sin configurar", icon="⚠️")

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

        # --- Config avanzada ---
        app_cfg = config.get("app", {})
        with st.expander("Configuración avanzada", expanded=False):
            st.caption(f"Timeout HTTP: `{app_cfg.get('timeout_request', 15)}s`")
            st.caption(f"Noticias IA por ejecución: `{app_cfg.get('max_noticias_ia', 10)}`")
            st.caption(f"Score mín. HN: `{app_cfg.get('hn_min_score', 100)}`")

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
    registros: list[dict] = []
    with get_session() as session:
        rows = (
            session.query(Noticia)
            .filter(Noticia.fecha_ingesta >= cutoff)
            .order_by(Noticia.fecha_ingesta.desc())
            .all()
        )
        for n in rows:
            registros.append({
                "id":          str(n.id),
                "Título":      str(n.titulo or ""),
                "URL":         str(n.url or ""),
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
                "Selected Score": n.selected_score,
                "Tags":        n.tags_json or "[]",
                "Motivo seleccion": n.selection_reason or "",
                "Score Version": n.score_version or "",
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


def _select_featured_items(df: pd.DataFrame, limit: int = 8, threshold: float = 70.0) -> pd.DataFrame:
    if df.empty or "Selected Score" not in df.columns:
        return pd.DataFrame()
    candidates = df.copy()
    candidates["_selected_score"] = candidates.apply(_selected_score_value, axis=1)
    if candidates["_selected_score"].max() <= 0:
        return pd.DataFrame()
    candidates = candidates.sort_values("_selected_score", ascending=False)
    qualified = candidates[candidates["_selected_score"] >= threshold]
    if len(qualified) < min(4, len(candidates)):
        qualified = candidates.head(max(limit, min(4, len(candidates))))

    selected_rows = []
    source_counts: Counter = Counter()
    area_counts: Counter = Counter()
    for _, row in qualified.iterrows():
        source = row.get("Fuente", "")
        area = row.get("Área", "general")
        if source_counts[source] >= 3 or area_counts[area] >= 4:
            continue
        selected_rows.append(row)
        source_counts[source] += 1
        area_counts[area] += 1
        if len(selected_rows) >= limit:
            break
    return pd.DataFrame(selected_rows).drop(columns=["_selected_score"], errors="ignore")


def _render_selected_section(df_hoy: pd.DataFrame, filtros: dict) -> None:
    df = df_hoy.copy()
    if not df.empty:
        if filtros.get("fuentes"):
            df = df[df["Fuente"].isin(filtros["fuentes"])]
        if filtros.get("areas_keys"):
            df = df[df["Área"].isin(filtros["areas_keys"])]

    selected = _select_featured_items(df)
    if selected.empty:
        return

    st.subheader("Selected")
    st.caption("Señales de mayor prioridad calculadas localmente; Gemini no se usa para esta selección.")

    for _, row in selected.iterrows():
        score = _selected_score_value(row)
        tags = _parse_tags(row.get("Tags"))
        reason = str(row.get("Motivo seleccion") or "").strip()
        description = str(row.get("Resumen IA") or "").strip()
        if not description or description == "Resumen no disponible":
            description = str(row.get("Descripción") or "").strip()
        if not description:
            description = "Sin descripcion disponible."

        with st.container(border=True):
            meta_col, score_col = st.columns([5, 1])
            with meta_col:
                st.caption(f"{row.get('Fuente', '')} · {_area_label(row.get('Área', 'general'))}")
                st.markdown(f"##### {row.get('Label') or row.get('Título', '')}")
            with score_col:
                st.metric("Score", f"{score:.0f}")
            if tags:
                st.caption(" · ".join(tags))
            st.caption(description[:260] + ("..." if len(description) > 260 else ""))
            if reason:
                st.info(reason)
            url = str(row.get("URL") or "")
            if url.startswith("http"):
                st.link_button("Leer original", url)
    st.divider()


def _render_feed_card(row: dict) -> None:
    """Renderiza una tarjeta individual estilo 'social media post' (componentes nativos)."""
    titulo_limpio = row.get("Label") or row.get("Título", "")
    fuente = row.get("Fuente", "")
    area_key = row.get("Área", "general")
    badge = _area_badge(area_key, _area_label(area_key))
    metrica = row.get("Métrica", 0)
    url = row.get("URL", "")

    icon = "⭐" if fuente == "GitHub Trending" else "🔺"
    label_metrica = "stars today" if fuente == "GitHub Trending" else "score HN"

    # Tiempo relativo
    try:
        delta = pd.Timestamp.now(tz="UTC") - row["Ingestada"]
        horas = int(delta.total_seconds() // 3600)
        minutos = int((delta.total_seconds() % 3600) // 60)
        tiempo_str = f"Hace {horas}h" if horas > 0 else f"Hace {minutos}m"
    except Exception:
        tiempo_str = ""

    with st.container(border=True):
        # Header de la tarjeta
        col_meta, col_time = st.columns([4, 1])
        with col_meta:
            st.markdown(badge)
            st.caption(fuente)
            selected_score = _selected_score_value(row)
            tags = _parse_tags(row.get("Tags"))
            if selected_score:
                st.caption(f"Score {selected_score:.0f}" + (f" · {' · '.join(tags[:3])}" if tags else ""))
        with col_time:
            st.caption(tiempo_str)

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
        else:
            if not es_github and tiene_descripcion:
                desc_str = str(descripcion_val)
                st.caption(desc_str[:220] + "..." if len(desc_str) > 220 else desc_str)
            else:
                if not (es_github and tiene_descripcion):
                    st.caption("Sin descripción disponible.")
                
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
        comments_col = next((c for c in row.keys() if "coment" in str(c).lower()), None)
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
                comments_val = row.get(comments_col) if comments_col else 0
                comments = 0 if pd.isna(comments_val) else int(comments_val)
                st.caption(f"💬 {comments:,} comentarios")
            elif ranking and not pd.isna(ranking):
                st.caption(f"Ranking #{int(ranking)}")
            else:
                st.caption("Trending")

        with col_f3:
            if url and str(url).startswith("http"):
                st.link_button("Leer original", url, use_container_width=True)


def _render_feed_agrupado(df_hoy: pd.DataFrame, filtros: dict) -> None:
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
        st.info(
            "Sin artículos para los filtros activos. Ejecutá 'Analizar Período'.",
            icon="ℹ️",
        )
        return

    def _ordenar_por_ranking(df: pd.DataFrame) -> pd.DataFrame:
        col_score = next((c for c in df.columns if c.lower() == "score"), None)
        col_ranking = next((c for c in df.columns if c.lower() == "ranking"), None)
        col_fuente = next((c for c in df.columns if c.lower() == "fuente"), None)
        
        if not col_fuente:
            return df
        
        github_mask = df[col_fuente] == "GitHub Trending"
        hn_mask = df[col_fuente] == "Hacker News"
        
        github = df[github_mask]
        if col_ranking and col_ranking in df.columns:
            github = github.sort_values(col_ranking, ascending=True, na_position="last")
        
        hn = df[hn_mask]
        if col_score and col_score in df.columns:
            hn = hn.sort_values(col_score, ascending=False, na_position="last")
        elif "Métrica" in df.columns:
            hn = hn.sort_values("Métrica", ascending=False, na_position="last")
        
        otras = df[~(github_mask | hn_mask)]
        return pd.concat([github, hn, otras], ignore_index=True)

    df_sorted = _ordenar_por_ranking(df_hoy)

    # Header
    gh_count = int((df_hoy["Fuente"] == "GitHub Trending").sum())
    hn_count = int((df_hoy["Fuente"] == "Hacker News").sum())
    global_count = int(df_hoy["Fuente"].isin(["Reuters", "GitHub Blog", "OpenAI Blog"]).sum())
    st.subheader(f"Feed de señales · {len(df_sorted)} publicaciones")
    st.caption(
        f"**{gh_count}** repositorios GitHub · **{hn_count}** debates HN. "
        "GitHub se ordena por ranking trending; HN por puntos."
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
# Componentes de la pestaña Histórica
# ===========================================================================

def _render_entity_trends(df: pd.DataFrame, top_n: int = 8) -> None:
    """Barras horizontales de entidades/términos más frecuentes."""
    if df.empty:
        st.info("Sin datos para el período seleccionado.", icon="ℹ️")
        return

    STOPWORDS_BASICAS = {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "is", "it", "this", "that", "are", "was",
        "be", "as", "its", "not", "has", "have", "had", "de", "la", "el", "en",
        "y", "los", "las", "un", "una", "con", "por", "para", "se", "al",
        "github", "hacker", "news", "hn", "stars", "today", "week", "new",
    }

    counter: Counter = Counter()
    for titulo in df.get("Título", pd.Series(dtype=str)):
        titulo_limpio = _re.sub(r"\[.*?\]|⭐.*|🔺.*|\(\+.*\)", "", str(titulo))
        words = _re.findall(r"[a-zA-Z]{4,}", titulo_limpio.lower())
        for w in words:
            if w not in STOPWORDS_BASICAS:
                counter[w] += 1

    if not counter:
        st.info("Insuficientes datos para calcular tendencias.", icon="ℹ️")
        return

    top_terms = counter.most_common(top_n)
    df_terms = pd.DataFrame(top_terms, columns=["Término", "Frecuencia"])
    df_terms = df_terms.sort_values("Frecuencia", ascending=True)

    fig = px.bar(
        df_terms,
        x="Frecuencia",
        y="Término",
        orientation="h",
        color="Frecuencia",
        color_continuous_scale=["#172033", "#2F6FED", "#7BA7FF"],
        labels={"Frecuencia": "Menciones", "Término": ""},
    )
    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        height=320,
        margin=dict(l=0, r=0, t=10, b=0),
        coloraxis_showscale=False,
        yaxis=dict(tickfont=dict(size=13)),
        font=dict(color="#E5E7EB"),
        xaxis=dict(gridcolor="rgba(148,163,184,0.16)", zeroline=False),
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_tendencias_chart(df_tend: pd.DataFrame) -> None:
    """Gráfico de barras con los términos NLP más frecuentes del período."""
    if df_tend.empty:
        st.info(
            "Sin tendencias NLP calculadas. Ejecutá el pipeline para generarlas.",
            icon="ℹ️",
        )
        return

    df_plot = df_tend.head(10).sort_values("Frecuencia", ascending=True)
    fig = px.bar(
        df_plot,
        x="Frecuencia",
        y="Término",
        orientation="h",
        color="Frecuencia",
        color_continuous_scale=["#0F1B2E", "#0891B2", "#67E8F9"],
        labels={"Frecuencia": "Frecuencia NLP", "Término": ""},
    )
    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        height=320,
        margin=dict(l=0, r=0, t=10, b=0),
        coloraxis_showscale=False,
        font=dict(color="#E5E7EB"),
        xaxis=dict(gridcolor="rgba(148,163,184,0.16)", zeroline=False),
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_explorador(df: pd.DataFrame) -> None:
    """Tabla interactiva con búsqueda para explorar el corpus histórico."""
    if df.empty:
        st.info("Sin artículos en el corpus para el período seleccionado.", icon="ℹ️")
        return

    busqueda = st.text_input(
        "🔍 Buscar en títulos y descripciones",
        placeholder="ej: AI, kubernetes, startup...",
        key="explorador_busqueda",
    )

    df_show = df.copy()
    if busqueda:
        mask = (
            df_show.get("Título", pd.Series(dtype=str))
            .str.contains(busqueda, case=False, na=False)
        )
        df_show = df_show[mask]

    cols_display = [c for c in ["Título", "Fuente", "Área", "Ingestada"] if c in df_show.columns]
    if not df_show.empty:
        st.caption(f"{len(df_show)} artículo(s) encontrado(s)")
        st.dataframe(
            df_show[cols_display].reset_index(drop=True),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("Sin resultados para la búsqueda.", icon="🔍")


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
# Pestañas
# ===========================================================================

def _render_tab_hoy(filtros: dict) -> None:
    """
    Pestaña Operativa — Command Center layout:
    KPIs → MacroResumen colapsable → [Feed agrupado | Panel señales]
    """
    st.markdown("### Monitoreo de hoy")
    st.caption("Señales recientes para detectar qué está ganando tracción en la comunidad técnica.")

    # KPIs
    _render_overview_kpis()
    st.divider()

    # MacroResumen colapsable
    with st.expander("Brief del día", expanded=True):
        _render_macro_resumen_card()

    st.divider()

    # Layout 2 columnas: Feed (75%) + Señales (25%)
    df_hoy = _obtener_noticias_hoy()
    _render_selected_section(df_hoy, filtros)
    col_feed, col_signals = st.columns([3, 1], gap="large")

    with col_feed:
        _render_feed_agrupado(df_hoy.copy(), filtros)

    with col_signals:
        # Aplicar filtros al df para las señales
        df_signals = df_hoy.copy()
        if not df_signals.empty:
            if filtros.get("fuentes"):
                df_signals = df_signals[df_signals["Fuente"].isin(filtros["fuentes"])]
            if filtros.get("areas_keys"):
                df_signals = df_signals[df_signals["Área"].isin(filtros["areas_keys"])]
        _render_panel_signals(df_signals)


def _render_tab_historico(
    df_noticias: pd.DataFrame, df_tend: pd.DataFrame, config: dict
) -> None:
    """
    Pestaña Analítica: entidades 7d + sentimiento + tendencias NLP + explorador.
    """
    top_n = int(config.get("app", {}).get("top_entidades", 8))

    # Corte fijo: últimos 7 días para el análisis de tendencias
    df_7d = df_noticias
    if not df_noticias.empty and "Ingestada" in df_noticias.columns:
        cutoff_7d = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=HISTORICO_DIAS)
        df_7d = df_noticias[df_noticias["Ingestada"] >= cutoff_7d].copy()

    # — Entidades + Sentimiento —
    col_main, col_stats = st.columns([2, 1], gap="large")

    with col_main:
        st.subheader(f"Entidades en tendencia · últimos {HISTORICO_DIAS} días")
        st.caption("Términos que aparecen con más fuerza en titulares recientes.")
        _render_entity_trends(df_7d, top_n=top_n)

    with col_stats:
        st.subheader("Sentimiento (7d)")
        if not df_7d.empty and "Sentimiento" in df_7d.columns:
            df_sent = df_7d["Sentimiento"].value_counts().reset_index()
            df_sent.columns = ["Sentimiento", "N"]
            df_sent["Sentimiento"] = df_sent["Sentimiento"].astype(str).str.lower()

            color_map = {
                "positivo": "#34D399",
                "negativo": "#F87171",
                "neutral":  "#94A3B8",
            }

            fig = px.pie(
                df_sent,
                values="N",
                names="Sentimiento",
                hole=0.4,
                color="Sentimiento",
                color_discrete_map=color_map,
            )
            fig.update_traces(
                textposition="inside",
                textinfo="percent+label",
                marker=dict(line=dict(color="#000000", width=1)),
            )
            fig.update_layout(
                margin=dict(l=0, r=0, t=10, b=10),
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                showlegend=False,
                height=220,
                font=dict(color="#E5E7EB"),
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Sin datos de sentimiento.", icon="ℹ️")

    st.divider()

    # — Tendencias NLP —
    col_chart, _ = st.columns([2, 1])
    with col_chart:
        st.subheader("Top términos · NLP")
        st.caption("Frecuencia calculada por el pipeline de procesamiento.")
        _render_tendencias_chart(df_tend)

    st.divider()

    # — Explorador histórico —
    st.subheader("Explorador histórico")
    _render_explorador(df_noticias)


# ===========================================================================
# Aplicación de filtros de usuario
# ===========================================================================

def _aplicar_filtros(df_noticias: pd.DataFrame, filtros: dict) -> pd.DataFrame:
    """Aplica filtros de fuente y área al DataFrame de noticias."""
    df = df_noticias.copy()

    if filtros.get("fuentes") and not df.empty:
        df = df[df["Fuente"].isin(filtros["fuentes"])]

    if filtros.get("areas_keys") and not df.empty:
        df = df[df["Área"].isin(filtros["areas_keys"])]

    return df


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
    st.title("Developer Pulse")
    st.caption("Radar local de repositorios, debates técnicos y narrativas emergentes.")

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
            _obtener_noticias.clear()
            _obtener_tendencias.clear()
            _obtener_macro_resumen_hoy.clear()
            _obtener_stats_globales.clear()
            st.session_state.etl_done_notified = True

        st.success("Pipeline ETL completado.", icon="✅")
        st.subheader("Resultado de la ejecución")
        _render_pipeline_result(st.session_state.etl_metrics)
        if st.button("Cerrar resultados", key="close_metrics"):
            st.session_state.etl_metrics = None
            st.session_state.etl_done_notified = False
            st.rerun()
        st.divider()

    # -------------------------------------------------------------------------
    # Precarga de ambos datasets antes del render de tabs.
    # @st.cache_data garantiza que las llamadas subsiguientes (dentro de los tabs)
    # retornen inmediatamente desde memoria — cambio de tab instantáneo.
    # -------------------------------------------------------------------------
    df_noticias = _obtener_noticias()          # corpus completo desde DB
    df_tend     = _obtener_tendencias()        # top términos NLP
    _obtener_macro_resumen_hoy()               # warm-up caché
    _obtener_stats_globales()                  # warm-up caché: KPIs

    # Aplicar filtros de fuente/área del sidebar (sin filtro de período)
    df_filtrado = _aplicar_filtros(df_noticias, filtros)

    # Tabs duales — navegación instantánea (datos ya en memoria)
    tab_hoy, tab_historico = st.tabs(["📡 Monitoreo de Hoy", "📈 Tendencias 7 Días"])

    with tab_hoy:
        _render_tab_hoy(filtros)

    with tab_historico:
        _render_tab_historico(df_filtrado, df_tend, config)


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    main()
