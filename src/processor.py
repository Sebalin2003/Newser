# =============================================================================
# src/processor.py
# =============================================================================
"""
Módulo de procesamiento y enriquecimiento de datos — v2.0.

Responsabilidades:
- Tokenización NLP y cálculo de tendencias por frecuencia de términos.
- Clustering diario con TF-IDF + similitud de coseno + NER veto (spaCy).
- Scoring de clústers: decaimiento temporal × autoridad de fuente × volumen.
- Generación del MacroResumen ejecutivo diario (Gemini, con guardarraíl de bajo volumen).
- Enriquecimiento individual de noticias con resúmenes de IA.
- Degradación elegante: cada componente falla de forma aislada sin crashear el pipeline.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import hashlib
import string
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import yaml
from dotenv import load_dotenv
from sqlalchemy import select

# Motor IA: Gemini (primario) — nuevo SDK google-genai
try:
    from google import genai as google_genai
    from google.genai import types as google_genai_types
    GEMINI_AVAILABLE = True
except ImportError:
    google_genai_types = None
    GEMINI_AVAILABLE = False
    logging.getLogger(__name__).warning("google-genai no instalado. Ejecuta: pip install google-genai")

from .database import Cluster, MacroResumen, Noticia, Tendencia, get_session
from .global_news import GlobalNewsItem, fetch_global_news
from .scoring import SCORE_VERSION, score_recent_items

# ---------------------------------------------------------------------------
# Dependencias opcionales (degradación elegante si no están instaladas)
# ---------------------------------------------------------------------------
try:
    from sentence_transformers import SentenceTransformer, util
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except Exception as exc:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    logging.getLogger(__name__).warning("sentence-transformers no disponible. Clustering semantico deshabilitado: %s", exc)

try:
    import spacy
    SPACY_AVAILABLE = True
except Exception as exc:
    SPACY_AVAILABLE = False
    logging.getLogger(__name__).warning("spaCy no disponible. NER deshabilitado: %s", exc)

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
load_dotenv()
logger = logging.getLogger(__name__)
CONFIG_PATH: Path = Path(__file__).parent.parent / "config.yaml"


# ---------------------------------------------------------------------------
# Stopwords bilingüe (español + inglés)
# ---------------------------------------------------------------------------
STOPWORDS: frozenset[str] = frozenset(
    {
        # Español
        "de", "la", "el", "en", "y", "a", "los", "del", "se", "las",
        "un", "por", "con", "no", "una", "su", "para", "es", "al", "lo",
        "como", "más", "pero", "sus", "le", "ya", "o", "fue", "este",
        "ha", "si", "sobre", "ser", "tiene", "año", "cuando", "también",
        "hasta", "hay", "desde", "todo", "nos", "durante", "entre",
        "sin", "son", "estado", "bien", "sido", "donde", "esta",
        "que", "así", "ante", "bajo", "cada", "cual", "cuya", "cuyo",
        "dos", "era", "esa", "ese", "eso", "han", "muy", "ni", "otro",
        "poco", "pues", "sea", "tan", "te", "toda", "todos", "tras",
        # Inglés
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to",
        "for", "of", "with", "by", "from", "as", "is", "was", "are",
        "were", "be", "been", "being", "have", "has", "had", "do",
        "does", "did", "will", "would", "could", "should", "may",
        "might", "shall", "can", "that", "this", "these", "those",
        "it", "its", "they", "their", "them", "he", "she", "his",
        "her", "we", "our", "you", "your", "i", "my", "me", "us",
        "not", "no", "nor", "so", "yet", "both", "either", "neither",
        "each", "every", "all", "any", "few", "more", "most", "other",
        "such", "than", "too", "very", "just", "into", "over", "after",
        "about", "up", "out", "then", "now", "how", "what", "who",
        "which", "when", "where", "why", "new", "says", "said", "get",
        "set", "use", "s", "t", "re", "ve", "ll", "d", "m",
    }
)


# ===========================================================================
# Helpers de texto
# ===========================================================================

def _tokenizar(texto: str) -> list[str]:
    """Tokeniza un texto: minúsculas, sin puntuación, sin stopwords, longitud >= 3."""
    texto_limpio = texto.lower().translate(str.maketrans("", "", string.punctuation))
    tokens = re.findall(r"\b[a-záéíóúüñ]{3,}\b", texto_limpio)
    return [t for t in tokens if t not in STOPWORDS]


def _calcular_densidad_keywords(titulo: str, areas_interes: dict[str, list[str]]) -> int:
    """Cuenta cuántas keywords del config coinciden en el título (para ranking de IA)."""
    titulo_lower = titulo.lower()
    return sum(
        1
        for keywords in areas_interes.values()
        for kw in keywords
        if kw.lower() in titulo_lower
    )


# ===========================================================================
# Motor de spaCy — carga diferida
# ===========================================================================

def _cargar_spacy_model():
    """
    Carga el modelo en_core_web_sm de spaCy.
    Retorna None con warning si el modelo no está instalado.
    """
    if not SPACY_AVAILABLE:
        logger.warning(
            "spaCy no está instalado. NER veto deshabilitado. "
            "Instalá con: pip install spacy && python -m spacy download en_core_web_sm"
        )
        return None
    try:
        nlp = spacy.load("en_core_web_sm", disable=["parser", "tagger", "lemmatizer"])
        logger.info("Modelo spaCy 'en_core_web_sm' cargado.")
        return nlp
    except OSError:
        logger.warning(
            "Modelo spaCy 'en_core_web_sm' no encontrado. "
            "Ejecutá: python -m spacy download en_core_web_sm"
        )
        return None

# Modelo Sentence Transformer cacheado globalmente
_sentence_model = None

def _cargar_sentence_transformer():
    """
    Carga el modelo paraphrase-multilingual-MiniLM-L12-v2 de sentence-transformers.
    Lo mantiene en caché en memoria.
    """
    global _sentence_model
    if not SENTENCE_TRANSFORMERS_AVAILABLE:
        logger.warning(
            "sentence-transformers no está instalado. "
            "Instalá con: pip install sentence-transformers"
        )
        return None
    if _sentence_model is None:
        logger.info("Cargando modelo sentence-transformer 'paraphrase-multilingual-MiniLM-L12-v2' (solo primera vez)...")
        _sentence_model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
        logger.info("Modelo cargado.")
    return _sentence_model


def extraer_entidades(texto: str, nlp) -> set[str]:
    """
    Extrae entidades ORG y PRODUCT de un texto usando spaCy.

    Args:
        texto: Texto a analizar (título de la noticia).
        nlp:   Modelo spaCy cargado, o None si no disponible.

    Returns:
        set[str]: Entidades normalizadas (lowercase, strip).
    """
    if nlp is None or not texto.strip():
        return set()
    doc = nlp(texto)
    return {
        ent.text.strip().lower()
        for ent in doc.ents
        if ent.label_ in ("ORG", "PRODUCT") and len(ent.text.strip()) > 2
    }


# ===========================================================================
# Motor de Tendencias NLP
# ===========================================================================

def calcular_tendencias(top_n: int = 10) -> list[dict[str, Any]]:
    """
    Extrae Top N términos del corpus de títulos en DB y los persiste como Tendencias.
    Reemplaza el conjunto anterior en cada ejecución.
    """
    logger.info("Calculando Top %d tendencias desde títulos en DB...", top_n)

    with get_session() as session:
        titulos_raw = session.execute(select(Noticia.titulo)).scalars().all()

    if not titulos_raw:
        logger.warning("No hay noticias en DB para calcular tendencias.")
        return []

    contador: Counter = Counter()
    for titulo in titulos_raw:
        contador.update(_tokenizar(titulo))

    top_terminos = contador.most_common(top_n)
    fecha_analisis = datetime.utcnow()

    with get_session() as session:
        session.query(Tendencia).delete()
        for palabra, frecuencia in top_terminos:
            session.add(Tendencia(
                palabra=palabra,
                frecuencia=frecuencia,
                fecha_analisis=fecha_analisis,
            ))

    resultado = [{"palabra": p, "frecuencia": f} for p, f in top_terminos]
    logger.info("Tendencias calculadas: %s", resultado)
    return resultado


# ===========================================================================
# Clustering Diario — TF-IDF + NER Veto + Scoring Ponderado
# ===========================================================================

def clustering_diario(config: dict, progress_callback: Callable[[str], None] = None) -> dict[str, int]:
    """
    Agrupa las noticias de las últimas 24h usando Sentence Transformers + cosine similarity.

    Algoritmo:
    1. Carga noticias de la ventana temporal configurada.
    2. Extrae entidades con spaCy (NER).
    3. Vectoriza títulos con TF-IDF bigramas.
    4. NER veto: pares similares sin entidades compartidas → similitud forzada a 0.
    5. Clustering greedy: asigna cada noticia al clúster más similar o crea uno nuevo.
    6. Calcula score ponderado: decay × autoridad × log-volumen.
    7. Persiste clústers en DB y actualiza cluster_id en cada Noticia.

    Returns:
        dict con métricas: clusters_generados, noticias_agrupadas.
    """
    if not SENTENCE_TRANSFORMERS_AVAILABLE:
        logger.warning("sentence-transformers no disponible. Clustering omitido.")
        return {"clusters_generados": 0, "noticias_agrupadas": 0}

    app_cfg = config.get("app", {})
    umbral: float = float(app_cfg.get("clustering_umbral", 0.65))
    horas: int = int(app_cfg.get("clustering_ventana_horas", 24))
    areas_interes = config.get("areas_interes", {})
    fuentes_config = {
        f["nombre"]: float(f.get("autoridad", 0.7))
        for f in config.get("fuentes", [])
    }

    # 1. Cargar noticias del período
    cutoff = datetime.utcnow() - timedelta(hours=horas)
    noticias_raw: list[dict] = []

    with get_session() as session:
        rows = (
            session.query(Noticia)
            .filter(Noticia.fecha_ingesta >= cutoff)
            .all()
        )
        for n in rows:
            noticias_raw.append({
                "id":              n.id,
                "titulo":          n.titulo or "",
                "descripcion":     n.descripcion_original or "",
                "fuente":          n.fuente or "Desconocida",
                "fecha_publicacion": n.fecha_publicacion,
                "area":            n.area_matcheada or "general",
                "entidades_json":  n.entidades_json,
                "entidades":       set(),
            })

    n_docs = len(noticias_raw)
    if n_docs < 2:
        logger.info(
            "Solo %d noticia(s) en las últimas %dh. Clustering omitido.", n_docs, horas
        )
        return {"clusters_generados": 0, "noticias_agrupadas": n_docs}

    if progress_callback:
        progress_callback(f"Clusterizando {n_docs} noticias (umbral={umbral})...")

    logger.info(
        "Iniciando clustering de %d noticias (umbral=%.2f, ventana=%dh)…",
        n_docs, umbral, horas,
    )

    # 2. Extraer entidades con spaCy
    nlp = _cargar_spacy_model()
    for nd in noticias_raw:
        if nd["entidades_json"]:
            try:
                nd["entidades"] = set(json.loads(nd["entidades_json"]))
            except (json.JSONDecodeError, TypeError):
                nd["entidades"] = set()
        else:
            entidades = extraer_entidades(nd["titulo"], nlp)
            nd["entidades"] = entidades
            # Persistir en DB
            with get_session() as session:
                noticia_db = session.get(Noticia, nd["id"])
                if noticia_db:
                    noticia_db.entidades_json = json.dumps(sorted(entidades))

    # 3. Sentence Transformers + cosine similarity
    textos_a_codificar = [
        f"{nd['titulo']} {nd.get('descripcion', '')}".strip() for nd in noticias_raw
    ]
    model = _cargar_sentence_transformer()
    
    if model is None:
        logger.error("No se pudo cargar el modelo de Sentence Transformers.")
        return {"clusters_generados": 0, "noticias_agrupadas": 0}

    try:
        embeddings = model.encode(textos_a_codificar, convert_to_tensor=True)
        # util.cos_sim retorna un tensor de PyTorch; lo pasamos a lista de listas
        sim_mat_tensor = util.cos_sim(embeddings, embeddings)
        sim_mat: list[list[float]] = sim_mat_tensor.tolist()
    except Exception as exc:
        logger.error("Error al calcular embeddings semánticos: %s", exc)
        return {"clusters_generados": 0, "noticias_agrupadas": 0}

    # 4. NER veto: fuerza similitud a 0 si ambas noticias tienen entidades pero no las comparten
    if nlp is not None:
        for i in range(n_docs):
            for j in range(i + 1, n_docs):
                if sim_mat[i][j] >= umbral:
                    ei = noticias_raw[i]["entidades"]
                    ej = noticias_raw[j]["entidades"]
                    if ei and ej and not ei.intersection(ej):
                        sim_mat[i][j] = 0.0
                        sim_mat[j][i] = 0.0

    # 5. Clustering greedy
    asignaciones: list[int] = [-1] * n_docs
    clusters_indices: list[list[int]] = []

    for i in range(n_docs):
        if asignaciones[i] != -1:
            continue

        mejor_cluster = -1
        mejor_sim = umbral

        for c_idx, miembros in enumerate(clusters_indices):
            sim_prom = sum(sim_mat[i][j] for j in miembros) / len(miembros)
            if sim_prom >= mejor_sim:
                mejor_sim = sim_prom
                mejor_cluster = c_idx

        if mejor_cluster >= 0:
            clusters_indices[mejor_cluster].append(i)
            asignaciones[i] = mejor_cluster
        else:
            clusters_indices.append([i])
            asignaciones[i] = len(clusters_indices) - 1

    # 6. Construir y persistir clústers
    # Usar hora LOCAL del sistema para que fecha_cluster coincida con la fecha
    # que la UI consulta (también con datetime.now()). UTC causa desfase en TZ negativas.
    now = datetime.now()
    fecha_hoy = now.date()

    # Eliminar clústers del día para regeneración limpia
    with get_session() as session:
        session.query(Cluster).filter(Cluster.fecha_cluster == fecha_hoy).delete()

    clusters_creados = 0

    for indices in clusters_indices:
        noticias_c = [noticias_raw[i] for i in indices]

        fuentes_unicas = list({nd["fuente"] for nd in noticias_c})
        n_fuentes = len(fuentes_unicas)
        n_noticias_c = len(noticias_c)

        # Fecha de publicación más reciente del clúster (normalizada a naive UTC)
        fechas_pub = [
            nd["fecha_publicacion"] for nd in noticias_c if nd["fecha_publicacion"]
        ]
        if fechas_pub:
            fechas_naive = []
            for f in fechas_pub:
                if hasattr(f, "tzinfo") and f.tzinfo is not None:
                    f = f.replace(tzinfo=None)
                fechas_naive.append(f)
            fecha_max = max(fechas_naive)
            horas_old = max(0.0, (now - fecha_max).total_seconds() / 3600)
        else:
            horas_old = 12.0  # conservador

        # Score: decay × autoridad × log-volumen
        decay = math.exp(-0.06 * horas_old)
        autoridad_prom = (
            sum(fuentes_config.get(nd["fuente"], 0.7) for nd in noticias_c) / n_noticias_c
        )
        volumen = math.log2(1 + n_fuentes)
        score = round(decay * autoridad_prom * volumen, 4)

        # Título representativo: mayor densidad de keywords
        titulo_rep = max(
            noticias_c,
            key=lambda nd: _calcular_densidad_keywords(nd["titulo"], areas_interes),
        )["titulo"]

        # Área dominante
        areas = [nd["area"] for nd in noticias_c if nd["area"]]
        area_dom = Counter(areas).most_common(1)[0][0] if areas else "general"

        # Entidades combinadas del clúster
        todas_entidades: set[str] = set()
        for nd in noticias_c:
            todas_entidades.update(nd["entidades"])

        cluster_obj = Cluster(
            titulo_representativo=titulo_rep[:512],
            fecha_cluster=fecha_hoy,
            score=score,
            n_noticias=n_noticias_c,
            n_fuentes=n_fuentes,
            area=area_dom,
            entidades_json=json.dumps(sorted(todas_entidades)),
            fecha_creacion=now,
        )

        with get_session() as session:
            session.add(cluster_obj)
            session.flush()
            cluster_db_id = cluster_obj.id

        # Actualizar cluster_id en cada noticia del clúster
        for idx in indices:
            noticia_id = noticias_raw[idx]["id"]
            with get_session() as session:
                nd_db = session.get(Noticia, noticia_id)
                if nd_db:
                    nd_db.cluster_id = cluster_db_id

        clusters_creados += 1
        logger.info(
            "Clúster #%d: '%s…' (%d noticias, %d fuentes, score=%.3f)",
            cluster_db_id, titulo_rep[:50], n_noticias_c, n_fuentes, score,
        )

    logger.info("Clustering completado: %d clústers generados.", clusters_creados)
    return {"clusters_generados": clusters_creados, "noticias_agrupadas": n_docs}


# ===========================================================================
# Motor de IA — Gemini
# ===========================================================================

DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-lite"
GEMINI_FALLBACK_MODELS = ("gemini-2.5-flash-lite",)
DEPRECATED_GEMINI_MODELS = {"gemini-2.0-flash", "gemini-2-flash"}
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
_configured_gemini_model = os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL).strip() or DEFAULT_GEMINI_MODEL
GEMINI_MODEL = DEFAULT_GEMINI_MODEL if _configured_gemini_model in DEPRECATED_GEMINI_MODELS else _configured_gemini_model
LAST_GEMINI_ERROR: str | None = None
LAST_GEMINI_MODEL: str | None = None

_PROMPT_RESUMEN = (
    "Eres un analista de noticias tecnológicas. "
    "Resume el siguiente titular en español para un lector técnico. "
    "Explica qué pasó y por qué importa, sin inventar datos. "
    "Responde solo JSON válido con la clave 'resumen' (máximo 3 frases).\n\n"
    "Titular: {titulo}\n\nRespuesta JSON:"
)

_PROMPT_RESUMEN_EN = (
    "You are a technology news analyst. "
    "Summarize the following headline in English for a technical reader. "
    "Explain what happened and why it matters, without inventing facts. "
    "Return only valid JSON with the key 'resumen' (maximum 3 sentences).\n\n"
    "Headline: {titulo}\n\nJSON response:"
)

_PROMPT_MACRO = (
    "Sos un analista senior de tecnología. "
    "Analizá los siguientes eventos informativos del día y redictá un briefing ejecutivo "
    "de exactamente 4 oraciones en español. Identificá los temas críticos, "
    "las organizaciones más activas y las tendencias emergentes. "
    "Usa lenguaje de negocios claro y directo. No uses viñetas ni numeración.\n\n"
    "Eventos destacados del día ({fecha}):\n{eventos}\n\nBriefing ejecutivo:"
)


def normalize_language(language: str | None = None) -> str:
    return "en" if str(language or "").strip().lower().startswith("en") else "es"


def build_article_summary_prompt(titulo: str, language: str | None = None) -> str:
    template = _PROMPT_RESUMEN_EN if normalize_language(language) == "en" else _PROMPT_RESUMEN
    return template.format(titulo=titulo)


def _verificar_gemini() -> bool:
    """Verifica configuracion local de Gemini sin gastar una llamada API."""
    global LAST_GEMINI_ERROR
    LAST_GEMINI_ERROR = None

    if not GEMINI_AVAILABLE:
        LAST_GEMINI_ERROR = "Gemini no esta disponible: falta instalar `google-genai`."
        logger.warning("google-genai no está instalado. IA deshabilitada.")
        return False
    if not GEMINI_API_KEY:
        LAST_GEMINI_ERROR = "Gemini no esta configurado: falta `GEMINI_API_KEY`."
        logger.warning("GEMINI_API_KEY no configurada. IA deshabilitada.")
        return False
    logger.info("Gemini configurado localmente; preflight remoto omitido para proteger cuota.")
    return True

def _gemini_candidate_models() -> list[str]:
    """Return configured Gemini model plus safe fallbacks, without duplicates."""
    models: list[str] = []
    for model in (GEMINI_MODEL, DEFAULT_GEMINI_MODEL, *GEMINI_FALLBACK_MODELS):
        model = str(model or "").strip()
        if model and model not in models:
            models.append(model)
    return models


def _is_gemini_fallback_error(exc: Exception) -> bool:
    msg_lower = str(exc).lower()
    return any(
        marker in msg_lower
        for marker in ("429", "quota", "rate", "exhausted", "not found", "model")
    )


def _gemini_model_usado() -> str:
    return LAST_GEMINI_MODEL or GEMINI_MODEL


def _mensaje_error_gemini(exc: Exception, model: str | None = None) -> str:
    """Convierte errores del SDK en mensajes seguros para mostrar en la UI."""
    model = model or GEMINI_MODEL
    msg = str(exc)
    msg_lower = msg.lower()
    if "429" in msg or "quota" in msg_lower or "rate" in msg_lower or "exhausted" in msg_lower:
        return (
            f"Gemini respondio sin cuota disponible para `{model}`. "
            "Revisa cuota/billing en Google AI Studio o configura otro `GEMINI_MODEL` con cuota."
        )
    if "api key" in msg_lower or "apikey" in msg_lower or "permission_denied" in msg_lower or "unauthorized" in msg_lower:
        return "Gemini rechazo la API key. Revisa `GEMINI_API_KEY` y reinicia la app."
    if "not found" in msg_lower or "model" in msg_lower:
        return f"El modelo `{model}` no esta disponible para esta API key. Cambia `GEMINI_MODEL` y reinicia la app."
    return "Gemini no pudo generar el resumen. Revisa la configuracion y vuelve a intentar."


def _llamar_gemini(prompt: str, progress_callback: Callable[[str], None] = None, interactive: bool = False) -> str | None:
    """
    Llama a Gemini usando el nuevo SDK google-genai.
    Prueba el modelo configurado y fallbacks solo ante cuota/modelo no disponible.
    """
    global LAST_GEMINI_ERROR, LAST_GEMINI_MODEL
    LAST_GEMINI_ERROR = None
    LAST_GEMINI_MODEL = None

    if not GEMINI_AVAILABLE:
        LAST_GEMINI_ERROR = "Gemini no esta disponible: falta instalar `google-genai`."
        if progress_callback:
            progress_callback("Gemini no esta disponible: falta instalar google-genai.")
        return None
    if not GEMINI_API_KEY:
        LAST_GEMINI_ERROR = "Gemini no esta configurado: falta `GEMINI_API_KEY`."
        if progress_callback:
            progress_callback("Gemini no esta configurado: falta GEMINI_API_KEY.")
        return None

    import traceback

    client = google_genai.Client(api_key=GEMINI_API_KEY)
    request_config = None
    if interactive and google_genai_types is not None:
        request_config = google_genai_types.GenerateContentConfig(
            temperature=0.2,
            maxOutputTokens=180,
            responseMimeType="application/json",
            responseSchema={
                "type": "object",
                "properties": {"resumen": {"type": "string"}},
                "required": ["resumen"],
            },
            thinkingConfig=google_genai_types.ThinkingConfig(thinkingBudget=0),
        )
    attempted_models: list[str] = []
    for model in _gemini_candidate_models():
        attempted_models.append(model)
        try:
            kwargs = {"model": model, "contents": prompt}
            if request_config is not None:
                kwargs["config"] = request_config
            response = client.models.generate_content(**kwargs)
            if response.text:
                LAST_GEMINI_MODEL = model
                return response.text.strip()
            LAST_GEMINI_ERROR = f"Gemini no devolvio texto con el modelo `{model}`."
            return None
        except Exception as exc:
            LAST_GEMINI_ERROR = _mensaje_error_gemini(exc, model)
            if _is_gemini_fallback_error(exc):
                logger.warning("Gemini no disponible para %s. Probando fallback si existe.", model)
                continue
            logger.warning("Error en llamada a Gemini: %s", exc)
            if progress_callback:
                progress_callback(f"[GEMINI ERROR] {type(exc).__name__}: {str(exc)}")
            print(f"[GEMINI ERROR] Tipo: {type(exc).__name__}")
            print(f"[GEMINI ERROR] Mensaje: {str(exc)}")
            print(f"[GEMINI ERROR] Traceback:\n{traceback.format_exc()}")
            return None

    logger.warning("Gemini sin cuota/modelo disponible. Modelos intentados: %s", ", ".join(attempted_models))
    if progress_callback:
        progress_callback("Gemini no respondio con los modelos configurados. Resumen no disponible.")
    return None


def _parsear_json_ia(raw: str) -> dict:
    """
    Extrae el primer bloque JSON de la respuesta del LLM.
    Fallback: resumen=raw.
    """
    if not raw:
        return {"resumen": "Resumen no disponible", "sentimiento": "neutral"}
    try:
        # Extraer el primer bloque {...} de la respuesta
        match = re.search(r"\{[^{}]*\}", raw, re.DOTALL)
        if match:
            data = json.loads(match.group())
            resumen = str(data.get("resumen", "")).strip() or "Resumen no disponible"
            return {"resumen": resumen, "sentimiento": "neutral"}
    except (json.JSONDecodeError, AttributeError):
        pass
    return {"resumen": raw[:400] if raw else "Resumen no disponible", "sentimiento": "neutral"}


# ===========================================================================
# MacroResumen Ejecutivo Diario
# ===========================================================================

def _serializar_global_item(item: GlobalNewsItem) -> dict[str, Any]:
    return {
        "title": item.title,
        "source": item.source,
        "url": item.url,
        "published_at": item.published_at,
        "excerpt": item.excerpt,
        "category": item.category,
        "score": item.score,
    }


def _score_local_signal(item: dict[str, Any]) -> float:
    for key in ("selected_score", "Selected Score", "score", "Score", "stars", "points", "ranking"):
        value = item.get(key)
        if value is None:
            continue
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            continue
        return -numeric if key == "ranking" else numeric
    return 0.0


def _payload_signature(payload: dict[str, Any]) -> str:
    records = payload.get("source_records", [])
    keys = [
        f"{record.get('url', '')}|{record.get('score', '')}|{record.get('score_version', '')}"
        for record in records
        if record.get("url")
    ]
    return hashlib.sha256("\n".join(sorted(keys)).encode("utf-8")).hexdigest()


def _macro_cache_matches(existing: MacroResumen, signature: str, language: str | None = None) -> bool:
    lang = normalize_language(language)
    model = getattr(existing, "modelo_en", None) if lang == "en" else getattr(existing, "modelo", None)
    brief_json = getattr(existing, "brief_json_en", None) if lang == "en" else getattr(existing, "brief_json", None)
    if model != GEMINI_MODEL or not brief_json:
        return False
    try:
        brief = json.loads(brief_json)
    except (TypeError, json.JSONDecodeError):
        return False
    return (
        brief.get("source_signature") == signature
        and brief.get("score_version") == SCORE_VERSION
    )


def build_hybrid_brief_payload(
    global_items: list[GlobalNewsItem | None],
    local_items: list[dict[str, Any]],
    fecha,
) -> dict[str, Any]:
    """Construye un paquete compacto y verificable para el brief hibrido."""
    max_total = 15
    clean_global = [item for item in global_items if item is not None]
    clean_global.sort(key=lambda item: item.score, reverse=True)
    global_payload = [_serializar_global_item(item) for item in clean_global[:8]]
    seen_urls = {item["url"].rstrip("/").lower() for item in global_payload if item.get("url")}

    clean_local = sorted(local_items, key=_score_local_signal, reverse=True)
    local_payload = []
    for item in clean_local:
        if len(global_payload) + len(local_payload) >= max_total:
            break
        url = str(item.get("url") or item.get("URL") or "")
        url_key = url.rstrip("/").lower()
        if url_key and url_key in seen_urls:
            continue
        seen_urls.add(url_key)
        local_payload.append({
            "title": str(item.get("title") or item.get("titulo") or item.get("Título") or "")[:240],
            "source": str(item.get("source") or item.get("fuente") or item.get("Fuente") or ""),
            "url": url,
            "summary": str(item.get("summary") or item.get("resumen") or item.get("Resumen IA") or "")[:500],
            "area": str(item.get("area") or item.get("Área") or ""),
            "score": round(_score_local_signal(item), 1),
            "tags": item.get("tags") or item.get("Tags") or [],
            "selection_reason": str(item.get("selection_reason") or item.get("Motivo seleccion") or ""),
            "score_version": str(item.get("score_version") or SCORE_VERSION),
        })

    source_records = []
    for item in global_payload + local_payload:
        if item.get("url"):
            source_records.append({
                "name": item["source"],
                "url": item["url"],
                "title": item["title"],
                "score": item.get("score", 0),
                "score_version": item.get("score_version", SCORE_VERSION),
            })

    return {
        "date": fecha.isoformat() if hasattr(fecha, "isoformat") else str(fecha),
        "global_news": global_payload,
        "developer_signals": local_payload,
        "source_records": source_records,
    }


def _extraer_json(raw: str) -> dict[str, Any] | None:
    cleaned = (raw or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            return json.loads(cleaned[start:end + 1])
        except json.JSONDecodeError:
            return None


def _parsear_brief_json(raw: str, source_records: list[dict[str, str]]) -> dict[str, Any] | None:
    data = _extraer_json(raw)
    if not isinstance(data, dict):
        return None

    allowed_urls = {str(record.get("url", "")).strip() for record in source_records}
    normalized_items = []
    for item in data.get("items", []):
        if not isinstance(item, dict):
            continue
        sources = []
        for source in item.get("sources", []):
            if not isinstance(source, dict):
                continue
            url = str(source.get("url", "")).strip()
            if url in allowed_urls:
                sources.append({"name": str(source.get("name") or "Fuente"), "url": url})
        normalized_items.append({
            "title": str(item.get("title", "")).strip(),
            "summary": str(item.get("summary", "")).strip(),
            "why_it_matters": str(item.get("why_it_matters", "")).strip(),
            "category": str(item.get("category", "IT")).strip() or "IT",
            "sources": sources,
        })

    return {
        "intro": str(data.get("intro", "")).strip(),
        "items": normalized_items,
        "trend_reading": str(data.get("trend_reading", "")).strip(),
        "source_records": source_records,
    }


def _brief_json_to_text(brief: dict[str, Any], language: str | None = None) -> str:
    lang = normalize_language(language)
    lines = []
    intro = str(brief.get("intro") or "").strip()
    if intro:
        lines.append(intro)
    for idx, item in enumerate(brief.get("items", []), start=1):
        title = str(item.get("title") or "").strip()
        summary = str(item.get("summary") or "").strip()
        why = str(item.get("why_it_matters") or "").strip()
        if title:
            lines.append(f"{idx}. {title}")
        if summary:
            lines.append(summary)
        if why:
            label = "Why it matters" if lang == "en" else "Por que importa"
            lines.append(f"{label}: {why}")
    trend = str(brief.get("trend_reading") or "").strip()
    if trend:
        label = "Trend reading" if lang == "en" else "Lectura de tendencias"
        lines.append(f"{label}: {trend}")
    fallback = "Summary unavailable" if lang == "en" else "Resumen no disponible"
    return "\n\n".join(lines).strip() or fallback


def _persistir_macro_resumen(
    fecha,
    texto: str,
    n_noticias: int,
    n_clusters: int,
    modelo: str,
    brief_json: str | None = None,
    language: str | None = None,
) -> None:
    """Upsert del MacroResumen del día en DB."""
    lang = normalize_language(language)
    with get_session() as session:
        existente = session.query(MacroResumen).filter(MacroResumen.fecha == fecha).first()
        if existente:
            existente.n_noticias = n_noticias
            existente.n_clusters = n_clusters
            if lang == "en":
                existente.texto_en = texto
                existente.modelo_en = modelo
                existente.brief_json_en = brief_json
                existente.fecha_generacion_en = datetime.now()  # timestamp local para display
            else:
                existente.texto = texto
                existente.modelo = modelo
                existente.brief_json = brief_json
                existente.fecha_generacion = datetime.now()  # timestamp local para display
        else:
            data = {
                "fecha": fecha,
                "texto": texto if lang == "es" else "Resumen no disponible",
                "n_noticias": n_noticias,
                "n_clusters": n_clusters,
                "modelo": modelo if lang == "es" else None,
                "brief_json": brief_json if lang == "es" else None,
                "fecha_generacion": datetime.now(),
            }
            if lang == "en":
                data.update({
                    "texto_en": texto,
                    "modelo_en": modelo,
                    "brief_json_en": brief_json,
                    "fecha_generacion_en": datetime.now(),
                })
            session.add(MacroResumen(
                **data,
            ))


def generar_macro_resumen_dia(
    config: dict,
    progress_callback: Callable[[str], None] = None,
    language: str | None = None,
) -> dict[str, Any]:
    """Genera el MacroResumen del día leyendo noticias directamente (sin clusters)."""
    lang = normalize_language(language)
    if progress_callback:
        progress_callback("Evaluando generación de MacroResumen del día...")

    hoy = datetime.now().date()
    FALLBACK_BAJO_VOLUMEN = (
        "Low update volume in the market today."
        if lang == "en"
        else "Bajo volumen de actualizaciones en el mercado hoy."
    )

    # Idempotencia
    with get_session() as session:
        existente = session.query(MacroResumen).filter(MacroResumen.fecha == hoy).first()
        existing_ready = None
        if existente:
            existing_model = existente.modelo_en if lang == "en" else existente.modelo
            existing_text = existente.texto_en if lang == "en" else existente.texto
            if existing_model in {"fallback", "gemini_error"}:
                logger.info("MacroResumen para %s es %s. Se regenerará.", hoy, existente.modelo)
                if lang == "es":
                    session.delete(existente)
                    session.commit()
                else:
                    existente.texto_en = None
                    existente.brief_json_en = None
                    existente.modelo_en = None
                    existente.fecha_generacion_en = None
            else:
                logger.info("MacroResumen para %s ya existe. Se omite generación.", hoy)
                if existing_text:
                    existing_ready = existente

        # Leer noticias directamente — NO clusters
        cutoff = datetime.combine(hoy, datetime.min.time())
        noticias = (
            session.query(Noticia)
            .filter(Noticia.fecha_ingesta >= cutoff)
            .order_by(Noticia.selected_score.desc(), Noticia.fecha_ingesta.desc())
            .limit(50)  # top 50 más relevantes del día
            .all()
        )
        n_noticias_hoy = len(noticias)

        if progress_callback:
            progress_callback("Buscando noticias globales IT verificables...")

        try:
            global_items = fetch_global_news(max_items=10)
        except Exception as exc:
            logger.warning("No se pudieron obtener noticias globales: %s", exc)
            global_items = []

        if n_noticias_hoy < 3 and not global_items:
            _persistir_macro_resumen(
                fecha=hoy,
                texto=FALLBACK_BAJO_VOLUMEN,
                n_noticias=n_noticias_hoy,
                n_clusters=0,
                modelo="fallback",
                language=lang,
            )
            return {"macro_resumen_generado": True, "texto": FALLBACK_BAJO_VOLUMEN, "uso_api": False}

        local_signals = []
        for n in noticias:
            local_signals.append({
                "title": n.titulo,
                "source": n.fuente,
                "url": n.url,
                "summary": n.resumen_ia if n.resumen_ia != "Resumen no disponible" else n.descripcion_original,
                "area": n.area_matcheada,
                "selected_score": getattr(n, "selected_score", None),
                "score": getattr(n, "selected_score", None) or n.score or n.ranking or 0,
                "tags": json.loads(n.tags_json or "[]") if getattr(n, "tags_json", None) else [],
                "selection_reason": getattr(n, "selection_reason", None) or "",
                "score_version": getattr(n, "score_version", None) or SCORE_VERSION,
            })

        payload = build_hybrid_brief_payload(global_items, local_signals, hoy)
        source_signature = _payload_signature(payload)
        if existing_ready and _macro_cache_matches(existing_ready, source_signature, lang):
            logger.info("MacroResumen para %s ya existe con la misma seleccion. Se omite Gemini.", hoy)
            existing_text = existing_ready.texto_en if lang == "en" else existing_ready.texto
            return {"macro_resumen_generado": False, "texto": existing_text, "uso_api": False}
        payload_json = json.dumps(payload, ensure_ascii=False, indent=2)

        if lang == "en":
            prompt = f"""You are a senior IT news editor.
