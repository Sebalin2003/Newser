from __future__ import annotations

import importlib.util
import json
import os
import unittest
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from src.database import Base, DynamicKeyword, MacroResumen, Noticia
from src import database, dynamic_keywords, web_services


class WebServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine)

        @contextmanager
        def temporary_session():
            session = self.session_factory()
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()

        self.temporary_session = temporary_session
        self.session_patch = patch.object(web_services, "get_session", temporary_session)
        self.session_patch.start()
        self.dynamic_session_patch = patch.object(dynamic_keywords, "get_session", temporary_session)
        self.dynamic_session_patch.start()

    def tearDown(self) -> None:
        self.dynamic_session_patch.stop()
        self.session_patch.stop()
        self.engine.dispose()

    def add_article(
        self,
        article_id: str,
        title: str,
        source: str,
        area: str,
        score: float,
        published_at: datetime | None = None,
        url: str | None = None,
        media_url: str | None = None,
        media_type: str | None = None,
        summary: str = "Resumen no disponible",
        summary_en: str | None = None,
    ) -> None:
        now = datetime.now(timezone.utc)
        with self.session_factory() as session:
            session.add(
                Noticia(
                    id=article_id,
                    titulo=title,
                    url=url or f"https://example.test/{article_id}",
                    fuente=source,
                    descripcion_original=f"{title} description",
                    resumen_ia=summary,
                    resumen_ia_en=summary_en,
                    area_matcheada=area,
                    fecha_publicacion=published_at or now,
                    fecha_ingesta=now,
                    selected_score=score,
                    tags_json=json.dumps(["agents"]),
                    media_url=media_url,
                    media_type=media_type,
                    media_source_url=url if media_url else None,
                )
            )
            session.commit()

    def add_brief(
        self,
        brief_date: date,
        text: str = "Brief text",
        payload: dict | None = None,
    ) -> None:
        with self.session_factory() as session:
            session.add(
                MacroResumen(
                    fecha=brief_date,
                    texto=text,
                    n_noticias=3,
                    n_clusters=1,
                    modelo="gemini",
                    brief_json=json.dumps(payload) if payload is not None else None,
                    fecha_generacion=datetime.now(timezone.utc),
                )
            )
            session.commit()

    def test_feed_filters_by_source_area_date_query_and_score_order(self) -> None:
        today = datetime.now(timezone.utc).date().isoformat()
        self.add_article("keep", "Agent runtime", "OpenAI Blog", "ai_agents", 90)
        self.add_article("wrong-source", "Agent runtime", "Reuters", "ai_agents", 95)
        self.add_article("wrong-area", "Agent runtime", "OpenAI Blog", "semiconductores", 99)

        result = web_services.get_feed(
            fecha=today,
            fuentes=["OpenAI Blog"],
            areas=["ai_agents"],
            q="agent",
        )

        self.assertEqual([item["id"] for item in result["items"]], ["keep"])
        self.assertEqual(result["count"], 1)

    def test_feed_all_dates_disables_date_filter(self) -> None:
        today = datetime.now(web_services.BRIEF_TIMEZONE).date()
        yesterday = today - timedelta(days=1)
        self.add_article(
            "today",
            "Agent runtime today",
            "OpenAI Blog",
            "ai_agents",
            90,
            published_at=datetime(today.year, today.month, today.day, 15, tzinfo=timezone.utc),
        )
        self.add_article(
            "yesterday",
            "Agent runtime yesterday",
            "OpenAI Blog",
            "ai_agents",
            80,
            published_at=datetime(yesterday.year, yesterday.month, yesterday.day, 15, tzinfo=timezone.utc),
        )

        today_result = web_services.get_feed(fecha=today.isoformat(), fuentes=["OpenAI Blog"])
        all_result = web_services.get_feed(fecha="all", fuentes=["OpenAI Blog"])

        self.assertEqual([item["id"] for item in today_result["items"]], ["today"])
        self.assertEqual([item["id"] for item in all_result["items"]], ["today", "yesterday"])
        self.assertEqual(all_result["fecha"], "all")
        self.assertEqual(all_result["hot_topics"], [])

    def test_feed_deduplicates_repeated_articles_by_url_after_sorting(self) -> None:
        today = datetime.now(web_services.BRIEF_TIMEZONE).date().isoformat()
        repo_url = "https://github.com/calesthio/OpenMontage"
        self.add_article(
            "repo-old",
            "[GitHub] calesthio/OpenMontage ⭐23,576 (+1,674 stars today)",
            "GitHub Trending",
            "developer_tools",
            89,
            url=repo_url,
        )
        self.add_article(
            "repo-new",
            "[GitHub] calesthio/OpenMontage ⭐23,669 (+1,754 stars today)",
            "GitHub Trending",
            "developer_tools",
            90,
            url=f"{repo_url}/",
        )
        self.add_article("other", "Different repository", "GitHub Trending", "developer_tools", 80)

        result = web_services.get_feed(fecha=today, fuentes=["GitHub Trending"])

        self.assertEqual([item["id"] for item in result["items"]], ["repo-new", "other"])
        self.assertEqual(result["count"], 2)

    def test_hot_topics_require_three_distinct_sources_and_pick_highest_score(self) -> None:
        today = datetime.now(web_services.BRIEF_TIMEZONE).date().isoformat()
        self.add_article("openai-low", "OpenAI GPT launch expands agents", "Reuters", "ai_agents", 71)
        self.add_article("openai-lead", "OpenAI GPT launch expands enterprise agents", "OpenAI Blog", "ai_agents", 93)
        self.add_article("openai-mid", "OpenAI GPT launch covered by developers", "Hacker News", "ai_agents", 86)
        self.add_article("small-1", "Cloud runtime outage report", "Reuters", "infrastructure_cloud", 95)
        self.add_article("small-2", "Cloud runtime outage analysis", "GitHub Blog", "infrastructure_cloud", 94)

        topics = web_services.get_hot_topics(date.fromisoformat(today))

        self.assertEqual(len(topics), 1)
        self.assertEqual(topics[0]["topic"], "OpenAI")
        self.assertEqual(topics[0]["representative_id"], "openai-lead")
        self.assertEqual(topics[0]["source_count"], 3)
        self.assertEqual(topics[0]["items"], 3)
        self.assertEqual(topics[0]["sources"], ["Hacker News", "OpenAI Blog", "Reuters"])
        self.assertEqual([item["id"] for item in topics[0]["supporting_items"]], ["openai-lead", "openai-mid", "openai-low"])

    def test_hot_topics_group_shared_model_version_across_different_wording(self) -> None:
        today = datetime.now(web_services.BRIEF_TIMEZONE).date()
        self.add_article("gpt-hn-1", "Previewing GPT‑5.6 Sol: a next-generation model", "Hacker News", "ai_agents", 89)
        self.add_article("gpt-openai", "Previewing GPT-5.6 Sol: a next-generation model", "OpenAI Blog", "cybersecurity", 91)
        self.add_article("gpt-hn-2", "U.S. government will decide who gets to use GPT-5.6", "Hacker News", "ai_agents", 88)
        self.add_article("gpt-reuters", "OpenAI defers public rollout of GPT‑5.6 as US seeks early access to frontier AI", "Reuters", "ai_agents", 87)
        self.add_article("other-model", "GPT-5.5 prompt leaks mention OpenAI and frontier AI", "GitHub Trending", "ai_agents", 99)
        self.add_article("model-free-ai", "A design format gives coding agents structured understanding", "GitHub Trending", "developer_tools", 98)

        topics = web_services.get_hot_topics(today)

        self.assertEqual(topics[0]["topic"], "GPT-5.6")
        self.assertEqual(topics[0]["representative_id"], "gpt-openai")
        self.assertEqual(topics[0]["source_count"], 3)
        self.assertEqual(topics[0]["items"], 4)
        self.assertEqual(topics[0]["sources"], ["Hacker News", "OpenAI Blog", "Reuters"])
        supporting_ids = [item["id"] for item in topics[0]["supporting_items"]]
        self.assertNotIn("other-model", supporting_ids)
        self.assertNotIn("model-free-ai", supporting_ids)

    def test_feed_filters_do_not_change_date_level_hot_topics(self) -> None:
        today = datetime.now(web_services.BRIEF_TIMEZONE).date().isoformat()
        self.add_article("openai-r", "OpenAI agent launch details", "Reuters", "ai_agents", 80)
        self.add_article("openai-o", "OpenAI agent launch details for teams", "OpenAI Blog", "ai_agents", 90)
        self.add_article("openai-h", "OpenAI agent launch details discussion", "Hacker News", "ai_agents", 75)
        self.add_article("visible-only", "Different GitHub repository", "GitHub Trending", "developer_tools", 99)

        result = web_services.get_feed(fecha=today, fuentes=["GitHub Trending"])

        self.assertEqual([item["id"] for item in result["items"]], ["visible-only"])
        self.assertEqual(result["hot_topics"][0]["topic"], "OpenAI")
        self.assertEqual(result["hot_topics"][0]["source_count"], 3)

    def test_hot_topics_sort_by_source_count_then_score(self) -> None:
        today = datetime.now(web_services.BRIEF_TIMEZONE).date()
        for article_id, source, score in [
            ("openai-1", "Reuters", 60),
            ("openai-2", "OpenAI Blog", 60),
            ("openai-3", "Hacker News", 60),
            ("openai-4", "GitHub Blog", 60),
            ("security-1", "Reuters", 95),
            ("security-2", "GitHub Blog", 95),
            ("security-3", "Hacker News", 95),
        ]:
            title = "OpenAI model policy update" if article_id.startswith("openai") else "Security breach advisory update"
            self.add_article(article_id, title, source, "ai_agents", score)

        topics = web_services.get_hot_topics(today)

        self.assertEqual([topic["topic"] for topic in topics[:2]], ["OpenAI", "Security"])

    def test_hot_topics_empty_when_no_multi_source_cluster(self) -> None:
        today = datetime.now(web_services.BRIEF_TIMEZONE).date()
        self.add_article("only-one", "OpenAI standalone update", "OpenAI Blog", "ai_agents", 90)
        self.add_article("only-two-a", "Security incident report", "Reuters", "cybersecurity", 80)
        self.add_article("only-two-b", "Security incident analysis", "Hacker News", "cybersecurity", 81)

        self.assertEqual(web_services.get_hot_topics(today), [])

    def test_brief_returns_structured_json_when_available(self) -> None:
        today = datetime.now(web_services.BRIEF_TIMEZONE).date()
        payload = {"intro": "Brief intro", "items": [], "trend_reading": "Trend"}
        with self.session_factory() as session:
            session.add(
                MacroResumen(
                    fecha=today,
                    texto="fallback",
                    n_noticias=3,
                    n_clusters=1,
                    modelo="gemini",
                    brief_json=json.dumps(payload),
                    fecha_generacion=datetime.now(timezone.utc),
                )
            )
            session.commit()

        result = web_services.get_brief(today.isoformat())

        self.assertTrue(result["available"])
        self.assertEqual(result["brief_json"], payload)

    def test_summary_generation_reports_missing_key_without_crashing(self) -> None:
        self.add_article("no-key", "Needs summary", "Reuters", "general", 60)

        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
            result = web_services.generate_summary("no-key")

        self.assertFalse(result["ok"])
        self.assertIn("GEMINI_API_KEY", result["reason"])

    def test_feed_uses_language_specific_summary_and_area_label(self) -> None:
        today = datetime.now(web_services.BRIEF_TIMEZONE).date().isoformat()
        self.add_article(
            "localized",
            "Localized story",
            "OpenAI Blog",
            "ai_agents",
            90,
            summary="Resumen español",
            summary_en="English summary",
        )

        spanish = web_services.get_feed(fecha=today, lang="es")["items"][0]
        english = web_services.get_feed(fecha=today, lang="en")["items"][0]

        self.assertEqual(spanish["resumen_ia"], "Resumen español")
        self.assertEqual(spanish["area_label"], "IA y agentes")
        self.assertEqual(english["resumen_ia"], "English summary")
        self.assertEqual(english["area_label"], "AI & Agents")

    def test_english_feed_does_not_fall_back_to_spanish_summary(self) -> None:
        today = datetime.now(web_services.BRIEF_TIMEZONE).date().isoformat()
        self.add_article(
            "spanish-only",
            "Spanish only story",
            "OpenAI Blog",
            "ai_agents",
            90,
            summary="Resumen español",
        )

        item = web_services.get_feed(fecha=today, lang="en")["items"][0]

        self.assertEqual(item["resumen_ia"], "")

    def test_generate_english_summary_does_not_overwrite_spanish_cache(self) -> None:
        self.add_article(
            "needs-en",
            "Needs English summary",
            "Reuters",
            "cybersecurity",
            84,
            summary="Resumen español",
        )

        with patch.dict(os.environ, {"GEMINI_API_KEY": "key"}, clear=False), \
             patch("src.processor.GEMINI_AVAILABLE", True), \
             patch("src.processor.GEMINI_API_KEY", "key"), \
             patch("src.processor._generar_resumen_gemini", return_value='{"resumen":"English summary"}'), \
             patch("src.processor.get_session", self.temporary_session):
            result = web_services.generate_summary("needs-en", lang="en")

        self.assertTrue(result["ok"])
        self.assertEqual(result["summary"], "English summary")
        with self.session_factory() as session:
            row = session.get(Noticia, "needs-en")
            self.assertEqual(row.resumen_ia, "Resumen español")
            self.assertEqual(row.resumen_ia_en, "English summary")

    def test_missing_article_message_is_localized(self) -> None:
        spanish = web_services.generate_summary("missing", lang="es")
        english = web_services.generate_summary("missing", lang="en")

        self.assertEqual(spanish["reason"], "Artículo no encontrado.")
        self.assertEqual(english["reason"], "Article not found.")

    def test_suggestions_require_two_characters_and_limit_results(self) -> None:
        today = datetime.now(web_services.BRIEF_TIMEZONE).date().isoformat()
        for index, score in enumerate([10, 80, 60, 70, 90, 50]):
            self.add_article(f"item-{index}", f"Agent story {index}", "GitHub Blog", "ai_agents", score)

        self.assertEqual(web_services.get_suggestions("a"), [])

        with patch.object(web_services, "parse_filter_date", return_value=date.fromisoformat(today)):
            suggestions = web_services.get_suggestions("agent")

        self.assertEqual(len(suggestions), 5)
        self.assertEqual([item["score"] for item in suggestions], [90.0, 80.0, 70.0, 60.0, 50.0])

    def test_feed_staleness_uses_thirty_minute_threshold(self) -> None:
        now = datetime.now(timezone.utc)

        self.assertFalse(web_services.is_feed_stale(now - timedelta(minutes=29), now))
        self.assertTrue(web_services.is_feed_stale(now - timedelta(minutes=30), now))
        self.assertTrue(web_services.is_feed_stale(None, now))

    def test_refresh_lock_prevents_concurrent_refreshes(self) -> None:
        acquired = web_services._refresh_lock.acquire(blocking=False)
        self.addCleanup(lambda: web_services._refresh_lock.release() if acquired else None)

        with patch.object(web_services, "is_feed_stale", return_value=True):
            self.assertFalse(web_services.ensure_feed_refresh(background=True))

    def test_past_daily_briefs_use_previous_seven_days_newest_first(self) -> None:
        today = date(2026, 6, 25)
        self.add_brief(today, "today")
        self.add_brief(today - timedelta(days=1), "yesterday", {"intro": "Yesterday", "items": []})
        self.add_brief(today - timedelta(days=7), "day seven")
        self.add_brief(today - timedelta(days=8), "too old")

        result = web_services.get_past_daily_briefs(today)

        self.assertEqual([item["fecha"] for item in result["items"]], ["2026-06-24", "2026-06-18"])
        self.assertEqual(result["items"][0]["brief_json"], {"intro": "Yesterday", "items": []})
        self.assertIsNone(result["items"][1]["brief_json"])

    def test_daily_brief_catchup_runs_only_after_8_when_missing(self) -> None:
        tz = web_services.BRIEF_TIMEZONE
        before_8 = datetime(2026, 6, 29, 7, 59, tzinfo=tz)
        after_8 = datetime(2026, 6, 29, 8, 1, tzinfo=tz)

        self.assertFalse(web_services.should_catch_up_daily_brief(before_8))
        self.assertTrue(web_services.should_catch_up_daily_brief(after_8))

        self.add_brief(date(2026, 6, 29), "today")

        self.assertFalse(web_services.should_catch_up_daily_brief(after_8))

    def test_daily_brief_catchup_uses_existing_generation_path_once(self) -> None:
        with (
            patch.object(web_services, "should_catch_up_daily_brief", return_value=True),
            patch.object(web_services, "generate_daily_brief_job", return_value={"ok": True}) as generate,
        ):
            self.assertTrue(web_services.ensure_daily_brief_catchup(background=False))
            generate.assert_called_once()

    def test_favorite_columns_are_declared(self) -> None:
        columns = {column["name"] for column in inspect(self.engine).get_columns("noticias")}

        self.assertIn("is_favorite", columns)
        self.assertIn("favorited_at", columns)

    def test_media_columns_are_declared_and_serialized(self) -> None:
        columns = {column["name"] for column in inspect(self.engine).get_columns("noticias")}
        self.assertIn("media_url", columns)
        self.assertIn("media_type", columns)
        self.assertIn("media_source_url", columns)

        today = datetime.now(web_services.BRIEF_TIMEZONE).date().isoformat()
        self.add_article(
            "media-story",
            "Story with image",
            "OpenAI Blog",
            "ai_agents",
            91,
            url="https://openai.com/news/story",
            media_url="https://cdn.example.test/story.jpg",
            media_type="image",
        )

        item = web_services.get_feed(fecha=today)["items"][0]

        self.assertEqual(item["media_url"], "https://cdn.example.test/story.jpg")
        self.assertEqual(item["media_type"], "image")
        self.assertEqual(item["media_source_url"], "https://openai.com/news/story")

    def test_dynamic_keywords_promote_emerging_multi_word_terms(self) -> None:
        self.add_article("vibe-1", "Vibe coding loop tools for AI agents", "Hacker News", "ai_agents", 88)
        self.add_article("vibe-2", "Developers adopt vibe coding skill loops", "GitHub Blog", "developer_tools", 84)
        self.add_article("vibe-3", "New vibe coding workflow improves agent skill routing", "GitHub Trending", "ai_agents", 82)

        items = dynamic_keywords.discover_dynamic_keywords()
        terms = {item["term"] for item in items}

        self.assertIn("vibe coding", terms)
        self.assertTrue(all("openai" != term for term in terms))
        self.assertTrue(all("airpods" != term for term in terms))

    def test_dynamic_keyword_scoring_boost_is_guarded(self) -> None:
        from src.scoring import calculate_item_score

        now = datetime.now(timezone.utc)
        relevant = {
            "titulo": "Vibe coding workflow improves AI agent loops",
            "descripcion_original": "A developer SDK for OpenAI coding agents.",
            "fuente": "GitHub Blog",
            "area_matcheada": "ai_agents",
            "fecha_ingesta": now,
        }
        off_topic = {
            "titulo": "LibrePods: AirPods liberated",
            "descripcion_original": "Open source firmware for Android bluetooth earbuds.",
            "fuente": "Hacker News",
            "area_matcheada": "ai_agents",
            "fecha_ingesta": now,
            "score": 150,
            "num_comentarios": 41,
        }

        base = calculate_item_score(relevant, now=now)
        boosted = calculate_item_score(relevant, now=now, dynamic_keywords=["vibe coding"])
        capped = calculate_item_score(off_topic, now=now, dynamic_keywords=["open source firmware"])

        self.assertGreater(boosted.selected_score, base.selected_score)
        self.assertEqual(boosted.components["dynamic_keyword_matches"], ["vibe coding"])
        self.assertLessEqual(capped.selected_score, 48)

    def test_mark_and_remove_favorite(self) -> None:
        self.add_article("fav-1", "Favorite story", "Reuters", "ai_agents", 82)

        marked = web_services.mark_favorite("fav-1")
        self.assertTrue(marked["ok"])
        self.assertTrue(marked["is_favorite"])
        self.assertIsNotNone(marked["favorited_at"])

        removed = web_services.remove_favorite("fav-1")
        self.assertTrue(removed["ok"])
        self.assertFalse(removed["is_favorite"])
        self.assertIsNone(removed["favorited_at"])

    def test_favorites_list_only_favorites_newest_first(self) -> None:
        self.add_article("old-fav", "Old favorite", "Reuters", "ai_agents", 80)
        self.add_article("new-fav", "New favorite", "Reuters", "ai_agents", 90)
        self.add_article("not-fav", "Regular story", "Reuters", "ai_agents", 95)
        now = datetime.now(timezone.utc)
        with self.session_factory() as session:
            session.query(Noticia).filter(Noticia.id == "old-fav").update(
                {"is_favorite": 1, "favorited_at": now - timedelta(hours=2)}
            )
            session.query(Noticia).filter(Noticia.id == "new-fav").update(
                {"is_favorite": 1, "favorited_at": now}
            )
            session.commit()

        result = web_services.get_favorites()

        self.assertEqual(result["count"], 2)
        self.assertEqual([item["id"] for item in result["items"]], ["new-fav", "old-fav"])
        self.assertTrue(result["items"][0]["is_favorite"])

    def test_cleanup_keeps_favorites_and_removes_old_non_favorites(self) -> None:
        old = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=45)
        self.add_article("keep-fav", "Keep favorite", "Reuters", "ai_agents", 80, old)
        self.add_article("remove-old", "Remove old", "Reuters", "ai_agents", 80, old)
        with self.session_factory() as session:
            session.query(Noticia).filter(Noticia.id.in_(["keep-fav", "remove-old"])).update(
                {"fecha_ingesta": old},
                synchronize_session=False,
            )
            session.query(Noticia).filter(Noticia.id == "keep-fav").update(
                {"is_favorite": 1, "favorited_at": datetime.now(timezone.utc).replace(tzinfo=None)}
            )
            session.commit()

        with patch.object(database, "engine", self.engine):
            database.limpiar_datos_antiguos(dias_retencion=30)

        with self.session_factory() as session:
            ids = {row.id for row in session.query(Noticia).all()}
        self.assertIn("keep-fav", ids)
        self.assertNotIn("remove-old", ids)


