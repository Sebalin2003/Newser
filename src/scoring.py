from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

SCORE_VERSION = "selected-v1"

WEIGHTS = {
    "topic_relevance": 0.35,
    "source_credibility": 0.20,
    "freshness": 0.15,
    "popularity": 0.15,
    "technical_importance": 0.10,
    "coverage_overlap": 0.05,
}

AREA_SCORES = {
    "inteligencia_artificial": 92,
    "ciberseguridad": 86,
    "arquitectura_software": 78,
    "cloud_computing": 76,
    "data_engineering": 74,
    "semiconductores": 70,
    "ciencias_computacion": 66,
    "startups_tecnologia": 48,
    "general": 35,
}

SOURCE_CREDIBILITY = {
    "OpenAI Blog": 98,
    "GitHub Blog": 94,
    "Reuters": 92,
    "Hacker News": 86,
    "GitHub Trending": 84,
}

TAG_KEYWORDS = {
    "AI": (
        "ai", "artificial intelligence", "machine learning", "deep learning",
        "llm", "model", "models", "agent", "agents", "openai", "gemini",
        "claude", "copilot", "transformer", "inference", "training",
    ),
    "Cybersecurity": (
        "security", "cyber", "hack", "breach", "vulnerability", "malware",
        "phishing", "ransomware", "exploit", "zero-day", "firewall", "vpn",
    ),
    "Developer Tools": (
        "developer", "programming", "github", "copilot", "ide", "sdk",
        "api", "framework", "library", "cli", "compiler", "runtime",
    ),
    "Cloud": (
        "cloud", "aws", "azure", "google cloud", "kubernetes", "docker",
        "serverless", "terraform", "infrastructure", "platform engineering",
    ),
    "Data": (
        "data", "pipeline", "kafka", "spark", "warehouse", "lakehouse",
        "database", "analytics", "etl",
    ),
    "Semiconductors": (
        "chip", "chips", "semiconductor", "gpu", "nvidia", "amd", "intel",
        "memory", "dram", "hbm", "tsmc",
    ),
    "Regulation": (
        "regulation", "regulator", "law", "export control", "blacklist",
        "entity list", "eu", "government", "antitrust",
    ),
}

IMPORTANCE_KEYWORDS = (
    "launch", "release", "announces", "introduces", "benchmark", "frontier",
    "outage", "breach", "attack", "vulnerability", "zero-day", "export control",
    "prices", "shortage", "open source", "model", "agent", "copilot",
)


@dataclass(frozen=True)
class ScoringResult:
    selected_score: float
    components: dict[str, float]
    tags: list[str]
    reason: str