Write an executive brief in English for {payload["date"]}.
Use only the provided JSON evidence. Do not invent facts or URLs.

EVIDENCE:
{payload_json}

Return only valid JSON with this shape:
{{
  "intro": "short paragraph about the day's central theme",
  "items": [
    {{
      "title": "clear title",
      "summary": "2 or 3 sentences in English",
      "why_it_matters": "1 sentence about impact",
      "category": "AI | Cybersecurity | Developer Tools | Infrastructure | Regulation | IT",
      "sources": [{{"name": "Reuters", "url": "exact URL included in source_records"}}]
    }}
  ],
  "trend_reading": "3 executive conclusions in one paragraph"
}}

Rules:
- Include 5 to 8 items if there is enough evidence.
- At least 3 items must come from global_news when available.
- Sources can only use URLs present in source_records.
- Use natural English and an executive tone.
- Do not use markdown inside the JSON."""
        else:
            prompt = f"""Sos un editor senior de noticias IT.
Escribi un brief ejecutivo en espanol para la fecha {payload["date"]}.
Usa exclusivamente la evidencia JSON provista. No inventes hechos ni URLs.

EVIDENCIA:
{payload_json}

Devuelve exclusivamente JSON valido con esta forma:
{{
  "intro": "parrafo breve sobre la linea central del dia",
  "items": [
    {{
      "title": "titulo claro",
      "summary": "2 o 3 frases en espanol",
      "why_it_matters": "1 frase sobre impacto",
      "category": "AI | Cybersecurity | Developer Tools | Infrastructure | Regulation | IT",
      "sources": [{{"name": "Reuters", "url": "URL exacta incluida en source_records"}}]
    }}
  ],
  "trend_reading": "3 conclusiones ejecutivas en un parrafo"
}}