@unittest.skipUnless(importlib.util.find_spec("fastapi"), "FastAPI is not installed")
class WebApiRouteTests(unittest.TestCase):
    def test_feed_route_delegates_to_service(self) -> None:
        from fastapi.testclient import TestClient
        import web_app

        with patch.object(web_app.web_services, "get_feed", return_value={"items": [], "count": 0, "hot_topics": []}) as get_feed:
            response = TestClient(web_app.app).get("/api/feed?lang=en")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 0)
        self.assertEqual(get_feed.call_args.kwargs["lang"], "en")

    def test_summary_route_returns_clear_error_status(self) -> None:
        from fastapi.testclient import TestClient
        import web_app

        with patch.object(
            web_app.web_services,
            "generate_summary",
            return_value={"ok": False, "reason": "GEMINI_API_KEY is missing."},
        ) as generate_summary:
            response = TestClient(web_app.app).post("/api/articles/article-1/summary?lang=en")

        self.assertEqual(response.status_code, 400)
        self.assertIn("GEMINI_API_KEY", response.json()["reason"])
        self.assertEqual(generate_summary.call_args.kwargs["lang"], "en")

    def test_refresh_status_route_returns_stable_json(self) -> None:
        from fastapi.testclient import TestClient
        import web_app

        with patch.object(web_app.web_services, "get_refresh_status", return_value={"updating": False}):
            response = TestClient(web_app.app).get("/api/refresh-status")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"updating": False})

    def test_dynamic_keywords_route_returns_items(self) -> None:
        from fastapi.testclient import TestClient
        import web_app

        with patch.object(web_app.web_services, "get_dynamic_keywords", return_value={"items": [{"term": "vibe coding"}]}):
            response = TestClient(web_app.app).get("/api/dynamic-keywords")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"][0]["term"], "vibe coding")

    def test_daily_briefs_route_returns_items(self) -> None:
        from fastapi.testclient import TestClient
        import web_app

        with patch.object(web_app.web_services, "get_past_daily_briefs", return_value={"items": []}) as get_past:
            response = TestClient(web_app.app).get("/api/daily-briefs?lang=en")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"items": []})
        self.assertEqual(get_past.call_args.kwargs["lang"], "en")

    def test_favorites_route_returns_items(self) -> None:
        from fastapi.testclient import TestClient
        import web_app

        with patch.object(web_app.web_services, "get_favorites", return_value={"items": [], "count": 0}):
            response = TestClient(web_app.app).get("/api/favorites")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"items": [], "count": 0})

    def test_favorite_routes_return_state_and_missing_errors(self) -> None:
        from fastapi.testclient import TestClient
        import web_app

        client = TestClient(web_app.app)
        with patch.object(web_app.web_services, "mark_favorite", return_value={"ok": True, "is_favorite": True}):
            response = client.post("/api/articles/article-1/favorite")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["is_favorite"])

        with patch.object(web_app.web_services, "remove_favorite", return_value={"ok": True, "is_favorite": False}):
            response = client.delete("/api/articles/article-1/favorite")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["is_favorite"])

        with patch.object(web_app.web_services, "mark_favorite", return_value={"ok": False, "reason": "Article not found."}):
            response = client.post("/api/articles/missing/favorite")
        self.assertEqual(response.status_code, 404)
        self.assertIn("Article not found", response.json()["reason"])

    def test_feed_route_returns_multi_source_hot_topic_shape(self) -> None:
        from fastapi.testclient import TestClient
        import web_app

        payload = {
            "items": [],
            "count": 0,
            "fecha": "2026-06-26",
            "orden": "Puntaje",
            "hot_topics": [
                {
                    "topic": "OpenAI",
                    "title": "OpenAI launch",
                    "representative_id": "article-1",
                    "items": 3,
                    "source_count": 3,
                    "sources": ["Hacker News", "OpenAI Blog", "Reuters"],
                    "score": 250.0,
                    "supporting_items": [
                        {"id": "article-1", "title": "OpenAI launch", "source": "OpenAI Blog", "score": 93.0, "url": "https://example.test/1"}
                    ],
                }
            ],
        }
        with patch.object(web_app.web_services, "get_feed", return_value=payload):
            response = TestClient(web_app.app).get("/api/feed?fecha=2026-06-26")

        self.assertEqual(response.status_code, 200)
        topic = response.json()["hot_topics"][0]
        self.assertEqual(topic["representative_id"], "article-1")
        self.assertEqual(topic["sources"], ["Hacker News", "OpenAI Blog", "Reuters"])
        self.assertEqual(topic["supporting_items"][0]["source"], "OpenAI Blog")

    def test_scheduler_registers_feed_refresh_job(self) -> None:
        import web_app

        scheduler = web_app.create_scheduler()
        try:
            self.assertIsNotNone(scheduler.get_job(web_app.REFRESH_JOB_ID))
            daily_job = scheduler.get_job(web_app.DAILY_BRIEF_JOB_ID)
            self.assertIsNotNone(daily_job)
            self.assertEqual(str(daily_job.trigger), "cron[hour='8', minute='0']")
        finally:
            if scheduler.running:
                scheduler.shutdown(wait=False)

