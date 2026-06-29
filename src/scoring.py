from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

from .relevance import contains_keyword, is_consumer_off_topic, strong_signal_count, weak_signal_count

SCORE_VERSION = "selected-v2"

WEIGHTS = {
    "topic_relevance": 0.28,
    "source_credibility": 0.15,
    "freshness": 0.10,
    "popularity": 0.08,
    "technical_importance": 0.10,
    "coverage_overlap": 0.04,
    "relevance_quality": 0.25,
}

AREA_SCORES = {
    "ai_agents": 94,
    "cybersecurity": 86,
    "developer_tools": 78,
    "infrastructure_cloud": 76,
    "chips_hardware": 72,
    "general": 35,
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
    "Startup/Product": (
        "startup", "funding", "venture capital", "ipo", "acquisition",
        "product", "launch", "valuation", "fintech",
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
    components: dict[str, Any]
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


def _core_area(area: str | None) -> str:
    return AREA_COMPATIBILITY.get(str(area or "general"), "general")


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
        if any(contains_keyword(text, keyword) for keyword in keywords):
            tags.append(tag)

    area_tags = {
        "ai_agents": "AI",
        "cybersecurity": "Cybersecurity",
        "developer_tools": "Developer Tools",
        "infrastructure_cloud": "Cloud",
        "chips_hardware": "Semiconductors",
    }
    area_tag = area_tags.get(_core_area(area))
    if area_tag == "AI" and "AI" not in tags and strong_signal_count(text) == 0:
        area_tag = None
    if area_tag and area_tag not in tags:
        tags.insert(0, area_tag)
    return tags[:5]


def _topic_score(text: str, area: str | None, tags: list[str]) -> float:
    score = float(AREA_SCORES.get(_core_area(area), 35))
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
        if contains_keyword(text, keyword)
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


def _dynamic_keyword_matches(text: str, dynamic_keywords: list[str] | None) -> list[str]:
    if not dynamic_keywords:
        return []
    return [term for term in dynamic_keywords if contains_keyword(text, term)]


def _dynamic_keyword_boost(matches: list[str]) -> float:
    if not matches:
        return 0.0
    return min(12.0, 4.0 + len(matches[:4]) * 2.0)


def _relevance_quality_score(text: str, tags: list[str], area: str | None) -> float:
    strong = strong_signal_count(text)
    weak = weak_signal_count(text)
    score = 20.0 + min(strong, 5) * 15 + min(weak, 4) * 4
    if _core_area(area) in {"ai_agents", "cybersecurity", "infrastructure_cloud", "chips_hardware"} and strong:
        score += 10
    if "Developer Tools" in tags and strong:
        score += 6
    if is_consumer_off_topic(text):
        score -= 35
    return max(0.0, min(100.0, score))


def _apply_relevance_cap(score: float, components: dict[str, float], text: str) -> float:
    relevance = components["relevance_quality"]
    if is_consumer_off_topic(text) and strong_signal_count(text) == 0:
        return min(score, 48.0)
    if relevance < 35:
        return min(score, 58.0)
    if relevance < 55:
        return min(score, 72.0)
    return score


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
    dynamic_keywords: list[str] | None = None,
) -> ScoringResult:
    config = config or {}
    now = now or datetime.now(timezone.utc)
    text = _text_for(item)
    area = _get(item, "area_matcheada") or _get(item, "area")
    source = str(_get(item, "fuente") or _get(item, "source") or "")
    tags = _tags_for(text, area)
    dynamic_matches = _dynamic_keyword_matches(text, dynamic_keywords)
    dynamic_boost = _dynamic_keyword_boost(dynamic_matches)

    components = {
        "topic_relevance": min(100.0, _topic_score(text, area, tags) + dynamic_boost),
        "source_credibility": _source_score(source, config),
        "freshness": _freshness_score(item, now),
        "popularity": _popularity_score(item),
        "technical_importance": min(100.0, _importance_score(text, tags) + dynamic_boost),
        "coverage_overlap": _coverage_score(item, coverage),
        "relevance_quality": min(100.0, _relevance_quality_score(text, tags, area) + dynamic_boost),
        "dynamic_keyword_boost": dynamic_boost,
        "dynamic_keyword_matches": dynamic_matches,
    }
    selected_score = round(sum(components[key] * weight for key, weight in WEIGHTS.items()), 1)
    selected_score = _apply_relevance_cap(selected_score, components, text)
    return ScoringResult(
        selected_score=min(100.0, selected_score),
        components={key: round(value, 1) if isinstance(value, (int, float)) else value for key, value in components.items()},
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

    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(hours=hours)).replace(tzinfo=None)
    updated = 0
    with get_session() as session:
        try:
            from .dynamic_keywords import active_terms

            dynamic_keywords = active_terms()
        except Exception:
            dynamic_keywords = []
        items = (
            session.query(Noticia)
            .filter(Noticia.fecha_ingesta >= cutoff)
            .all()
        )
        coverage = build_coverage_context(items)
        for item in items:
            result = calculate_item_score(item, config=config, now=now, coverage=coverage, dynamic_keywords=dynamic_keywords)
            item.selected_score = result.selected_score
            item.score_components_json = json.dumps(result.components, ensure_ascii=False)
            item.tags_json = json.dumps(result.tags, ensure_ascii=False)
            item.selection_reason = result.reason
            item.scored_at = datetime.now()
            item.score_version = SCORE_VERSION
            updated += 1
    return updated
