from __future__ import annotations

import unittest
from unittest.mock import patch

from src.media import extract_media_from_feed_entry, extract_media_from_html, fetch_media_preview


class MediaExtractionTests(unittest.TestCase):
    def test_extracts_og_image(self) -> None:
        preview = extract_media_from_html(
            '<meta property="og:image" content="/preview.jpg">',
            "https://example.com/articles/story",
        )

        self.assertIsNotNone(preview)
        self.assertEqual(preview.media_url, "https://example.com/preview.jpg")
        self.assertEqual(preview.media_type, "image")

    def test_extracts_twitter_image_fallback(self) -> None:
        preview = extract_media_from_html(
            '<meta name="twitter:image" content="https://cdn.example.com/card.png">',
            "https://example.com/story",
        )

        self.assertIsNotNone(preview)
        self.assertEqual(preview.media_url, "https://cdn.example.com/card.png")
        self.assertEqual(preview.media_type, "image")

    def test_detects_video_metadata_with_image_thumbnail(self) -> None:
        preview = extract_media_from_html(
            """
            <meta property="og:type" content="video.other">
            <meta property="og:image" content="https://cdn.example.com/video.jpg">
            <meta property="og:video" content="https://cdn.example.com/video.mp4">
            """,
            "https://example.com/watch",
        )

        self.assertIsNotNone(preview)
        self.assertEqual(preview.media_url, "https://cdn.example.com/video.jpg")
        self.assertEqual(preview.media_type, "video")

    def test_video_metadata_without_thumbnail_is_skipped(self) -> None:
        preview = extract_media_from_html(
            '<meta property="og:video" content="https://cdn.example.com/video.mp4">',
            "https://example.com/watch",
        )

        self.assertIsNone(preview)

    def test_skips_local_and_private_urls(self) -> None:
        self.assertIsNone(extract_media_from_html('<meta property="og:image" content="/x.jpg">', "http://localhost/story"))
        self.assertIsNone(extract_media_from_html('<meta property="og:image" content="/x.jpg">', "http://127.0.0.1/story"))
        self.assertIsNone(extract_media_from_html('<meta property="og:image" content="/x.jpg">', "ftp://example.com/story"))

    def test_extracts_feed_entry_media(self) -> None:
        preview = extract_media_from_feed_entry(
            {"media_thumbnail": [{"url": "https://cdn.example.com/feed.jpg"}]},
            "https://example.com/story",
        )

        self.assertIsNotNone(preview)
        self.assertEqual(preview.media_url, "https://cdn.example.com/feed.jpg")
        self.assertEqual(preview.media_type, "image")

    def test_fetch_skips_non_html_response(self) -> None:
        class Response:
            text = "binary"
            headers = {"content-type": "image/jpeg"}

            def raise_for_status(self) -> None:
                return None

        with patch("src.media.requests.get", return_value=Response()):
            self.assertIsNone(fetch_media_preview("https://example.com/image.jpg"))


if __name__ == "__main__":
    unittest.main()