class WebUiStaticTests(unittest.TestCase):
    def test_new_filter_controls_replace_refresh_and_order_select(self) -> None:
        template = Path("templates/index.html").read_text(encoding="utf-8")
        script = Path("static/app.js").read_text(encoding="utf-8")

        self.assertIn("data-multiselect", template)
        self.assertIn("Seleccionar todo", template)
        self.assertIn('type="radio" name="orden"', template)
        self.assertNotIn("Refresh feed", template)
        self.assertNotIn("refreshButton", script)

    def test_search_mode_hides_overview_and_fetches_only_feed(self) -> None:
        template = Path("templates/index.html").read_text(encoding="utf-8")
        script = Path("static/app.js").read_text(encoding="utf-8")

        self.assertIn("overview-only", template)
        self.assertIn("setSearchMode(searchActive)", script)
        self.assertIn('section.hidden = active', script)
        self.assertIn('if (!searchActive)', script)

    def test_search_enter_submits_query(self) -> None:
        script = Path("static/app.js").read_text(encoding="utf-8")

        self.assertIn("function submitSearch()", script)
        self.assertIn('event.key !== "Enter"', script)
        self.assertIn("event.preventDefault()", script)
        input_handler = script.split('search.addEventListener("input"', maxsplit=1)[1].split('search.addEventListener("keydown"', maxsplit=1)[0]
        self.assertIn("loadSuggestions();", input_handler)
        self.assertNotIn("state.query = search.value.trim()", input_handler)
        self.assertNotIn("loadAll();\n  }, 250)", input_handler)

    def test_daily_briefs_mode_ui_is_present(self) -> None:
        template = Path("templates/index.html").read_text(encoding="utf-8")
        script = Path("static/app.js").read_text(encoding="utf-8")
        styles = Path("static/app.css").read_text(encoding="utf-8")

        self.assertIn("Actualizaciones de hoy", template)
        self.assertIn('rel="icon"', template)
        self.assertIn("/assets/favicon.png?v=logo-v1", template)
        self.assertIn('rel="apple-touch-icon"', template)
        self.assertIn("/assets/apple-touch-icon.png?v=logo-v1", template)
        self.assertGreater(Path("assets/favicon.png").stat().st_size, 0)
        self.assertGreater(Path("assets/apple-touch-icon.png").stat().st_size, 0)
        self.assertIn('"nav.today": "Actualizaciones de hoy"', script)
        self.assertIn('"nav.today": "Today\'s Updates"', script)
        self.assertIn('aria-label="Actualizaciones de hoy"', template)
        self.assertIn("Briefs diarios", template)
        self.assertIn("Favoritos", template)
        self.assertIn("Espacio de trabajo", template)
        self.assertIn("Controles del feed", template)
        self.assertIn("Estado del sistema", template)
        self.assertIn('data-view-target="today"', template)
        self.assertIn('data-view-target="briefs"', template)
        self.assertIn('data-view-target="favorites"', template)
        self.assertIn('id="daily-briefs"', template)
        self.assertIn('id="favorites"', template)
        self.assertIn('id="favorites-feed"', template)
        self.assertIn("favorites-feed-list", template)
        favorites_block = template.split('id="favorites"', maxsplit=1)[1].split('id="daily-briefs"', maxsplit=1)[0]
        self.assertNotIn("favorites-title", favorites_block)
        self.assertNotIn("Articles and repositories you marked for follow-up.", favorites_block)
        self.assertIn("Resumen ejecutivo", template)
        self.assertIn("Briefs diarios anteriores", template)
        self.assertIn("últimos 7 días", template)
        self.assertIn("loadDailyBriefs", script)
        self.assertIn("loadFavorites", script)
        self.assertIn('fetchJson(withLanguage("/api/brief"))', script)
        self.assertIn("/api/daily-briefs", script)
        self.assertIn("/api/favorites", script)
        self.assertIn("/favorite", script)
        self.assertIn("favorite-button", script)
        self.assertIn('"article.addFavorite": "Add to favorites"', script)
        self.assertIn('"article.removeFavorite": "Remove from favorites"', script)
        self.assertIn('item.fuente === "GitHub Trending"', script)
        self.assertIn("const summary = isRepository ? item.descripcion", script)
        self.assertIn("summary-button", script)
        self.assertIn("summary-spinner", script)
        self.assertIn("is-generating", script)
        self.assertIn('button.setAttribute("aria-busy", "true")', script)
        self.assertIn("function applyGeneratedSummary", script)
        self.assertNotIn("escapeHtml(summary).slice(0, 420)", script)
        self.assertNotIn("String(summary || \"\").slice(0, 420)", script)
        self.assertIn("function renderMediaPreview", script)
        self.assertIn("data-media-image", script)
        self.assertIn("article-media-video", script)
        self.assertIn("function openMediaModal", script)
        self.assertIn("function closeMediaModal", script)
        self.assertIn('id="media-modal"', template)
        self.assertIn('id="media-modal-image"', template)
        generate_summary_block = script.split("async function generateSummary", maxsplit=1)[1].split("async function toggleFavorite", maxsplit=1)[0]
        self.assertNotIn("await loadAll()", generate_summary_block)
        favorite_markup = script.split('const favoriteButton = `', maxsplit=1)[1].split("  return `", maxsplit=1)[0]
        self.assertNotIn("<span>", favorite_markup)
        self.assertIn("M8 13.8", script)
        self.assertIn("Usá el botón de corazón", script)
        self.assertNotIn("Saved to favorites.", script)
        self.assertNotIn("Removed from favorites.", script)
        self.assertIn("/static/app.js?v=lang-v1", template)
        self.assertIn("/static/app.css?v=lang-v1", template)
        self.assertIn('id="desktop-theme-toggle"', template)
        self.assertNotIn('id="mobile-theme-toggle"', template)
        self.assertIn('aria-label="Cambiar a modo claro"', template)
        self.assertIn('data-language-option="es"', template)
        self.assertIn('data-language-option="en"', template)
        self.assertIn('window.localStorage.getItem("newser.language")', script)
        self.assertIn('window.localStorage.setItem("newser.language", nextLanguage)', script)
        self.assertIn('return state.language === "en" ? "en-US" : "es-AR"', script)
        self.assertIn('fetchJson(withLanguage(`/api/articles/${encodeURIComponent(articleId)}/summary`)', script)
        self.assertIn('document.documentElement.dataset.theme', template)
        self.assertIn('localStorage.getItem("newser.theme") || "dark"', template)
        self.assertIn("function initTheme()", script)
        self.assertIn("function setTheme(theme)", script)
        self.assertIn('window.localStorage.setItem("newser.theme", selectedTheme)', script)
        self.assertIn("initTheme();", script)
        self.assertIn('html[data-theme="light"]', styles)
        self.assertIn("color-scheme: light", styles)
        self.assertIn("--sidebar-bg: #eef3f8", styles)
        self.assertIn("--text: #172131", styles)
        self.assertIn(".sidebar-theme-toggle", styles)
        topbar = template.split('class="topbar"', maxsplit=1)[1].split('id="status"', maxsplit=1)[0]
        self.assertNotIn("Command center", topbar)
        self.assertIn('id="topbar-date"', template)
        self.assertIn("data-all-dates", template)
        self.assertIn("date-all-option", template)
        self.assertIn('id="topbar-subtitle"', template)
        self.assertIn("topbarTitle.textContent", script)
        self.assertIn("function updateTopbarTitle()", script)
        self.assertIn("formatFeedDate(selectedDate)", script)
        self.assertIn('params.set("fecha", "all")', script)
        self.assertIn("function syncDateMode()", script)
        self.assertIn("dateInput.disabled = allDates", script)
        self.assertIn('dateModeLabel.textContent = allDates ? i18n("date.all") : i18n("date.today")', script)
        self.assertIn(".date-all-option", styles)
        self.assertIn("input:disabled", styles)
        self.assertIn('"brief.subtitle": "Every morning at 8 o\'clock"', script)
        self.assertIn('"brief.generating": "Today\'s brief is being generated.', script)
        self.assertIn(".topbar-subtitle", styles)
        self.assertNotIn("topbarEyebrow", script)
        self.assertIn('search.value = ""', script)
        self.assertIn("archive-empty", script)
        self.assertIn("data-daily-brief-toggle", script)
        self.assertIn("data-current-brief-toggle", script)
        self.assertIn("function renderCurrentBriefShell", script)
        self.assertIn("function bindCurrentBriefToggle", script)
        self.assertIn("function toggleDailyBrief", script)
        self.assertIn("daily-brief-chevron", script)
        self.assertIn(".mode-nav", styles)
        self.assertIn("#brief", styles)
        self.assertIn(".current-brief-body", styles)
        self.assertIn(".daily-brief-toggle", styles)
        self.assertIn(".daily-brief-chevron", styles)
        self.assertIn(".topbar-date", styles)
        self.assertNotIn("archive-hero", template)
        self.assertNotIn(".archive-hero", styles)
        self.assertNotIn(".archive-window", styles)
        self.assertIn(".favorites-view", styles)
        self.assertIn(".favorites-feed-list", styles)
        self.assertNotIn(".favorites-title", styles)
        self.assertIn(".favorite-button", styles)
        self.assertIn(".summary-spinner", styles)
        self.assertIn("@keyframes summary-spin", styles)
        self.assertIn(".article-media", styles)
        self.assertIn("article-main", script)
        self.assertIn("article-visual", script)
        self.assertIn("article-controls", script)
        self.assertIn(".article.has-visual .article-main", styles)
        self.assertIn("grid-template-columns: minmax(0, 1fr) minmax(190px, 240px)", styles)
        self.assertIn("max-width: min(250px, 100%)", styles)
        self.assertIn(".media-modal", styles)
        self.assertIn(".media-play", styles)
        self.assertIn("border-radius: 50%", styles)
        self.assertIn("background: var(--favorite-tint)", styles)
        self.assertNotIn("background: #ffe2ec", styles)
        self.assertIn("fill: transparent", styles)
        self.assertIn("fill: currentColor", styles)
        self.assertNotIn("body.view-favorites .feed {", styles)
        self.assertIn("[hidden]", styles)

    def test_system_status_central_panel_is_present(self) -> None:
        template = Path("templates/index.html").read_text(encoding="utf-8")
        script = Path("static/app.js").read_text(encoding="utf-8")
        styles = Path("static/app.css").read_text(encoding="utf-8")

        self.assertIn('id="system-status-button"', template)
        self.assertIn('data-view-target="system"', template)
        self.assertNotIn('id="refresh-status"', template)
        self.assertIn('id="system-status"', template)
        self.assertIn("Resumen operativo", template)
        self.assertIn('id="system-health"', template)
        self.assertIn('id="system-metrics"', template)
        self.assertIn('id="source-breakdown"', template)
        self.assertIn('state.view === "system"', script)
        self.assertIn("loadSystemStatus", script)
        self.assertIn('fetchJson(withLanguage("/api/stats"))', script)
        self.assertIn('fetchJson(withLanguage("/api/refresh-status"))', script)
        self.assertIn("renderSourceBreakdown", script)
        self.assertIn("view-system", script)
        system_hide_block = styles.split("body.view-system .today-only,", maxsplit=1)[1].split("{", maxsplit=1)[0]
        self.assertIn("body.view-system .feed-controls", system_hide_block)
        self.assertIn(".system-status-view", styles)
        self.assertIn(".system-health-grid", styles)
        self.assertIn(".source-breakdown", styles)

    def test_hot_topics_render_multi_source_details(self) -> None:
        script = Path("static/app.js").read_text(encoding="utf-8")
        styles = Path("static/app.css").read_text(encoding="utf-8")

        self.assertIn('"topics.empty": "No multi-source hot topics for this date yet."', script)
        self.assertIn("topic.sources", script)
        self.assertIn("topic.supporting_items", script)
        self.assertIn('"topics.supporting": "Supporting articles"', script)
        self.assertIn("topic-source-chip", script)
        self.assertIn("topic-support-item", script)
        self.assertIn(".topic-source-chip", styles)
        self.assertIn(".topic-support-item", styles)

    def test_today_mode_does_not_render_daily_brief_panel(self) -> None:
        template = Path("templates/index.html").read_text(encoding="utf-8")
        script = Path("static/app.js").read_text(encoding="utf-8")

        today_region = template.split('<section id="daily-briefs"', maxsplit=1)[0]
        self.assertNotIn('id="brief"', today_region)
        self.assertNotIn('id="stats"', today_region)
        self.assertNotIn('fetchJson(`/api/brief?fecha=', script)

    def test_sidebar_has_collapsible_responsive_state(self) -> None:
        template = Path("templates/index.html").read_text(encoding="utf-8")
        script = Path("static/app.js").read_text(encoding="utf-8")
        styles = Path("static/app.css").read_text(encoding="utf-8")

        brand_block = template.split('class="brand"', maxsplit=1)[1].split('id="sidebar-toggle"', maxsplit=1)[0]
        self.assertNotIn("<h1>Newser</h1>", brand_block)
        self.assertIn("brand-tagline", brand_block)
        self.assertIn("Analizador de tendencias IT", brand_block)
        self.assertIn("IT News Trend Analyzer", script)
        self.assertNotIn('id="theme-toggle"', brand_block)
        self.assertIn('id="desktop-theme-toggle"', template)
        self.assertIn("sidebar-theme-section", template)
        self.assertIn("width: 86px", styles)
        self.assertIn('id="sidebar-toggle"', template)
        self.assertIn('class="nav-icon"', template)
        self.assertNotIn("data-short=", template)
        self.assertIn("body.sidebar-collapsed .nav-button > span:not(.nav-icon)", styles)
        self.assertIn("body.sidebar-collapsed .nav-icon", styles)
        collapsed_theme_styles = styles.split("body.sidebar-collapsed .sidebar-theme-section", maxsplit=1)[1].split("}", maxsplit=1)[0]
        self.assertIn("display: none", collapsed_theme_styles)
        self.assertIn(".nav-button[data-view-target=\"favorites\"] .nav-icon path", styles)
        self.assertIn("function setSidebarCollapsed", script)
        self.assertIn("function initSidebar", script)
        self.assertIn("if (isPhoneViewport())", script)
        self.assertIn("closeMobileDrawer();", script)
        self.assertIn('document.querySelectorAll("#desktop-theme-toggle, [data-mobile-theme-action]")', script)
        self.assertIn("newser.sidebarCollapsed.mobile", script)
        self.assertIn("newser.sidebarCollapsed.desktop", script)
        self.assertIn("const shouldCollapse = saved === null ? isMobile", script)
        self.assertIn("body.sidebar-collapsed", styles)
        self.assertIn("grid-template-columns: 78px minmax(0, 1fr)", styles)
        self.assertIn("height: calc(72px + env(safe-area-inset-top, 0px))", styles)

    def test_mobile_shell_navigation_and_drawer_are_present(self) -> None:
        template = Path("templates/index.html").read_text(encoding="utf-8")
        script = Path("static/app.js").read_text(encoding="utf-8")
        styles = Path("static/app.css").read_text(encoding="utf-8")

        self.assertIn('class="mobile-appbar"', template)
        self.assertIn('id="mobile-menu-toggle"', template)
        self.assertNotIn('id="mobile-theme-toggle"', template)
        self.assertIn('id="mobile-drawer-backdrop"', template)
        self.assertIn('class="mobile-tabbar"', template)
        self.assertIn('data-view-target="more"', template)
        self.assertIn('id="mobile-more"', template)
        mobile_more = template.split('id="mobile-more"', maxsplit=1)[1].split('id="system-status"', maxsplit=1)[0]
        self.assertNotIn("Feed filters", mobile_more)
        self.assertNotIn("data-mobile-open-drawer", mobile_more)
        self.assertNotIn("mobile-more-hero", mobile_more)
        self.assertIn("Estado del sistema", mobile_more)
        self.assertIn("Apariencia", mobile_more)
        self.assertNotIn("About", mobile_more)
        self.assertNotIn("IT News Trend Analyzer for AI", mobile_more)
        self.assertIn("mobile-more-theme-toggle", mobile_more)
        self.assertIn("mobile-theme-main", mobile_more)
        self.assertIn("mobile-theme-state", mobile_more)
        self.assertIn("sidebar-theme-icon", mobile_more)
        self.assertIn("sidebar-theme-copy", mobile_more)
        self.assertIn("Cambiar entre modo oscuro y claro.", mobile_more)
        self.assertNotIn("mobile-more-theme-indicator", mobile_more)
        self.assertIn("function initMobileShell()", script)
        self.assertIn("function openMobileDrawer()", script)
        self.assertIn("function closeMobileDrawer()", script)
        self.assertIn('window.matchMedia("(max-width: 900px)")', script)
        self.assertIn("mobileMenuToggle.hidden = !todayActive", script)
        self.assertNotIn("data-mobile-open-drawer", script)
        self.assertIn('state.view === "more"', script)
        self.assertIn("view-more", script)
        self.assertIn("mobile-drawer-open", script)
        self.assertIn("@media (max-width: 900px)", styles)
        self.assertIn(".mobile-appbar", styles)
        self.assertIn(".mobile-tabbar", styles)
        self.assertIn(".mobile-more-view", styles)
        self.assertIn(".mobile-more-theme-toggle", styles)
        self.assertIn(".mobile-theme-main", styles)
        self.assertIn(".mobile-theme-state", styles)
        self.assertIn("body.sidebar-collapsed .mobile-more-theme-toggle .sidebar-theme-copy", styles)
        self.assertIn("const themeStateLabels", script)
        self.assertIn("[data-theme-state]", script)
        self.assertIn(".mobile-drawer-backdrop", styles)
        self.assertIn(".sidebar-theme-section", styles)
        mobile_styles = styles.rsplit("@media (max-width: 900px)", maxsplit=1)[1]
        self.assertIn(".mode-nav", mobile_styles)
        self.assertIn("display: none", mobile_styles.split(".mode-nav", maxsplit=1)[1].split("}", maxsplit=1)[0])
        self.assertIn(".sidebar-theme-section", mobile_styles)
        self.assertIn("display: none", mobile_styles.split(".sidebar-theme-section", maxsplit=1)[1].split("}", maxsplit=1)[0])
        self.assertIn(".system-section", mobile_styles)
        self.assertIn("body.sidebar-collapsed .system-section", mobile_styles)
        self.assertIn("body.sidebar-collapsed .sidebar-theme-section", mobile_styles)
        self.assertIn("width: min(82vw, 300px)", mobile_styles)
        self.assertIn("max-width: 300px", mobile_styles)
        self.assertIn("env(safe-area-inset-bottom", styles)
        self.assertIn("grid-template-columns: repeat(4, minmax(0, 1fr))", styles)
        self.assertIn("transform: translateX(-105%)", styles)
        self.assertIn("body.mobile-drawer-open .sidebar", styles)
        self.assertIn("-webkit-line-clamp: 3", styles)

    def test_github_star_titles_use_svg_icon(self) -> None:
        script = Path("static/app.js").read_text(encoding="utf-8")
        styles = Path("static/app.css").read_text(encoding="utf-8")

        self.assertIn("function renderTitleLabel", script)
        self.assertIn("function splitStarTitle", script)
        self.assertIn("function renderStarCount", script)
        self.assertIn("github-star-count", script)
        self.assertIn("<svg viewBox", script)
        self.assertIn("article-heading", script)
        self.assertIn("article-visual", script)
        self.assertIn("article-star-metric", script)
        self.assertIn("topic-title-row", script)
        self.assertIn("topic-star-metric", script)
        self.assertIn("function renderTopic", script)
        self.assertIn(".github-star-count", styles)
        self.assertIn(".article-star-metric", styles)
        self.assertIn(".topic-star-metric", styles)

    def test_hot_topics_are_compact_clickable_rows(self) -> None:
        template = Path("templates/index.html").read_text(encoding="utf-8")
        script = Path("static/app.js").read_text(encoding="utf-8")
        styles = Path("static/app.css").read_text(encoding="utf-8")

        topics_section = template.split('id="topics-panel"', maxsplit=1)[1].split('id="hot-topics"', maxsplit=1)[0]
        self.assertNotIn("Topics</p>", topics_section)
        self.assertIn("compact-title", template)
        self.assertIn("data-topic-toggle", script)
        self.assertIn("toggleTopicDetails", script)
        self.assertIn("topic-detail", script)
        self.assertIn("aria-expanded", script)
        self.assertIn("#topics-panel", styles)
        self.assertIn(".topic-detail", styles)

    def test_feed_header_does_not_show_feed_eyebrow(self) -> None:
        template = Path("templates/index.html").read_text(encoding="utf-8")

        feed_header = template.split('class="feed-head"', maxsplit=1)[1].split('id="feed"', maxsplit=1)[0]
        self.assertNotIn(">Feed<", feed_header)

    def test_layout_uses_right_panel_scroll_and_centered_content(self) -> None:
        template = Path("templates/index.html").read_text(encoding="utf-8")
        styles = Path("static/app.css").read_text(encoding="utf-8")

        self.assertIn('class="feed-block"', template)
        self.assertIn("grid-template-columns: clamp(236px, 22vw, 268px) minmax(0, 1fr)", styles)
        self.assertIn("scrollbar-gutter: stable", styles)
        self.assertIn(".workspace > *", styles)
        self.assertIn("width: 100%", styles)
        self.assertIn("scrollbar-width: none", styles)
        self.assertIn(".topic-title-row", styles)
        self.assertIn("overflow-wrap: anywhere", styles)
        self.assertIn("grid-template-columns: minmax(0, 1fr) auto", styles)
        self.assertIn("align-items: baseline", styles)
        self.assertIn("white-space: nowrap", styles)
        self.assertIn("position: fixed", styles)
        self.assertIn(".feed-block", styles)
        self.assertIn("env(safe-area-inset-top", styles)


if __name__ == "__main__":
    unittest.main()
