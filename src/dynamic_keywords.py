from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Iterable

from .database import DynamicKeyword, Noticia, get_session
from .relevance import (
    CONSUMER_OFF_TOPIC_KEYWORDS,
    STRONG_RELEVANCE_KEYWORDS,
    WEAK_RELEVANCE_KEYWORDS,
    contains_keyword,
    is_consumer_off_topic,
)

STOPWORDS = {
    "about", "after", "again", "also", "and", "are", "because", "been", "but",
    "can", "from", "has", "have", "into", "more", "new", "not", "now", "that",
    "the", "their", "this", "through", "use", "using", "when", "with", "your",
    "para", "por", "con", "los", "las", "una", "uno", "del", "que", "como",
}

CURATED_TERMS = {term.lower() for term in STRONG_RELEVANCE_KEYWORDS + WEAK_RELEVANCE_KEYWORDS}
OFF_TOPIC_TERMS = {term.lower() for term in CONSUMER_OFF_TOPIC_KEYWORDS}


def _tokenize(text: str) -> list[str]:
    cleaned = re.sub(r"[^a-z0-9+#.\-\s]", " ", text.lower())
    tokens = [token.strip("-_.") for token in cleaned.split()]
    return [token for token in tokens if len(token) >= 3 and token not in STOPWORDS]


def _ngrams(tokens: list[str]) -> Iterable[str]:
    for size in (1, 2, 3):
        for index in range(0, len(tokens) - size + 1):
            gram = " ".join(tokens[index:index + size])
            if any(part in STOPWORDS for part in gram.split()):
                continue
            yield gram


def _candidate_terms(title: str, description: str) -> set[str]:
    return set(_ngrams(_tokenize(f"{title} {description}")))


def _is_allowed_term(term: str) -> bool:
    if term in CURATED_TERMS or term in OFF_TOPIC_TERMS:
        return False
    if is_consumer_off_topic(term):
        return False
    if len(term) < 4 and " " not in term:
        return False
    return True


def discover_dynamic_keywords(days_recent: int = 2, baseline_days: int = 7, limit: int = 25) -> list[dict]:
    now = datetime.now(timezone.utc)
    recent_cutoff = (now - timedelta(days=days_recent)).replace(tzinfo=None)
    baseline_cutoff = (now - timedelta(days=baseline_days + days_recent)).replace(tzinfo=None)
    previous_cutoff = (now - timedelta(days=days_recent)).replace(tzinfo=None)

    with get_session() as session:
        rows = (
            session.query(Noticia)
            .filter(Noticia.fecha_ingesta >= baseline_cutoff)
            .all()
        )

        recent_frequency: Counter[str] = Counter()
        baseline_frequency: Counter[str] = Counter()
        sources: dict[str, set[str]] = defaultdict(set)
        first_seen: dict[str, datetime] = {}
        last_seen: dict[str, datetime] = {}

        for item in rows:
            terms = {term for term in _candidate_terms(item.titulo or "", item.descripcion_original or "") if _is_allowed_term(term)}
            if not terms:
                continue
            if item.fecha_ingesta and item.fecha_ingesta >= previous_cutoff:
                for term in terms:
                    recent_frequency[term] += 1
                    sources[term].add(item.fuente or "")
                    first_seen[term] = min(first_seen.get(term, item.fecha_ingesta), item.fecha_ingesta)
                    last_seen[term] = max(last_seen.get(term, item.fecha_ingesta), item.fecha_ingesta)
            else:
                for term in terms:
                    baseline_frequency[term] += 1

        promoted: list[dict] = []
        for term, frequency in recent_frequency.items():
            source_count = len({source for source in sources[term] if source})
            baseline = baseline_frequency.get(term, 0)
            momentum = round(float(frequency + source_count * 1.5) / max(1.0, baseline + 1.0), 3)
            if frequency < 3 and source_count < 2:
                continue
            if momentum <= 1.0:
                continue
            promoted.append({
                "term": term,
                "frequency": frequency,
                "source_count": source_count,
                "momentum_score": momentum,
                "first_seen_at": first_seen.get(term),
                "last_seen_at": last_seen.get(term),
            })

        promoted.sort(key=lambda item: (item["momentum_score"], item["source_count"], item["frequency"]), reverse=True)
        promoted = promoted[:limit]
        active_terms = {item["term"] for item in promoted}

        session.query(DynamicKeyword).update({"is_active": 0})
        for item in promoted:
            record = session.get(DynamicKeyword, item["term"])
            if record is None:
                record = DynamicKeyword(term=item["term"])
                session.add(record)
            record.frequency = int(item["frequency"])
            record.source_count = int(item["source_count"])
            record.momentum_score = float(item["momentum_score"])
            record.is_active = 1
            record.first_seen_at = item["first_seen_at"]
            record.last_seen_at = item["last_seen_at"]
            record.updated_at = datetime.now()

        if not active_terms:
            return []
        return [serialize_dynamic_keyword(item) for item in session.query(DynamicKeyword).filter(DynamicKeyword.term.in_(active_terms)).all()]


def get_active_dynamic_keywords(limit: int = 50) -> list[dict]:
    with get_session() as session:
        rows = (
            session.query(DynamicKeyword)
            .filter(DynamicKeyword.is_active == 1)
            .order_by(DynamicKeyword.momentum_score.desc(), DynamicKeyword.frequency.desc())
            .limit(limit)
            .all()
        )
        return [serialize_dynamic_keyword(row) for row in rows]


def active_terms(limit: int = 50) -> list[str]:
    return [item["term"] for item in get_active_dynamic_keywords(limit=limit)]


def matched_terms(text: str, terms: list[str]) -> list[str]:
    lowered = text.lower()
    return [term for term in terms if contains_keyword(lowered, term)]


def serialize_dynamic_keyword(item) -> dict:
    if isinstance(item, dict):
        payload = item
    else:
        payload = {
            "term": item.term,
            "frequency": item.frequency,
            "source_count": item.source_count,
            "momentum_score": item.momentum_score,
            "first_seen_at": item.first_seen_at,
            "last_seen_at": item.last_seen_at,
            "updated_at": item.updated_at,
        }
    return {
        "term": payload["term"],
        "frequency": int(payload.get("frequency") or 0),
        "source_count": int(payload.get("source_count") or 0),
        "momentum_score": float(payload.get("momentum_score") or 0),
        "first_seen_at": _iso(payload.get("first_seen_at")),
        "last_seen_at": _iso(payload.get("last_seen_at")),
        "updated_at": _iso(payload.get("updated_at")),
    }


def _iso(value) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    return None
