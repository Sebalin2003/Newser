from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlparse

import feedparser
import requests

logger = logging.getLogger(__name__)

TRUSTED_SOURCES = {
    "Reuters": ("reuters.com", "www.reuters.com"),
    "GitHub Blog": ("github.blog",),
    "OpenAI Blog": ("openai.com",),
}

FEEDS = [
    ("GitHub Blog", "https://github.blog/feed/"),
    ("OpenAI Blog", "https://openai.com/news/rss.xml"),
]

REUTERS_NEWS_SITEMAP = "https://www.reuters.com/arc/outboundfeeds/news-sitemap/?outputType=xml"

IT_KEYWORDS = (
    "artificial intelligence", "cyber", "security", "hack", "vulnerability",
    "chip", "semiconductor", "memory", "gpu", "cloud", "software", "developer",
    "openai", "github", "anthropic", "deepseek", "apple", "meta", "microsoft",
    "google", "nvidia", "data center", "datacenter", "model",
)


def looks_like_it_story(title: str, url: str) -> bool:
    haystack = f"{title} {url}".lower()
    if "reuters.com/pt/" in haystack:
        return False
    if re.search(r"\bai\b", haystack):
        return True
    return any(keyword in haystack for keyword in IT_KEYWORDS)


@dataclass(frozen=True)
class GlobalNewsItem:
    title: str
    source: str
    url: str
    published_at: str | None
    excerpt: str
    category: str
    score: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _strip_html(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value or "")).strip()


def _parse_date(value: Any) -> str | None:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str) and value.strip():
        raw_value = value.strip()
        try:
            dt = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            try:
                dt = parsedate_to_datetime(raw_value)
            except (TypeError, ValueError):
                return None
    else:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _source_allowed(source: str, url: str) -> bool:
    hosts = TRUSTED_SOURCES.get(source)
    if not hosts:
        return False
    hostname = (urlparse(url).hostname or "").lower()
    return any(hostname == host or hostname.endswith(f".{host}") for host in hosts)


def _classify(title: str, excerpt: str) -> str:
    text = f"{title} {excerpt}".lower()
    if any(term in text for term in ("security", "cyber", "hack", "vulnerability", "vpn", "firewall")):
        return "Cybersecurity"
    if any(term in text for term in ("ai", "artificial intelligence", "model", "llm", "openai", "copilot")):
        return "AI"
    if any(term in text for term in ("chip", "semiconductor", "memory", "gpu", "datacenter", "data center")):
        return "Infrastructure"
    if any(term in text for term in ("developer", "github", "software", "programming")):
        return "Developer Tools"
    return "IT"


def normalize_global_item(
    title: str,
    source: str,
    url: str,
    published_at: Any = None,
    excerpt: str = "",
    category: str = "IT",
    score: int = 0,
) -> GlobalNewsItem | None:
    title = _strip_html(title)
    url = (url or "").strip()
    source = (source or "").strip()
    excerpt = _strip_html(excerpt)

    if not title or not url or not _source_allowed(source, url):
        return None

    clean_category = category if category and category != "IT" else _classify(title, excerpt)
    return GlobalNewsItem(
        title=title[:240],
        source=source,
        url=url,
        published_at=_parse_date(published_at),
        excerpt=excerpt[:500],
        category=clean_category,
        score=int(score or 0),
    )


def dedupe_global_items(items: list[GlobalNewsItem | None]) -> list[GlobalNewsItem]:
    seen: set[str] = set()
    deduped: list[GlobalNewsItem] = []
    for item in sorted((i for i in items if i is not None), key=lambda x: x.score, reverse=True):
        key = item.url.rstrip("/").lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _fetch_reuters_sitemap(max_items: int, timeout: int) -> list[GlobalNewsItem]:
    try:
        response = requests.get(
            REUTERS_NEWS_SITEMAP,
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 DeveloperPulse/2.0"},
        )
        response.raise_for_status()
    except Exception as exc:
        logger.warning("No se pudo leer sitemap Reuters: %s", exc)
        return []

    namespaces = {
        "sm": "http://www.sitemaps.org/schemas/sitemap/0.9",
        "news": "http://www.google.com/schemas/sitemap-news/0.9",
    }
    try:
        root = ET.fromstring(response.text)
    except ET.ParseError as exc:
        logger.warning("Sitemap Reuters invalido: %s", exc)
        return []

    items: list[GlobalNewsItem] = []
    for index, url_node in enumerate(root.findall("sm:url", namespaces)):
        loc = url_node.findtext("sm:loc", default="", namespaces=namespaces)
        news_node = url_node.find("news:news", namespaces)
        title = ""
        published = ""
        if news_node is not None:
            title = news_node.findtext("news:title", default="", namespaces=namespaces)
            published = news_node.findtext("news:publication_date", default="", namespaces=namespaces)
        if not looks_like_it_story(title, loc):
            continue
        item = normalize_global_item(
            title=title,
            source="Reuters",
            url=loc,
            published_at=published,
            excerpt="",
            category=_classify(title, ""),
            score=max_items * 3 - index,
        )
        if item:
            items.append(item)
        if len(items) >= max_items:
            break
    return items


def fetch_global_news(max_items: int = 10, timeout: int = 12) -> list[GlobalNewsItem]:
    items: list[GlobalNewsItem | None] = _fetch_reuters_sitemap(max_items=max_items, timeout=timeout)
    for source, feed_url in FEEDS:
        try:
            parsed = feedparser.parse(feed_url, request_headers={"User-Agent": "DeveloperPulse/2.0"}, agent="DeveloperPulse/2.0")
        except Exception as exc:
            logger.warning("No se pudo leer feed global %s: %s", source, exc)
            continue

        for index, entry in enumerate(parsed.entries[: max_items * 2]):
            link = getattr(entry, "link", "")
            title = getattr(entry, "title", "")
            excerpt = getattr(entry, "summary", "") or getattr(entry, "description", "")
            published = getattr(entry, "published", "") or getattr(entry, "updated", "")
            score = max(1, max_items * 2 - index)
            item = normalize_global_item(title, source, link, published, excerpt, score=score)
            items.append(item)

    return dedupe_global_items(items)[:max_items]
