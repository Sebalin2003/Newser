from __future__ import annotations

import re

STRONG_RELEVANCE_KEYWORDS = (
    "artificial intelligence", "machine learning", "deep learning", "large language model",
    "generative ai", "llm", "gpt", "openai", "gemini", "claude", "copilot",
    "transformer", "inference", "training", "agentic", "ai agent", "ai agents",
    "cybersecurity", "ransomware", "data breach", "vulnerability", "malware",
    "phishing", "exploit", "zero-day", "threat actor", "semiconductor",
    "gpu", "nvidia", "amd", "intel", "tsmc", "hbm", "kubernetes", "docker",
    "terraform", "data pipeline", "platform engineering", "compiler", "runtime",
    "sdk", "cli", "framework", "library",
)

WEAK_RELEVANCE_KEYWORDS = (
    "ai", "model", "models", "agent", "agents", "developer", "github",
    "api", "open source", "hardware", "software", "programming", "product",
)

CONSUMER_OFF_TOPIC_KEYWORDS = (
    "airpods", "headphones", "earbuds", "bluetooth", "phone accessory",
    "android app", "ios app", "smartphone", "watch", "fitness tracker",
    "camera app", "wallpaper", "keyboard case",
)


def contains_keyword(text: str, keyword: str) -> bool:
    return bool(re.search(rf"(?<!\w){re.escape(keyword.lower())}(?!\w)", text))


def has_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(contains_keyword(text, keyword) for keyword in keywords)


def strong_signal_count(text: str) -> int:
    return sum(1 for keyword in STRONG_RELEVANCE_KEYWORDS if contains_keyword(text, keyword))


def weak_signal_count(text: str) -> int:
    return sum(1 for keyword in WEAK_RELEVANCE_KEYWORDS if contains_keyword(text, keyword))


def is_consumer_off_topic(text: str) -> bool:
    return has_any(text, CONSUMER_OFF_TOPIC_KEYWORDS)


def classify_relevance(titulo: str, descripcion: str, areas_interes: dict) -> tuple[bool, str]:
    text = f"{titulo} {descripcion}".lower()
    off_topic = is_consumer_off_topic(text)
    for area, keywords in areas_interes.items():
        matches = [kw.lower() for kw in keywords if contains_keyword(text, kw)]
        if not matches:
            continue
        strong_matches = [kw for kw in matches if kw not in WEAK_RELEVANCE_KEYWORDS]
        if strong_matches:
            return True, area
        if len(matches) >= 2 and not off_topic:
            return True, area
    return False, ""