Reglas:
- Inclui entre 5 y 8 items si hay evidencia suficiente.
- Al menos 3 items deben venir de global_news cuando existan.
- Las sources solo pueden usar URLs presentes en source_records.
- Usa espanol natural y tono ejecutivo.
- No uses markdown dentro del JSON."""

        texto = None
        modelo_usado = "fallback"
        brief_json = None

        if progress_callback:
            progress_callback("Redactando brief hibrido con Gemini...")

        raw = _llamar_gemini(prompt, progress_callback)
        brief_data = _parsear_brief_json(raw or "", payload.get("source_records", []))
        if brief_data:
            brief_data["source_signature"] = source_signature
            brief_data["score_version"] = SCORE_VERSION
            texto = _brief_json_to_text(brief_data, lang)
            brief_json = json.dumps(brief_data, ensure_ascii=False)
            modelo_usado = _gemini_model_usado()
            logger.info(
                "MacroResumen hibrido generado con Gemini (%d locales, %d globales).",
                n_noticias_hoy,
                len(global_items),
            )
        elif raw:
            texto = raw
            modelo_usado = _gemini_model_usado()
            logger.info("MacroResumen generado con Gemini (%d noticias).", n_noticias_hoy)
        else:
            texto = LAST_GEMINI_ERROR or (
                "Gemini could not generate the daily brief. Check quota, key, or configured model."
                if lang == "en"
                else "Gemini no pudo generar el brief del dia. Revisa cuota, clave o modelo configurado."
            )
            modelo_usado = "gemini_error"
            logger.warning("Gemini no disponible. Se guarda estado de error del brief: %s", texto)

        _persistir_macro_resumen(
            fecha=hoy,
            texto=texto,
            n_noticias=n_noticias_hoy,
            n_clusters=0,
            modelo=modelo_usado,
            brief_json=brief_json,
            language=lang,
        )
        return {"macro_resumen_generado": True, "texto": texto, "uso_api": modelo_usado != "gemini_error"}

        if n_noticias_hoy < 3:
            _persistir_macro_resumen(fecha=hoy, texto=FALLBACK_BAJO_VOLUMEN, n_noticias=n_noticias_hoy, n_clusters=0, modelo="fallback")
            return {"macro_resumen_generado": True, "texto": FALLBACK_BAJO_VOLUMEN, "uso_api": False}

        # Construir contexto para Gemini
        contexto_items = []
        for n in noticias:
            item = f"- {n.titulo}"
            if n.descripcion_original:
                item += f": {n.descripcion_original[:150]}"
            if n.area_matcheada:
                item += f" [{n.area_matcheada}]"
            contexto_items.append(item)
        
        contexto = "\n".join(contexto_items)
        
        prompt = f"""Eres un analista de tendencias tecnológicas. 