def _get(item: Any, name: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def _text_for(item: Any) -> str:
    return " ".join(
        str(value or "")
        for value in (
            _get(item, "titulo") or _get(item, "title"),
            _get(item, "descripcion_original") or _get(item, "summary") or _get(item, "excerpt"),
            _get(item, "area_matcheada") or _get(item, "area"),
        )
    ).lower()


def _parse_period_stars(title: str) -> int:
    match = re.search(r"\(\+(\d[\d,]*)", title or "")
    if not match:
        return 0
    try:
        return int(match.group(1).replace(",", ""))
    except ValueError:
        return 0


def _age_hours(item: Any, now: datetime) -> float:
    dt = _get(item, "fecha_publicacion") or _get(item, "published_at") or _get(item, "fecha_ingesta")
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except ValueError:
            return 24.0
    if not isinstance(dt, datetime):
        return 24.0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    now_utc = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    return max(0.0, (now_utc.astimezone(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() / 3600)


def _freshness_score(item: Any, now: datetime) -> float:
    hours = _age_hours(item, now)
    if hours <= 6:
        return 100.0
    if hours <= 24:
        return 85.0 - ((hours - 6) * 1.8)
    return max(0.0, 52.0 * math.exp(-0.035 * (hours - 24)))


def _source_score(source: str, config: dict[str, Any]) -> float:
    if source in SOURCE_CREDIBILITY:
        return float(SOURCE_CREDIBILITY[source])
    for cfg in config.get("fuentes", []):
        if cfg.get("nombre") == source:
            return float(cfg.get("autoridad", 0.65)) * 100
    return 55.0


def _tags_for(text: str, area: str | None) -> list[str]:
    tags: list[str] = []
    for tag, keywords in TAG_KEYWORDS.items():
        if any(re.search(rf"\b{re.escape(keyword)}\b", text) for keyword in keywords):
            tags.append(tag)

    area_tags = {
        "inteligencia_artificial": "AI",
        "ciberseguridad": "Cybersecurity",
        "arquitectura_software": "Developer Tools",
        "cloud_computing": "Cloud",
        "data_engineering": "Data",
        "semiconductores": "Semiconductors",
    }
    area_tag = area_tags.get(area or "")
    if area_tag and area_tag not in tags:
        tags.insert(0, area_tag)
    return tags[:5]


def _topic_score(text: str, area: str | None, tags: list[str]) -> float:
    score = float(AREA_SCORES.get(area or "general", 35))
    if "AI" in tags:
        score += 12
    if "Cybersecurity" in tags:
        score += 8
    if "Developer Tools" in tags:
        score += 5
    keyword_hits = sum(
        1
        for keywords in TAG_KEYWORDS.values()
        for keyword in keywords
        if re.search(rf"\b{re.escape(keyword)}\b", text)
    )
    return min(100.0, score + min(keyword_hits, 6) * 2)


def _popularity_score(item: Any) -> float:
    source = str(_get(item, "fuente") or _get(item, "source") or "")
    source_score = _get(item, "score")
    comments = _get(item, "num_comentarios") or _get(item, "comments") or 0
    ranking = _get(item, "ranking")
    title = str(_get(item, "titulo") or _get(item, "title") or "")

    if source == "Hacker News":
        points = int(source_score or 0)
        return min(100.0, math.log1p(points) * 14 + math.log1p(int(comments or 0)) * 8)
    if source == "GitHub Trending":
        stars = _parse_period_stars(title)
        stars_part = min(100.0, math.log1p(stars) * 13) if stars else 0.0
        try:
            rank_part = max(0.0, 100.0 - (int(ranking) - 1) * 4)
        except (TypeError, ValueError):
            rank_part = 0.0
        return max(stars_part, rank_part)
    try:
        return min(70.0, math.log1p(int(source_score or 0)) * 22)
    except (TypeError, ValueError):
        return 0.0


def _importance_score(text: str, tags: list[str]) -> float:
    score = 25.0
    if "AI" in tags:
        score += 25
    if "Cybersecurity" in tags:
        score += 20
    if "Semiconductors" in tags:
        score += 12
    hits = sum(1 for keyword in IMPORTANCE_KEYWORDS if keyword in text)
    return min(100.0, score + hits * 9)


def _coverage_score(item: Any, coverage: dict[Any, tuple[int, int]] | None) -> float:
    if not coverage:
        return 0.0
    cluster_id = _get(item, "cluster_id")
    key = cluster_id if cluster_id is not None else _canonical_title_key(str(_get(item, "titulo") or ""))
    count, sources = coverage.get(key, (1, 1))
    if count <= 1 and sources <= 1:
        return 0.0
    return min(100.0, 35 + (count - 1) * 18 + (sources - 1) * 22)


def _canonical_title_key(title: str) -> str:
    cleaned = re.sub(r"^\[[^\]]+\]\s*", "", title.lower())
    cleaned = re.sub(r"https?://\S+|[^\w\s]", " ", cleaned)
    tokens = [t for t in cleaned.split() if len(t) > 3][:8]
    return " ".join(tokens)


def calculate_item_score(
    item: Any,
    config: dict[str, Any] | None = None,
    now: datetime | None = None,
    coverage: dict[Any, tuple[int, int]] | None = None,
) -> ScoringResult:
    config = config or {}
    now = now or datetime.now(timezone.utc)
    text = _text_for(item)
    area = _get(item, "area_matcheada") or _get(item, "area")
    source = str(_get(item, "fuente") or _get(item, "source") or "")
    tags = _tags_for(text, area)

    components = {
        "topic_relevance": _topic_score(text, area, tags),
        "source_credibility": _source_score(source, config),
        "freshness": _freshness_score(item, now),
        "popularity": _popularity_score(item),
        "technical_importance": _importance_score(text, tags),
        "coverage_overlap": _coverage_score(item, coverage),
    }
    selected_score = round(sum(components[key] * weight for key, weight in WEIGHTS.items()), 1)
    return ScoringResult(
        selected_score=min(100.0, selected_score),
        components={key: round(value, 1) for key, value in components.items()},
        tags=tags,
        reason=_selection_reason(source, tags, components),
    )


def _selection_reason(source: str, tags: list[str], components: dict[str, float]) -> str:
    reasons: list[str] = []
    if tags:
        main_tag = tags[0]
        if main_tag == "AI":
            reasons.append("alta relevancia en inteligencia artificial")
        else:
            reasons.append(f"relevancia en {main_tag}")
    if components.get("source_credibility", 0) >= 85 and source:
        reasons.append(f"fuente confiable ({source})")
    if components.get("freshness", 0) >= 80:
        reasons.append("publicacion reciente")
    if components.get("popularity", 0) >= 70:
        reasons.append("traccion fuerte en la comunidad")
    if components.get("coverage_overlap", 0) >= 50:
        reasons.append("cobertura coincidente en varias senales")
    if not reasons:
        reasons.append("senal tecnica relevante para el monitoreo")
    return "Seleccionado por " + ", ".join(reasons[:3]) + "."


def build_coverage_context(items: list[Any]) -> dict[Any, tuple[int, int]]:
    grouped: dict[Any, list[Any]] = {}
    for item in items:
        key = item.cluster_id if item.cluster_id is not None else _canonical_title_key(item.titulo or "")
        if not key:
            parsed = urlparse(item.url or "")
            key = parsed.path.rstrip("/") or item.id
        grouped.setdefault(key, []).append(item)
    return {
        key: (len(group), len({item.fuente for item in group}))
        for key, group in grouped.items()
    }


def score_recent_items(config: dict[str, Any], hours: int = 24) -> int:
    from .database import Noticia, get_session

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    now = datetime.now(timezone.utc)
    updated = 0
    with get_session() as session:
        items = (
            session.query(Noticia)
            .filter(Noticia.fecha_ingesta >= cutoff)
            .all()
        )
        coverage = build_coverage_context(items)
        for item in items:
            result = calculate_item_score(item, config=config, now=now, coverage=coverage)
            item.selected_score = result.selected_score
            item.score_components_json = json.dumps(result.components, ensure_ascii=False)
            item.tags_json = json.dumps(result.tags, ensure_ascii=False)
            item.selection_reason = result.reason
            item.scored_at = datetime.now()
            item.score_version = SCORE_VERSION
            updated += 1
    return updated
