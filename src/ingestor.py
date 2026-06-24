# =============================================================================
# src/ingestor.py — v4.0 Developer Pulse Edition · Dual-Window Ingestion
# =============================================================================
"""
Módulo de ingestión de datos con soporte multi-fuente y ventanas temporales duales.

Fuentes y ventanas:
  GitHub API  · 1d  → "Monitoreo de Hoy"
  GitHub API  · 7d  → "Tendencias 7 Días"
  HN Firebase · top → "Monitoreo de Hoy"   (top stories actuales)
  HN Algolia  · 7d  → "Tendencias 7 Días"  (histórico 7d via Algolia Search API)
  RSS genérico      → fuentes adicionales (ej. Reddit cuando esté activo)

Arquitectura:
  - Un ThreadPoolExecutor con los 4 workers en paralelo.
  - Deduplicación por SHA-256 (título + URL) antes del INSERT.
  - Sanitización PII en la ingesta (GDPR / Ley 25.326).
  - Métricas detalladas para el feedback de la UI.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import feedparser
import requests
import yaml

from .database import Noticia, get_session
from .global_news import GlobalNewsItem, fetch_global_news

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

CONFIG_PATH: Path = Path(__file__).parent.parent / "config.yaml"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def cargar_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"No se encontró config.yaml en: {CONFIG_PATH}")
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _calcular_hash(titulo: str, url: str) -> str:
    """Hash estándar para noticias (permanente entre días)."""
    contenido = f"{titulo.strip().lower()}|{url.strip().lower()}"
    return hashlib.sha256(contenido.encode("utf-8")).hexdigest()


def _calcular_hash_diario(titulo: str, url: str, fecha: str | None = None) -> str:
    """
    Hash con componente de fecha.
    Permite que el mismo repo aparezca en el trending de días distintos
    como entradas independientes, manteniendo la trazabilidad diaria.
    """
    if fecha is None:
        fecha = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    contenido = f"{titulo.strip().lower()}|{url.strip().lower()}|{fecha}"
    return hashlib.sha256(contenido.encode("utf-8")).hexdigest()


def _ahora_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _es_relevante(titulo: str, descripcion: str, areas_interes: dict) -> tuple[bool, str]:
    """Clasifica una noticia contra las keywords de áreas_interes (OR inclusivo)."""
    texto = f"{titulo} {descripcion}".lower()
    for area, keywords in areas_interes.items():
        for kw in keywords:
            if kw.lower() in texto:
                return True, area
    return False, ""


def _sanitize_record(data: dict) -> dict:
    """Elimina campos PII del registro antes de persistir (GDPR / Ley 25.326)."""
    PII_FIELDS = {"author", "username", "avatar_url", "email", "user", "login"}
    return {k: v for k, v in data.items() if k.lower() not in PII_FIELDS}


def _metricas_vacias(nombre: str) -> dict:
    return {
        "total_procesadas": 0,
        "fuentes_fallidas": 0,
        "nombres_fallidas": [],
        "no_relevantes": 0,
        "nombre": nombre,
    }


def _area_desde_categoria_global(category: str) -> str:
    mapping = {
        "AI": "inteligencia_artificial",
        "Cybersecurity": "ciberseguridad",
        "Developer Tools": "arquitectura_software",
        "Infrastructure": "semiconductores",
        "Regulation": "startups_tecnologia",
        "IT": "ciencias_computacion",
    }
    return mapping.get(category or "IT", "ciencias_computacion")


def _fecha_global_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        fecha = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if fecha.tzinfo is not None:
        fecha = fecha.astimezone(timezone.utc).replace(tzinfo=None)
    return fecha


def _noticias_desde_global_items(items: list[GlobalNewsItem]) -> list[Noticia]:
    noticias: list[Noticia] = []
    for item in items:
        noticias.append(Noticia(
            id=_calcular_hash(item.title, item.url),
            titulo=f"[Global] {item.title}",
            url=item.url,
            fuente=item.source,
            fecha_publicacion=_fecha_global_utc(item.published_at),
            descripcion_original=item.excerpt[:1000],
            resumen_ia="Resumen no disponible",
            area_matcheada=_area_desde_categoria_global(item.category),
            fecha_ingesta=_ahora_utc(),
            score=item.score,
        ))
    return noticias


def _worker_global_news(
    fuente_cfg: dict,
    app_cfg: dict,
    areas_interes: dict,
) -> tuple[list[Noticia], dict]:
    nombre = fuente_cfg.get("nombre", "Global IT Brief")
    max_items = app_cfg.get("global_news_count", 15)
    timeout = app_cfg.get("timeout_request", 15)
    metricas = _metricas_vacias(nombre)

    try:
        items = fetch_global_news(max_items=max_items, timeout=timeout)
        metricas["total_procesadas"] = len(items)
        return _noticias_desde_global_items(items), metricas
    except Exception as exc:
        logger.error("Error en worker Global IT News: %s", exc)
        metricas["fuentes_fallidas"] += 1
        metricas["nombres_fallidas"].append(nombre)
        return [], metricas


# ---------------------------------------------------------------------------
# Worker GitHub — soporta ventana de 1d (hoy) o 7d (semanal)
# ---------------------------------------------------------------------------

def _worker_github(
    fuente_cfg: dict,
    app_cfg: dict,
    areas_interes: dict,
    dias_ventana: int = 1,
) -> tuple[list[Noticia], dict]:
    """
    Scraper de github.com/trending (página oficial).

    dias_ventana=1  → GET github.com/trending?since=daily
    dias_ventana=7  → GET github.com/trending?since=weekly

    Métrica de ranking: estrellas ganadas en el período
    ("4,721 stars today" o "12,345 stars this week").
    Ese número es el criterio de trending que usa GitHub.

    Nota: GitHub no ofrece una API oficial de trending;
    el scraping del HTML es la única forma de obtener
    exactamente la misma lista que muestra la web.
    """
    from bs4 import BeautifulSoup

    nombre_base = fuente_cfg.get("nombre", "GitHub Trending")
    label = "hoy" if dias_ventana == 1 else f"{dias_ventana}d"
    nombre = f"{nombre_base} ({label})"
    timeout = app_cfg.get("timeout_request", 15)

    since = "daily" if dias_ventana == 1 else "weekly"
    url_trending = f"https://github.com/trending?since={since}"

    # User-Agent de navegador para evitar bloqueos
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    metricas = _metricas_vacias(nombre)
    noticias: list[Noticia] = []

    try:
        logger.info("GitHub Trending scraper: GET %s", url_trending)
        resp = requests.get(url_trending, headers=headers, timeout=timeout)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        articles = soup.select("article.Box-row")
        logger.info("GitHub Trending %s: %d repos en página.", since, len(articles))

        for idx, article in enumerate(articles):
            metricas["total_procesadas"] += 1

            # --- Nombre y URL del repo ---
            link_tag = article.select_one("h2 a")
            if not link_tag:
                continue
            full_name = link_tag.get("href", "").strip("/")  # "owner/repo"
            if not full_name or "/" not in full_name:
                continue
            url_repo = f"https://github.com/{full_name}"

            # --- Descripción ---
            p_tag = article.select_one("p")
            descripcion = p_tag.get_text(strip=True) if p_tag else ""

            # --- Total stars del repo ---
            star_link = article.select_one("a[href$='/stargazers']")
            total_stars = 0
            if star_link:
                try:
                    total_stars = int(
                        star_link.get_text(strip=True).replace(",", "")
                    )
                except ValueError:
                    pass

            # --- Estrellas ganadas en el período (métrica de trending) ---
            period_span = article.select_one("span.d-inline-block.float-sm-right")
            stars_periodo = 0
            period_label = f"stars {'today' if since == 'daily' else 'this week'}"
            if period_span:
                period_text = period_span.get_text(strip=True)
                m = re.search(r"([\d,]+)", period_text)
                if m:
                    try:
                        stars_periodo = int(m.group(1).replace(",", ""))
                    except ValueError:
                        pass

            # --- Lenguaje ---
            lang_span = article.select_one("span[itemprop='programmingLanguage']")
            language = lang_span.get_text(strip=True) if lang_span else ""

            # --- Clasificación por área ---
            es_rel, area = _es_relevante(
                full_name, f"{descripcion} {language}", areas_interes
            )
            if not es_rel:
                area = "arquitectura_software"  # trending siempre relevante

            # Título enriquecido con ambas métricas de estrellas
            titulo = (
                f"[GitHub] {full_name} "
                f"⭐{total_stars:,} "
                f"(+{stars_periodo:,} {period_label})"
            )

            id_hash = _calcular_hash_diario(full_name, url_repo)
            noticias.append(Noticia(
                id=id_hash,
                titulo=titulo,
                url=url_repo,
                fuente=nombre_base,
                fecha_publicacion=None,
                descripcion_original=descripcion[:1000],
                resumen_ia="Resumen no disponible",
                area_matcheada=area,
                fecha_ingesta=_ahora_utc(),
                ranking=idx + 1,
            ))

        # Ordenar por estrellas del período (descendente) antes de persistir
        noticias.sort(
            key=lambda n: _extraer_stars_periodo(n.titulo),
            reverse=True,
        )

    except requests.exceptions.HTTPError as exc:
        logger.warning("GitHub Trending HTTP error: %s", exc)
        metricas["fuentes_fallidas"] += 1
        metricas["nombres_fallidas"].append(nombre)
    except Exception as exc:
        logger.error("Error en scraper GitHub Trending %s: %s", since, exc)
        metricas["fuentes_fallidas"] += 1
        metricas["nombres_fallidas"].append(nombre)

    return noticias, metricas


def _extraer_stars_periodo(titulo: str) -> int:
    """Extrae el número de estrellas del período del título enriquecido."""
    m = re.search(r"\(\+(\d[\d,]*)", titulo)
    if m:
        try:
            return int(m.group(1).replace(",", ""))
        except ValueError:
            pass
    return 0



# ---------------------------------------------------------------------------
# Worker HN Firebase — top stories actuales (Monitoreo de Hoy)
# ---------------------------------------------------------------------------

def _worker_hn(
    fuente_cfg: dict,
    app_cfg: dict,
    areas_interes: dict,
) -> tuple[list[Noticia], dict]:
    """
    Ingesta Hacker News Top Stories via Firebase API pública.
    Solo incluye stories con score >= hn_min_score.
    Alimenta "Monitoreo de Hoy".
    """
    nombre = fuente_cfg.get("nombre", "Hacker News")
    timeout = app_cfg.get("timeout_request", 15)
    min_score = app_cfg.get("hn_min_score", 100)

    metricas = _metricas_vacias(nombre + " (hoy)")
    noticias: list[Noticia] = []

    BASE = "https://hacker-news.firebaseio.com/v0"
    headers = {"User-Agent": "NewsTrendAnalyzer/4.0"}

    try:
        resp = requests.get(f"{BASE}/topstories.json", timeout=timeout, headers=headers)
        resp.raise_for_status()
        top_ids = resp.json()[:30]  # Top 30 historias del momento
        logger.info("HN Firebase: %d IDs recibidos, score >= %d.", len(top_ids), min_score)

        def _fetch_story(story_id: int) -> dict | None:
            try:
                r = requests.get(f"{BASE}/item/{story_id}.json", timeout=5, headers=headers)
                r.raise_for_status()
                return r.json()
            except Exception:
                return None

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
            items = list(pool.map(_fetch_story, top_ids))

        for item in items:
            if not item or item.get("type") != "story":
                continue
            metricas["total_procesadas"] += 1

            score = item.get("score", 0)
            if score < min_score:
                metricas["no_relevantes"] += 1
                continue

            titulo = item.get("title", "").strip()
            url = item.get("url", f"https://news.ycombinator.com/item?id={item.get('id')}")
            discussion_url = f"https://news.ycombinator.com/item?id={item.get('id')}"
            texto = item.get("text", "") or ""
            ts = item.get("time")
            fecha = datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None) if ts else None

            if not titulo:
                continue

            es_rel, area = _es_relevante(titulo, texto, areas_interes)
            if not es_rel:
                area = "ciencias_computacion"

            id_hash = _calcular_hash(titulo, url)
            noticias.append(Noticia(
                id=id_hash,
                titulo=f"[HN] {titulo} 🔺{score}",
                url=url,
                discussion_url=discussion_url,
                fuente=nombre,
                fecha_publicacion=fecha,
                descripcion_original=texto[:1000],
                resumen_ia="Resumen no disponible",
                area_matcheada=area,
                fecha_ingesta=_ahora_utc(),
                num_comentarios=item.get("descendants", 0) or 0,
                score=score,
            ))

    except Exception as exc:
        logger.error("Error en worker HN Firebase: %s", exc)
        metricas["fuentes_fallidas"] += 1
        metricas["nombres_fallidas"].append(metricas["nombre"])

    return noticias, metricas


# ---------------------------------------------------------------------------
# Worker HN Algolia — histórico 7 días (Tendencias 7 Días)
# ---------------------------------------------------------------------------

def _worker_hn_algolia(
    fuente_cfg: dict,
    app_cfg: dict,
    areas_interes: dict,
    dias_ventana: int = 7,
) -> tuple[list[Noticia], dict]:
    """
    Ingesta Hacker News vía Algolia Search API (pública, sin auth).
    Permite recuperar stories de los últimos N días con filtro por score.
    Alimenta "Tendencias 7 Días".

    Endpoint: https://hn.algolia.com/api/v1/search
    Parámetros:
      tags=story
      numericFilters=created_at_i>TIMESTAMP,points>MIN_SCORE
      hitsPerPage=100
    """
    nombre = fuente_cfg.get("nombre", "Hacker News")
    timeout = app_cfg.get("timeout_request", 15)
    min_score = app_cfg.get("hn_algolia_min_score", 50)
    count = app_cfg.get("hn_algolia_count", 100)

    metricas = _metricas_vacias(f"{nombre} Algolia {dias_ventana}d")
    noticias: list[Noticia] = []

    BASE_ALGOLIA = "https://hn.algolia.com/api/v1/search"
    headers = {"User-Agent": "NewsTrendAnalyzer/4.0"}

    try:
        ts_desde = int((datetime.now(timezone.utc) - timedelta(days=dias_ventana)).timestamp())
        url = (
            f"{BASE_ALGOLIA}"
            f"?tags=story"
            f"&numericFilters=created_at_i>{ts_desde},points>{min_score}"
            f"&hitsPerPage={count}"
            f"&attributesToRetrieve=title,url,points,created_at_i,objectID,story_text,num_comments"
        )
        logger.info("HN Algolia %dd: GET (min_score=%d, count=%d)", dias_ventana, min_score, count)
        resp = requests.get(url, timeout=timeout, headers=headers)
        resp.raise_for_status()
        hits = resp.json().get("hits", [])
        logger.info("HN Algolia %dd: %d stories obtenidas.", dias_ventana, len(hits))

        for hit in hits:
            metricas["total_procesadas"] += 1
            titulo = (hit.get("title") or "").strip()
            url_hit = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
            discussion_url = f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
            texto = hit.get("story_text") or ""
            score = hit.get("points", 0)
            ts = hit.get("created_at_i")
            fecha = datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None) if ts else None

            if not titulo:
                continue

            es_rel, area = _es_relevante(titulo, texto, areas_interes)
            if not es_rel:
                area = "ciencias_computacion"

            id_hash = _calcular_hash(titulo, url_hit)
            noticias.append(Noticia(
                id=id_hash,
                titulo=f"[HN] {titulo} 🔺{score}",
                url=url_hit,
                discussion_url=discussion_url,
                fuente=nombre,
                fecha_publicacion=fecha,
                descripcion_original=texto[:1000],
                resumen_ia="Resumen no disponible",
                area_matcheada=area,
                fecha_ingesta=_ahora_utc(),
                num_comentarios=hit.get("num_comments", 0) or 0,
                score=score,
            ))

    except Exception as exc:
        logger.error("Error en worker HN Algolia: %s", exc)
        metricas["fuentes_fallidas"] += 1
        metricas["nombres_fallidas"].append(metricas["nombre"])

    return noticias, metricas


# ---------------------------------------------------------------------------
# Worker RSS genérico (Reddit y futuros feeds)
# ---------------------------------------------------------------------------

def _worker_rss(
    fuente_cfg: dict,
    app_cfg: dict,
    areas_interes: dict,
) -> tuple[list[Noticia], dict]:
    """Worker genérico para fuentes RSS (feedparser)."""
    nombre = fuente_cfg.get("nombre", "RSS")
    url_fuente = fuente_cfg.get("url", "")
    timeout = app_cfg.get("timeout_request", 15)

    metricas = _metricas_vacias(nombre)
    noticias: list[Noticia] = []

    headers = {"User-Agent": "NewsTrendAnalyzer/4.0 (+https://github.com/newser)"}
    try:
        response = requests.get(url_fuente, timeout=timeout, headers=headers)
        response.raise_for_status()
        feed = feedparser.parse(response.content)
        entradas = feed.get("entries", [])
        logger.info("RSS %s: %d entradas recibidas.", nombre, len(entradas))

        for entrada in entradas:
            metricas["total_procesadas"] += 1
            titulo = entrada.get("title", "Sin título").strip()
            url = entrada.get("link", "").strip()
            descripcion = entrada.get("summary", entrada.get("description", "")).strip()

            fecha_pub = None
            fecha_raw = entrada.get("published") or entrada.get("updated")
            if fecha_raw:
                try:
                    from email.utils import parsedate_to_datetime
                    fecha_pub = parsedate_to_datetime(fecha_raw).replace(tzinfo=None)
                except Exception:
                    try:
                        fecha_pub = datetime(*fecha_raw[:6])
                    except Exception:
                        pass

            es_rel, area = _es_relevante(titulo, descripcion, areas_interes)
            if not es_rel:
                metricas["no_relevantes"] += 1
                continue

            id_hash = _calcular_hash(titulo, url)
            noticias.append(Noticia(
                id=id_hash,
                titulo=titulo,
                url=url,
                fuente=nombre,
                fecha_publicacion=fecha_pub,
                descripcion_original=descripcion,
                resumen_ia="Resumen no disponible",
                area_matcheada=area,
                fecha_ingesta=_ahora_utc(),
            ))

    except requests.exceptions.Timeout:
        logger.warning("Timeout al conectar con '%s'.", url_fuente)
        metricas["fuentes_fallidas"] += 1
        metricas["nombres_fallidas"].append(nombre)
    except Exception as exc:
        logger.error("Error en worker RSS '%s': %s", nombre, exc)
        metricas["fuentes_fallidas"] += 1
        metricas["nombres_fallidas"].append(nombre)

    return noticias, metricas


# ---------------------------------------------------------------------------
# Orquestador — Dual-Window Pipeline
# ---------------------------------------------------------------------------

def _acumular_metricas(dest: dict, src: dict) -> None:
    dest["total_procesadas"] += src.get("total_procesadas", 0)
    dest["fuentes_fallidas"] += src.get("fuentes_fallidas", 0)
    dest["nombres_fallidas"].extend(src.get("nombres_fallidas", []))
    dest["no_relevantes"] += src.get("no_relevantes", 0)


def ejecutar_ingesta(progress_callback: Callable[[str], None] | None = None) -> dict[str, Any]:
    """
    Orquesta el pipeline de ingesta DUAL-WINDOW en paralelo.

    Por cada ejecución lanza hasta 4 workers simultáneos:
      1. GitHub 1d    → "Monitoreo de Hoy"
      2. GitHub 7d    → "Tendencias 7 Días"
      3. HN Firebase  → "Monitoreo de Hoy"   (top stories actuales)
      4. HN Algolia   → "Tendencias 7 Días"  (histórico 7d)
      + Cualquier fuente RSS activa en config.yaml

    Returns:
        dict con métricas globales del proceso.
    """
    if progress_callback:
        progress_callback("Cargando configuración de fuentes...")

    config = cargar_config()
    app_cfg = config.get("app", {})
    areas_interes = config.get("areas_interes", {})
    fuentes = config.get("fuentes", [])

    metricas: dict[str, Any] = {
        "total_procesadas": 0,
        "nuevas_persistidas": 0,
        "duplicadas_omitidas": 0,
        "fuentes_fallidas": 0,
        "nombres_fallidas": [],
        "no_relevantes": 0,
    }

    # --- Construir lista de tareas ---
    tareas: list[tuple[str, Any, tuple]] = []  # (label, fn, args)

    fuentes_activas = [f for f in fuentes if f.get("activa", True)]
    for fuente_cfg in fuentes_activas:
        tipo = fuente_cfg.get("tipo", "rss").lower()
        nombre = fuente_cfg.get("nombre", "?")

        if tipo == "github_api":
            dias_hoy = app_cfg.get("github_trending_dias_hoy", 1)
            dias_sem = app_cfg.get("github_trending_dias_semanal", 7)
            tareas.append((
                f"GitHub {dias_hoy}d (hoy)",
                _worker_github,
                (fuente_cfg, app_cfg, areas_interes, dias_hoy),
            ))
            tareas.append((
                f"GitHub {dias_sem}d (semana)",
                _worker_github,
                (fuente_cfg, app_cfg, areas_interes, dias_sem),
            ))

        elif tipo == "hn_api":
            # Firebase: top stories actuales
            tareas.append((
                "HN Firebase (hoy)",
                _worker_hn,
                (fuente_cfg, app_cfg, areas_interes),
            ))
            # Algolia: histórico 7 días
            dias_sem = app_cfg.get("github_trending_dias_semanal", 7)
            tareas.append((
                f"HN Algolia {dias_sem}d (semana)",
                _worker_hn_algolia,
                (fuente_cfg, app_cfg, areas_interes, dias_sem),
            ))

        elif tipo == "rss":
            tareas.append((
                nombre,
                _worker_rss,
                (fuente_cfg, app_cfg, areas_interes),
            ))

        elif tipo == "global_news":
            tareas.append((
                nombre,
                _worker_global_news,
                (fuente_cfg, app_cfg, areas_interes),
            ))

    msg = f"Iniciando ingesta DUAL-WINDOW: {len(tareas)} workers paralelos."
    logger.info(msg)
    if progress_callback:
        progress_callback(msg)

    todas_noticias: list[Noticia] = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(tareas) or 1) as executor:
        futuros = {
            executor.submit(fn, *args): label
            for label, fn, args in tareas
        }
        for fut in concurrent.futures.as_completed(futuros):
            label = futuros[fut]
            try:
                noticias_loc, met_loc = fut.result()
                todas_noticias.extend(noticias_loc)
                _acumular_metricas(metricas, met_loc)
                if progress_callback:
                    progress_callback(f"✅ {label}: {len(noticias_loc)} artículos")
                logger.info("Worker '%s': %d artículos preseleccionados.", label, len(noticias_loc))
            except Exception as exc:
                logger.error("Error en worker '%s': %s", label, exc)
                metricas["fuentes_fallidas"] += 1
                metricas["nombres_fallidas"].append(label)

    # --- Persistencia con deduplicación ---
    if todas_noticias:
        msg = f"💾 Deduplicando y persistiendo {len(todas_noticias)} artículos..."
        logger.info(msg)
        if progress_callback:
            progress_callback(msg)

        noticias_unicas = {n.id: n for n in todas_noticias}
        with get_session() as session:
            for noticia in noticias_unicas.values():
                existing = session.get(Noticia, noticia.id)
                if existing is None:
                    session.add(noticia)
                    metricas["nuevas_persistidas"] += 1
                else:
                    if noticia.discussion_url and not existing.discussion_url:
                        existing.discussion_url = noticia.discussion_url
                    if existing.fecha_publicacion is None and noticia.fecha_publicacion is not None:
                        existing.fecha_publicacion = noticia.fecha_publicacion
                    metricas["duplicadas_omitidas"] += 1
            session.commit()

    msg_fin = (
        f"Ingesta completada · Nuevas: {metricas['nuevas_persistidas']} · "
        f"Duplicadas: {metricas['duplicadas_omitidas']} · "
        f"Fallos: {metricas['fuentes_fallidas']}"
    )
    logger.info(msg_fin)
    if progress_callback:
        progress_callback(msg_fin)

    return metricas