Basándote en las siguientes {n_noticias_hoy} noticias y repositorios trending del día, 
genera un resumen ejecutivo en español de 3-4 oraciones que identifique:
1. Las tendencias dominantes del día
2. Tecnologías o proyectos clave que emergen
3. Implicaciones estratégicas para equipos de tecnología

Noticias del día:
{contexto}

Responde SOLO con el resumen, sin títulos ni bullet points."""

        texto = None
        modelo_usado = "fallback"

        if progress_callback:
            progress_callback("Redactando MacroResumen con Gemini...")

        # Intento Gemini (primario)
        texto = _llamar_gemini(prompt, progress_callback)
        if texto:
            modelo_usado = _gemini_model_usado()
            logger.info("MacroResumen generado con Gemini (%d noticias).", n_noticias_hoy)
        else:
            texto = FALLBACK_BAJO_VOLUMEN
            logger.warning("Gemini no disponible. Se guarda fallback de bajo volumen.")

        _persistir_macro_resumen(fecha=hoy, texto=texto, n_noticias=n_noticias_hoy, n_clusters=0, modelo=modelo_usado)
        return {"macro_resumen_generado": True, "texto": texto, "uso_api": modelo_usado != "fallback"}


# ===========================================================================
# Enriquecimiento Individual con Gemini
# ===========================================================================

def _generar_resumen_gemini(
    titulo: str,
    progress_callback: Callable[[str], None] = None,
    interactive: bool = False,
    language: str | None = None,
) -> str:
    """Genera resumen via Gemini. Retorna raw JSON string."""
    prompt = build_article_summary_prompt(titulo, language)
    resultado = _llamar_gemini(prompt, progress_callback, interactive)
    return resultado or "Resumen no disponible"


def _worker_enriquecer(
    idx: int, total_candidatas: int, noticia_id: str, titulo: str,
    config: dict,
    progress_callback: Callable[[str], None] = None,
    interactive: bool = False
) -> tuple[str, str, str]:
    """Worker de enriquecimiento con Gemini."""
    if progress_callback:
        progress_callback(f"Generando resumen IA {idx} de {total_candidatas}...")
    logger.info("  Generando resumen para: '%s'", titulo[:60])

    raw = _generar_resumen_gemini(titulo, progress_callback, interactive)
    parsed = _parsear_json_ia(raw)
    return noticia_id, parsed["resumen"], parsed["sentimiento"]



def enriquecer_con_ia(config: dict, max_noticias: int = 10, progress_callback: Callable[[str], None] = None) -> int:
    """
    Selecciona las noticias sin resumen con mayor densidad de keywords
    y las enriquece con resúmenes de Gemini.
    """
    if not GEMINI_AVAILABLE or not GEMINI_API_KEY:
        logger.warning("Gemini no configurado. Enriquecimiento IA omitido.")
        if progress_callback:
            progress_callback("Gemini no configurado. Enriquecimiento IA omitido.")
        return 0

    areas_interes = config.get("areas_interes", {})

    with get_session() as session:
        candidatas = (
            session.query(Noticia)
            .filter(
                (Noticia.resumen_ia == "Resumen no disponible")
                | (Noticia.resumen_ia.is_(None))
            )
            .all()
        )
        # Desacoplar objetos ORM antes de enviarlos a los workers
        lista_candidatas = [{"id": str(n.id), "titulo": str(n.titulo)} for n in candidatas]

    if not lista_candidatas:
        logger.info("Todas las noticias ya tienen resumen de IA.")
        return 0

    priorizadas = sorted(
        lista_candidatas,
        key=lambda n: _calcular_densidad_keywords(n["titulo"], areas_interes),
        reverse=True,
    )[:max_noticias]

    enriquecidas = 0
    total_candidatas = len(priorizadas)

    # Enriquecimiento secuencial con delay fijo de 4s (15 req/min)
    import time
    for idx, noticia_dict in enumerate(priorizadas, 1):
        if progress_callback:
            progress_callback(f"Generando resumen IA {idx}/{total_candidatas}: {noticia_dict['titulo'][:50]}...")
        try:
            n_id, res, sent = _worker_enriquecer(
                idx, total_candidatas, noticia_dict["id"], noticia_dict["titulo"],
                config, progress_callback
            )
            # Persistir inmediatamente (incremental)
            with get_session() as session:
                nd = session.get(Noticia, n_id)
                if nd:
                    nd.resumen_ia = res
                    nd.sentimiento = sent
                session.commit()
            
            if res != "Resumen no disponible":
                enriquecidas += 1
            
            # Dormir para respetar el Free Tier de Gemini (15 rpm)
            time.sleep(4.1)
        except Exception as e:
            logger.error("Error en worker de enriquecimiento: %s", e)

    logger.info(
        "Enriquecimiento IA: %d/%d noticias con resumen.", enriquecidas, len(priorizadas)
    )
    return enriquecidas


def generar_resumen_individual(n_id: str, titulo: str, language: str | None = None) -> dict[str, Any]:
    """Genera un resumen para un único artículo con Gemini y persiste el resultado."""
    lang = normalize_language(language)
    if not GEMINI_AVAILABLE:
        return {
            "ok": False,
            "reason": (
                "Gemini is unavailable. Install the google-genai dependency."
                if lang == "en"
                else "Gemini no está disponible. Instalá la dependencia google-genai."
            ),
        }
    if not GEMINI_API_KEY:
        return {
            "ok": False,
            "reason": (
                "Gemini is not configured. Add GEMINI_API_KEY to .env and restart the app."
                if lang == "en"
                else "Gemini no está configurado. Agregá GEMINI_API_KEY en .env y reiniciá la app."
            ),
        }

    try:
        raw = _generar_resumen_gemini(titulo, progress_callback=None, interactive=True, language=lang)
        parsed = _parsear_json_ia(raw)
        res = parsed["resumen"]

        with get_session() as session:
            nd = session.get(Noticia, n_id)
            if nd:
                if lang == "en":
                    nd.resumen_ia_en = res
                else:
                    nd.resumen_ia = res
            session.commit()

        if res == "Resumen no disponible":
            reason = LAST_GEMINI_ERROR or (
                "Gemini no devolvio un resumen valido. "
                "Revisa la clave, cuota o modelo configurado."
            )
            return {"ok": False, "reason": reason}

        if res == "Resumen no disponible":
            return {
                "ok": False,
                "reason": "Gemini no devolvió un resumen válido. Revisá la clave, cuota o modelo configurado.",
            }
        return {"ok": True, "summary": res, "reason": ""}
    except Exception as e:
        logger.error("Error al generar resumen individual para la noticia %s: %s", n_id, e)
        return {
            "ok": False,
            "reason": (
                "The summary could not be generated with Gemini. Check the configuration and try again."
                if lang == "en"
                else "No se pudo generar el resumen con Gemini. Revisá la configuración y volvé a intentar."
            ),
        }


# ===========================================================================
# Orquestador principal
# ===========================================================================

def ejecutar_procesamiento(progress_callback: Callable[[str], None] = None) -> dict[str, Any]:
    """
    Orquesta el pipeline de procesamiento v2.0:
    1. Tendencias NLP (frecuencia de términos en corpus global)
    2. Clustering diario (Embeddings + NER veto + scoring)
    3. Enriquecimiento IA individual (Top N por densidad de keywords)
    4. MacroResumen ejecutivo del día (Gemini con guardarraíl de volumen)

    Returns:
        dict con métricas de todas las etapas.
    """
    if progress_callback:
        progress_callback("Iniciando procesamiento de datos...")
        
    # Verificación temprana de Gemini
    logger.info("Gemini configurado: %s · modelo=%s", bool(GEMINI_API_KEY), GEMINI_MODEL)
    
    gemini_disponible = _verificar_gemini()
    if not gemini_disponible:
        logger.warning("Gemini no disponible. Se omite enriquecimiento IA y continúa el resto del ETL.")
        
    config = cargar_config_procesador()
    app_cfg = config.get("app", {})
    top_n = int(app_cfg.get("top_tendencias", 10))
    max_ia = int(app_cfg.get("max_noticias_ia", 0))
    areas_interes = config.get("areas_interes", {})

    # Etapa 1: Tendencias
    if progress_callback:
        progress_callback("Calculando tendencias NLP del corpus...")
    tendencias = calcular_tendencias(top_n=top_n)

    # Etapa 2: Clustering diario
    metricas_clustering = clustering_diario(config, progress_callback=progress_callback)

    if progress_callback:
        progress_callback("Calculando score de seleccion sin usar Gemini...")
    try:
        noticias_scored = score_recent_items(config, hours=24)
    except Exception as exc:
        logger.warning("Scoring de seleccion omitido por error: %s", exc)
        noticias_scored = 0

    # Etapa 3: Enriquecimiento IA individual
    if gemini_disponible and max_ia > 0:
        noticias_enriquecidas = enriquecer_con_ia(config, max_noticias=max_ia, progress_callback=progress_callback)
    else:
        noticias_enriquecidas = 0
        if progress_callback:
            if max_ia <= 0:
                progress_callback("Enriquecimiento individual desactivado para proteger cuota Gemini.")
            else:
                progress_callback("Gemini no disponible. Se omite enriquecimiento individual para priorizar el brief.")

    # Etapa 4: MacroResumen del día
    resultado_macro = generar_macro_resumen_dia(config, progress_callback=progress_callback)

    if progress_callback:
        progress_callback("Procesamiento completado.")

    return {
        "top_tendencias":        tendencias,
        "noticias_enriquecidas": noticias_enriquecidas,
        "clusters_generados":    metricas_clustering.get("clusters_generados", 0),
        "noticias_agrupadas":    metricas_clustering.get("noticias_agrupadas", 0),
        "noticias_scored":       noticias_scored,
        "macro_resumen_generado": resultado_macro.get("macro_resumen_generado", False),
        "uso_api_macro":         resultado_macro.get("uso_api", False),
    }


def cargar_config_procesador() -> dict[str, Any]:
    """Carga config.yaml desde la raíz del proyecto."""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
