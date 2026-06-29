"""Media metadata extraction for article thumbnails."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


@dataclass(frozen=True)
class MediaPreview:
    media_url: str
    media_type: str
    media_source_url: str


def _is_safe_http_url(url: str) -> bool:
    parsed = urlparse(str(url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    host = (parsed.hostname or "").lower()
    if host in {"localhost"} or host.endswith(".localhost"):
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return True
    return not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved)


def _absolute_media_url(value: str, base_url: str) -> str:
    return urljoin(base_url, str(value or "").strip())


def _media_type_from_url(url: str, fallback: str = "image") -> str:
    path = urlparse(url).path.lower()
    if path.endswith((".mp4", ".webm", ".mov", ".m4v")):
        return "video"
    return fallback


def _entry_value(entry: Any, key: str) -> Any:
    if isinstance(entry, dict):
        return entry.get(key)
    return getattr(entry, key, None)


def extract_media_from_feed_entry(entry: Any, article_url: str) -> MediaPreview | None:
    if not _is_safe_http_url(article_url):
        return None

    candidates: list[tuple[str, str]] = []
    for key in ("media_thumbnail", "media_content", "enclosures", "links"):
        value = _entry_value(entry, key) or []
        for item in value:
            href = item.get("url") or item.get("href") if isinstance(item, dict) else ""
            mime = str(item.get("type") or item.get("medium") or "") if isinstance(item, dict) else ""
            if href and ("image" in mime or "video" in mime or key in {"media_thumbnail", "media_content"}):
                media_type = "video" if "video" in mime else _media_type_from_url(href)
                candidates.append((href, media_type))

    for raw_url, media_type in candidates:
        media_url = _absolute_media_url(raw_url, article_url)
        if _is_safe_http_url(media_url) and media_type in {"image", "video"}:
            return MediaPreview(media_url=media_url, media_type=media_type, media_source_url=article_url)
    return None


def extract_media_from_html(html: str, page_url: str) -> MediaPreview | None:
    if not html or not _is_safe_http_url(page_url):
        return None
    soup = BeautifulSoup(html, "html.parser")

    def content_for(*names: str) -> str:
        for name in names:
            tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
            content = tag.get("content", "") if tag else ""
            if content:
                return str(content).strip()
        return ""

    video_url = content_for("og:video", "og:video:url", "twitter:player")
    image_url = content_for("og:image", "og:image:url", "twitter:image", "twitter:image:src")
    og_type = content_for("og:type").lower()

    if video_url and image_url:
        media_url = _absolute_media_url(image_url, page_url)
        if _is_safe_http_url(media_url):
            return MediaPreview(media_url=media_url, media_type="video", media_source_url=page_url)
    if image_url:
        media_url = _absolute_media_url(image_url, page_url)
        if _is_safe_http_url(media_url):
            media_type = "video" if "video" in og_type else "image"
            return MediaPreview(media_url=media_url, media_type=media_type, media_source_url=page_url)
    return None


def fetch_media_preview(article_url: str, timeout: int = 4) -> MediaPreview | None:
    if not _is_safe_http_url(article_url):
        return None
    response = requests.get(
        article_url,
        timeout=timeout,
        headers={"User-Agent": "NewserBot/1.0 (+media-preview)"},
    )
    response.raise_for_status()
    content_type = response.headers.get("content-type", "").lower()
    if "text/html" not in content_type and "application/xhtml" not in content_type:
        return None
    return extract_media_from_html(response.text[:160_000], article_url)
