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
        ingested_at: datetime | None = None,
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
                    fecha_ingesta=ingested_at or now,
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

    def test_date_bounds_cover_thirty_day_display_window(self) -> None:
        today = date(2026, 6, 25)

        self.assertEqual(web_services.date_bounds(today), (date(2026, 5, 27), today))
        self.assertEqual(web_services.parse_filter_date("2026-05-27", today), date(2026, 5, 27))
        self.assertEqual(web_services.parse_filter_date("2026-05-26", today), today)
        self.assertEqual(web_services.parse_filter_date("invalid", today), today)

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

    def test_feed_marks_and_sorts_prioritized_sources_without_mutating_scores(self) -> None:
        today = datetime.now(web_services.BRIEF_TIMEZONE).date().isoformat()
        self.add_article("normal", "Normal source story", "Reuters", "ai_agents", 90)
        self.add_article("priority", "Priority source story", "OpenAI Blog", "ai_agents", 88)

        result = web_services.get_feed(
            fecha=today,
            fuentes=["Reuters", "OpenAI Blog"],
            prioritized_fuentes=["OpenAI Blog"],
        )

        self.assertEqual([item["id"] for item in result["items"][:2]], ["priority", "normal"])
        self.assertEqual(result["items"][0]["source_preference"], "prioritized")
        self.assertEqual(result["items"][0]["selected_score"], 88)
        self.assertEqual(result["items"][1]["source_preference"], "normal")

    def test_feed_all_dates_disables_date_filter_over_thirty_day_window(self) -> None:
        today = datetime.now(web_services.BRIEF_TIMEZONE).date()
        yesterday = today - timedelta(days=1)
        day_29 = today - timedelta(days=29)
        day_30 = today - timedelta(days=30)
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
        self.add_article(
            "day-29",
            "Agent runtime day 29",
            "OpenAI Blog",
            "ai_agents",
            70,
            published_at=datetime(day_29.year, day_29.month, day_29.day, 15, tzinfo=timezone.utc),
            ingested_at=datetime.now(timezone.utc) - timedelta(days=29),
        )
        self.add_article(
            "day-30",
            "Agent runtime day 30",
            "OpenAI Blog",
            "ai_agents",
            99,
            published_at=datetime(day_30.year, day_30.month, day_30.day, 15, tzinfo=timezone.utc),
            ingested_at=datetime.now(timezone.utc) - timedelta(days=31),
        )

        today_result = web_services.get_feed(fecha=today.isoformat(), fuentes=["OpenAI Blog"])
        all_result = web_services.get_feed(fecha="all", fuentes=["OpenAI Blog"])

        self.assertEqual([item["id"] for item in today_result["items"]], ["today"])
        self.assertEqual([item["id"] for item in all_result["items"]], ["today", "yesterday", "day-29"])
        self.assertEqual(all_result["fecha"], "all")
        self.assertEqual(all_result["hot_topics"], [])

    def test_feed_excludes_low_relevance_scores(self) -> None:
        today = datetime.now(web_services.BRIEF_TIMEZONE).date().isoformat()
        self.add_article("technical", "Developer SDK release", "GitHub Blog", "developer_tools", 60)
        self.add_article("off-topic", "Celebrity opens public library", "Hacker News", "developer_tools", 48)

        ids = [item["id"] for item in web_services.get_feed(fecha=today)["items"]]

        self.assertIn("technical", ids)
        self.assertNotIn("off-topic", ids)

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

    def test_hot_topics_exclude_github_trending_repositories(self) -> None:
        today = datetime.now(web_services.BRIEF_TIMEZONE).date()
        self.add_article("anthropic-r", "China issues backdoor security alert over Anthropic Claude Code", "Reuters", "cybersecurity", 78)
        self.add_article("anthropic-o", "Anthropic responds to Claude Code security concerns", "OpenAI Blog", "cybersecurity", 76)
        self.add_article("anthropic-h", "Developers discuss Claude Code security alert", "Hacker News", "cybersecurity", 74)
        self.add_article("repo-1", "hesreallyhim/awesome-claude-code", "GitHub Trending", "developer_tools", 95)
        self.add_article("repo-2", "wonderwhy-er/DesktopCommanderMCP", "GitHub Trending", "developer_tools", 94)
        self.add_article("repo-3", "steipete/CodexBar", "GitHub Trending", "developer_tools", 93)

        topics = web_services.get_hot_topics(today)

        self.assertEqual(len(topics), 1)
        self.assertEqual(topics[0]["sources"], ["Hacker News", "OpenAI Blog", "Reuters"])
        self.assertEqual(topics[0]["source_count"], 3)
        supporting_ids = [item["id"] for item in topics[0]["supporting_items"]]
        self.assertEqual(supporting_ids, ["anthropic-r", "anthropic-o", "anthropic-h"])
        self.assertNotIn("GitHub Trending", topics[0]["sources"])

    def test_search_feed_skips_hot_topic_clustering(self) -> None:
        today = datetime.now(web_services.BRIEF_TIMEZONE).date().isoformat()
        self.add_article("agent-search", "Agent runtime search", "OpenAI Blog", "ai_agents", 80)

        with patch.object(web_services, "get_hot_topics") as hot_topics:
            result = web_services.get_feed(fecha=today, q="agent")

        hot_topics.assert_not_called()
        self.assertEqual([item["id"] for item in result["items"]], ["agent-search"])
        self.assertEqual(result["hot_topics"], [])

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

    def test_hot_topics_limit_is_applied_after_selected_date_filter(self) -> None:
        today = datetime.now(web_services.BRIEF_TIMEZONE).date()
        yesterday = today - timedelta(days=1)
        for index in range(web_services.HOT_TOPIC_QUERY_LIMIT + 5):
            self.add_article(
                f"yesterday-{index}",
                f"Yesterday unrelated platform story {index}",
                "GitHub Trending",
                "developer_tools",
                99,
                published_at=datetime(yesterday.year, yesterday.month, yesterday.day, 12, tzinfo=timezone.utc),
                ingested_at=datetime(yesterday.year, yesterday.month, yesterday.day, 12, tzinfo=timezone.utc),
            )
        for article_id, source, score in [
            ("today-openai-r", "Reuters", 70),
            ("today-openai-o", "OpenAI Blog", 69),
            ("today-openai-h", "Hacker News", 68),
        ]:
            self.add_article(article_id, "OpenAI agent launch details", source, "ai_agents", score)

        topics = web_services.get_hot_topics(today)

        self.assertEqual([topic["topic"] for topic in topics], ["OpenAI"])
        self.assertEqual(topics[0]["source_count"], 3)

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

    def test_summary_generation_uses_article_language_lock(self) -> None:
        self.add_article("locked-summary", "Needs summary", "Reuters", "general", 60)

        with patch.dict(os.environ, {"GEMINI_API_KEY": "key"}, clear=False), \
             patch.object(web_services, "_get_summary_lock", wraps=web_services._get_summary_lock) as get_lock, \
             patch("src.processor.generar_resumen_individual", return_value={"ok": True, "summary": "Done"}):
            result = web_services.generate_summary("locked-summary", lang="en")

        self.assertTrue(result["ok"])
        get_lock.assert_called_once_with("locked-summary", "en")

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
        today_date = datetime.now(web_services.BRIEF_TIMEZONE).date()
        today = today_date.isoformat()
        day_29 = today_date - timedelta(days=29)
        day_31 = today_date - timedelta(days=31)
        for index, score in enumerate([10, 80, 60, 70, 90, 50]):
            self.add_article(f"item-{index}", f"Agent story {index}", "GitHub Blog", "ai_agents", score)
        self.add_article(
            "older-window-item",
            "Agent story older window",
            "GitHub Blog",
            "ai_agents",
            65,
            published_at=datetime(day_29.year, day_29.month, day_29.day, 15, tzinfo=timezone.utc),
            ingested_at=datetime.now(timezone.utc) - timedelta(days=29),
        )
        self.add_article(
            "outside-window-item",
            "Agent story outside window",
            "GitHub Blog",
            "ai_agents",
            100,
            published_at=datetime(day_31.year, day_31.month, day_31.day, 15, tzinfo=timezone.utc),
            ingested_at=datetime.now(timezone.utc) - timedelta(days=31),
        )

        self.assertEqual(web_services.get_suggestions("a"), [])

        with (
            patch.object(web_services, "parse_filter_date", return_value=date.fromisoformat(today)),
            patch.object(web_services, "get_feed") as get_feed,
        ):
            suggestions = web_services.get_suggestions("agent")
        get_feed.assert_not_called()
        all_date_suggestions = web_services.get_suggestions("older", fecha="all")

        self.assertEqual(len(suggestions), 5)
        self.assertEqual([item["score"] for item in suggestions], [90.0, 80.0, 70.0, 60.0, 50.0])
        self.assertEqual([item["id"] for item in all_date_suggestions], ["older-window-item"])

    def test_feed_staleness_uses_one_hour_threshold(self) -> None:
        now = datetime.now(timezone.utc)

        self.assertFalse(web_services.is_feed_stale(now - timedelta(minutes=59), now))
        self.assertTrue(web_services.is_feed_stale(now - timedelta(hours=1), now))
        self.assertTrue(web_services.is_feed_stale(None, now))

    def test_refresh_lock_prevents_concurrent_refreshes(self) -> None:
        acquired = web_services._refresh_lock.acquire(blocking=False)
        self.addCleanup(lambda: web_services._refresh_lock.release() if acquired else None)

        with patch.object(web_services, "is_feed_stale", return_value=True):
            self.assertFalse(web_services.ensure_feed_refresh(background=True))

    def test_past_daily_briefs_use_previous_thirty_days_newest_first(self) -> None:
        today = date(2026, 6, 25)
        self.add_brief(today, "today")
        self.add_brief(today - timedelta(days=1), "yesterday", {"intro": "Yesterday", "items": []})
        self.add_brief(today - timedelta(days=30), "day thirty")
        self.add_brief(today - timedelta(days=31), "too old")

        result = web_services.get_past_daily_briefs(today)

        self.assertEqual([item["fecha"] for item in result["items"]], ["2026-06-24", "2026-05-26"])
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
            patch.object(web_services, "generate_daily_brief_catchup_job", return_value={"ok": True}) as generate,
        ):
            self.assertTrue(web_services.ensure_daily_brief_catchup(background=False))
            generate.assert_called_once()

    def test_english_brief_generation_does_not_block_request(self) -> None:
        today = datetime.now(web_services.BRIEF_TIMEZONE).date()
        self.add_brief(today, "Resumen español")

        with (
            patch.object(web_services, "ensure_english_daily_brief", return_value=True) as ensure,
            patch("src.processor.generar_macro_resumen_dia") as generate,
        ):
            result = web_services.get_brief(today.isoformat(), lang="en")

        self.assertFalse(result["available"])
        self.assertTrue(result["catchup_started"])
        ensure.assert_called_once_with(background=True)
        generate.assert_not_called()

    def test_english_daily_brief_job_uses_english_generation(self) -> None:
        with patch("src.processor.generar_macro_resumen_dia", return_value={"macro_resumen_generado": True}) as generate:
            result = web_services.generate_english_daily_brief_job()

        self.assertTrue(result["macro_resumen_generado"])
        self.assertEqual(generate.call_args.kwargs["language"], "en")
        self.assertIsNone(generate.call_args.kwargs["target_date"])

    def test_english_daily_brief_job_can_target_archive_date(self) -> None:
        brief_date = date(2026, 7, 7)

        with patch("src.processor.generar_macro_resumen_dia", return_value={"macro_resumen_generado": True}) as generate:
            web_services.generate_english_daily_brief_job(brief_date)

        self.assertEqual(generate.call_args.kwargs["language"], "en")
        self.assertEqual(generate.call_args.kwargs["target_date"], brief_date)

    def test_daily_brief_job_generates_spanish_and_english(self) -> None:
        with (
            patch.object(web_services, "refresh_feed", return_value={"ok": True}) as refresh,
            patch("src.processor.ejecutar_procesamiento", return_value={"macro_resumen_generado": True, "lang": "es"}) as spanish,
            patch.object(web_services, "generate_english_daily_brief_job", return_value={"macro_resumen_generado": True, "lang": "en"}) as english,
        ):
            result = web_services.generate_daily_brief_job()

        refresh.assert_called_once()
        spanish.assert_called_once()
        english.assert_called_once()
        self.assertEqual(result["spanish"]["lang"], "es")
        self.assertEqual(result["english"]["lang"], "en")

    def test_english_archive_starts_backfill_for_missing_english_brief(self) -> None:
        today = date(2026, 7, 8)
        self.add_brief(date(2026, 7, 7), "Resumen español")

        with patch.object(web_services, "ensure_english_daily_brief", return_value=True) as ensure:
            result = web_services.get_past_daily_briefs(today=today, lang="en")

        self.assertEqual(result["items"], [])
        ensure.assert_called_once_with(background=True, brief_date=date(2026, 7, 7))

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
            response = TestClient(web_app.app).get("/api/feed?lang=en&prioritized_fuentes=OpenAI%20Blog")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 0)
        self.assertEqual(get_feed.call_args.kwargs["lang"], "en")
        self.assertEqual(get_feed.call_args.kwargs["prioritized_fuentes"], ["OpenAI Blog"])

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

    def test_health_route_reports_ready_runtime(self) -> None:
        from fastapi.testclient import TestClient
        import web_app

        class FakeScheduler:
            running = True

            def get_job(self, job_id: str):
                if job_id in {web_app.REFRESH_JOB_ID, web_app.DAILY_BRIEF_JOB_ID}:
                    return type("FakeJob", (), {"next_run_time": None})()
                return None

        web_app.app.state.scheduler = FakeScheduler()
        with (
            patch.object(web_app, "SERVERLESS_RUNTIME", False),
            patch.object(web_app.web_services, "check_database_connection"),
            patch.object(web_app.web_services, "get_refresh_status", return_value={"last_error": None}),
        ):
            response = TestClient(web_app.app).get("/api/health")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertTrue(response.json()["checks"]["database"])
        self.assertTrue(response.json()["checks"]["scheduler_running"])

    def test_health_route_fails_when_scheduler_has_last_error(self) -> None:
        from fastapi.testclient import TestClient
        import web_app

        class FakeScheduler:
            running = True

            def get_job(self, job_id: str):
                if job_id in {web_app.REFRESH_JOB_ID, web_app.DAILY_BRIEF_JOB_ID}:
                    return type("FakeJob", (), {"next_run_time": None})()
                return None

        web_app.app.state.scheduler = FakeScheduler()
        with (
            patch.object(web_app, "SERVERLESS_RUNTIME", False),
            patch.object(web_app.web_services, "check_database_connection"),
            patch.object(web_app.web_services, "get_refresh_status", return_value={"last_error": "refresh failed"}),
        ):
            response = TestClient(web_app.app).get("/api/health")

        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.json()["ok"])
        self.assertIn("refresh failed", response.json()["errors"][0])

    def test_health_route_allows_serverless_without_scheduler(self) -> None:
        from fastapi.testclient import TestClient
        import web_app

        web_app.app.state.scheduler = None
        with (
            patch.object(web_app, "SERVERLESS_RUNTIME", True),
            patch.object(web_app.web_services, "check_database_connection"),
            patch.object(web_app.web_services, "get_refresh_status", return_value={"last_error": None}),
        ):
            response = TestClient(web_app.app).get("/api/health")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertTrue(response.json()["serverless_runtime"])
        self.assertTrue(response.json()["checks"]["scheduler_running"])

    def test_cron_refresh_requires_vercel_cron_headers_in_serverless(self) -> None:
        from fastapi.testclient import TestClient
        import web_app

        with (
            patch.object(web_app, "SERVERLESS_RUNTIME", True),
            patch.object(web_app.web_services, "refresh_feed") as refresh_feed,
        ):
            response = TestClient(web_app.app).get("/api/cron/refresh")

        self.assertEqual(response.status_code, 403)
        refresh_feed.assert_not_called()

    def test_cron_refresh_runs_for_vercel_cron_request(self) -> None:
        from fastapi.testclient import TestClient
        import web_app

        with (
            patch.object(web_app, "SERVERLESS_RUNTIME", True),
            patch.object(web_app.web_services, "refresh_feed", return_value={"ok": True}) as refresh_feed,
            patch.object(web_app.web_services, "ensure_daily_brief_catchup", return_value=True) as catchup,
        ):
            response = TestClient(web_app.app).get(
                "/api/cron/refresh",
                headers={
                    "user-agent": "vercel-cron/1.0",
                    "x-vercel-cron-schedule": "0 * * * *",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(response.json()["schedule"], "0 * * * *")
        self.assertTrue(response.json()["daily_brief_catchup_started"])
        refresh_feed.assert_called_once()
        catchup.assert_called_once_with(background=False)

    def test_cron_daily_brief_requires_vercel_cron_headers_in_serverless(self) -> None:
        from fastapi.testclient import TestClient
        import web_app

        with (
            patch.object(web_app, "SERVERLESS_RUNTIME", True),
            patch.object(web_app.web_services, "generate_daily_brief_job") as generate,
        ):
            response = TestClient(web_app.app).get("/api/cron/daily-brief")

        self.assertEqual(response.status_code, 403)
        generate.assert_not_called()

    def test_cron_daily_brief_runs_for_vercel_cron_request(self) -> None:
        from fastapi.testclient import TestClient
        import web_app

        with (
            patch.object(web_app, "SERVERLESS_RUNTIME", True),
            patch.object(
                web_app.web_services,
                "generate_daily_brief_job",
                return_value={"spanish": {"ok": True}, "english": {"ok": True}},
            ) as generate,
        ):
            response = TestClient(web_app.app).get(
                "/api/cron/daily-brief",
                headers={
                    "user-agent": "vercel-cron/1.0",
                    "x-vercel-cron-schedule": "0 11 * * *",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(response.json()["schedule"], "0 11 * * *")
        self.assertEqual(response.json()["spanish"], {"ok": True})
        self.assertEqual(response.json()["english"], {"ok": True})
        generate.assert_called_once()

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
            self.assertEqual(str(scheduler.get_job(web_app.REFRESH_JOB_ID).trigger), "interval[1:00:00]")
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
        self.assertIn("feedAbortController?.abort()", script)
        self.assertIn('error.name !== "AbortError"', script)

    def test_search_enter_submits_query(self) -> None:
        script = Path("static/app.js").read_text(encoding="utf-8")

        self.assertIn("function submitSearch()", script)
        self.assertIn('event.key !== "Enter"', script)
        self.assertIn("event.preventDefault()", script)
        input_handler = script.split('search.addEventListener("input"', maxsplit=1)[1].split('search.addEventListener("keydown"', maxsplit=1)[0]
        self.assertIn("loadSuggestions();", input_handler)
        self.assertNotIn("state.query =", input_handler)
        self.assertNotIn("loadAll();", input_handler)
        self.assertNotIn("setTimeout", input_handler)

    def test_search_suggestions_abort_stale_requests(self) -> None:
        script = Path("static/app.js").read_text(encoding="utf-8")

        self.assertIn("function hideSuggestions()", script)
        self.assertIn("let suggestionAbortController = null", script)
        self.assertIn("suggestionAbortController?.abort()", script)
        self.assertIn("requestId !== suggestionRequestId", script)
        self.assertIn('document.addEventListener("click"', script)
        self.assertIn('event.target instanceof Element && event.target.closest(".search")', script)
        self.assertIn("hideSuggestions();", script)

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
        self.assertIn("Fuentes", template)
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
        workspace_nav = template.split('class="sidebar-section mode-nav"', maxsplit=1)[1].split("</nav>", maxsplit=1)[0]
        feed_controls = template.split('class="sidebar-section feed-controls"', maxsplit=1)[1].split("</div>\n    </form>", maxsplit=1)[0]
        sidebar_preferences = template.split('class="sidebar-theme-section preferences-section"', maxsplit=1)[1].split("</aside>", maxsplit=1)[0]
        self.assertNotIn("Espacio de trabajo", workspace_nav)
        self.assertNotIn("Controles del feed", feed_controls)
        self.assertNotIn("Preferencias", sidebar_preferences)
        self.assertNotIn("data-date-mode-label", template)
        self.assertNotIn("Artículos, repositorios, temas y búsqueda en vivo.", workspace_nav)
        self.assertNotIn("Resumen ejecutivo de hoy y últimos 7 días.", workspace_nav)
        self.assertNotIn("Artículos y repositorios guardados.", workspace_nav)
        self.assertIn("últimos 30 días", script)
        self.assertIn("previous 30 days", script)
        self.assertNotIn("últimos 7 días", script)
        self.assertNotIn("previous 7 days", script)
        self.assertIn("loadDailyBriefs", script)
        self.assertIn("let dailyBriefRequestId = 0", script)
        self.assertIn("const requestId = ++dailyBriefRequestId", script)
        self.assertIn("const requestLanguage = state.language", script)
        self.assertIn('requestLanguage !== state.language || state.view !== "briefs"', script)
        self.assertIn("if (requestId === dailyBriefRequestId)", script)
        self.assertIn("loadFavorites", script)
        self.assertIn('fetchJson(withLanguage("/api/brief"))', script)
        self.assertIn("/api/daily-briefs", script)
        self.assertNotIn("formatDate(data.fecha_generacion)", script)
        self.assertNotIn("formatDate(item.fecha_generacion)", script)
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
        self.assertIn("const summaryRequests = new Map()", script)
        self.assertIn('"article.generating": "Generating..."', script)
        self.assertIn("function setSummaryLoading", script)
        self.assertIn("if (summaryRequests.has(articleId))", script)
        self.assertIn("summaryRequests.delete(articleId)", script)
        self.assertNotIn('"status.generatingSummary"', script)
        generate_summary_block = script.split("async function generateSummary", maxsplit=1)[1].split("async function toggleFavorite", maxsplit=1)[0]
        self.assertNotIn("setStatus(i18n(\"status.generatingSummary\"))", generate_summary_block)
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
        self.assertIn("/static/app.js?v=brief-meta-v1", template)
        self.assertIn("/static/app.css?v=brief-meta-v1", template)
        self.assertIn('placeholder="Buscar"', template)
        self.assertIn('"search.placeholder": "Buscar"', script)
        self.assertIn('"search.placeholder": "Search"', script)
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
        feed_controls = template.split('class="sidebar-section feed-controls"', maxsplit=1)[1].split("</div>\n    </form>", maxsplit=1)[0]
        self.assertNotIn('data-i18n="filters.date"', feed_controls)
        self.assertIn('data-i18n-aria-label="filters.date"', feed_controls)
        self.assertNotIn('id="topbar-subtitle"', template)
        self.assertIn("topbarTitle.textContent", script)
        self.assertIn("function updateTopbarTitle()", script)
        self.assertIn("formatFeedDate(selectedDate)", script)
        self.assertIn('params.set("fecha", "all")', script)
        self.assertIn("function syncDateMode()", script)
        self.assertIn("dateInput.disabled = allDates", script)
        self.assertNotIn("dateModeLabel", script)
        self.assertIn(".date-all-option", styles)
        filters_styles = styles.split("\n.filters {", maxsplit=1)[1].split("}", maxsplit=1)[0]
        self.assertIn("margin-bottom: 22px", filters_styles)
        self.assertIn("input:disabled", styles)
        self.assertNotIn('"brief.subtitle"', script)
        self.assertIn('"brief.schedule": "The daily brief is generated every day at 8:00."', script)
        self.assertIn('"brief.schedule": "El brief diario se genera todos los días a las 8:00."', script)
        self.assertIn("brief-schedule-note", script)
        self.assertIn(".brief-schedule-note", styles)
        self.assertIn('"brief.generating": "Today\'s brief is being generated.', script)
        self.assertNotIn(".topbar-subtitle", styles)
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
        self.assertIn("function expandableText", script)
        self.assertIn("function toggleExpandableText", script)
        self.assertIn("function syncExpandableTextLabels", script)
        self.assertIn("data-full-text", script)
        self.assertIn("data-short-text", script)
        self.assertIn("expandableAvailable", script)
        self.assertIn("data-expandable-text", script)
        self.assertIn("expandable-text", styles)
        self.assertIn('.expandable-text[data-expandable-available="true"] small', styles)
        self.assertIn(".article-summary[aria-expanded=\"false\"] span", styles)
        self.assertIn(".brief-text[aria-expanded=\"false\"] span", styles)
        self.assertNotIn("article-reason", script)
        self.assertNotIn("item.selection_reason", script)
        self.assertNotIn(".article-reason", styles)
        self.assertIn(".article.has-visual .article-main", styles)
        self.assertIn("grid-template-columns: minmax(0, 1fr) minmax(190px, 240px)", styles)
        self.assertIn('${starMetric}', script)
        self.assertIn('const visualRail = mediaPreview', script)
        self.assertIn('${mediaPreview}</aside>', script)
        self.assertIn('${mediaPreview ? " has-media" : ""}', script)
        self.assertIn("max-width: min(220px, 100%)", styles)
        self.assertNotIn("grid-template-columns: minmax(0, 1fr) 112px", styles)
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

    def test_source_preferences_replace_user_facing_system_status(self) -> None:
        template = Path("templates/index.html").read_text(encoding="utf-8")
        script = Path("static/app.js").read_text(encoding="utf-8")
        styles = Path("static/app.css").read_text(encoding="utf-8")

        self.assertNotIn('id="system-status-button"', template)
        self.assertNotIn('data-view-target="system"', template)
        self.assertNotIn('id="refresh-status"', template)
        self.assertNotIn('id="system-status"', template)
        self.assertNotIn("Resumen operativo", template)
        self.assertNotIn("Estado del sistema", template)
        workspace_nav = template.split('class="sidebar-section mode-nav"', maxsplit=1)[1].split("</nav>", maxsplit=1)[0]
        preferences_section = template.split('class="sidebar-theme-section preferences-section"', maxsplit=1)[1].split("</aside>", maxsplit=1)[0]
        self.assertNotIn('data-view-target="sources"', workspace_nav)
        self.assertIn('data-view-target="sources"', preferences_section)
        self.assertNotIn("3 modos", workspace_nav)
        self.assertNotIn("3 modes", script)
        self.assertNotIn("Preferencias guardadas para filtros y ranking.", preferences_section)
        self.assertNotIn("Cambiar tema", preferences_section)
        self.assertIn('data-view-target="sources"', template)
        self.assertIn('id="source-preferences"', template)
        self.assertIn("/static/app.css?v=brief-meta-v1", template)
        source_preferences = template.split('id="source-preferences"', maxsplit=1)[1].split("</section>", maxsplit=1)[0]
        self.assertNotIn('data-i18n="sources.kicker"', source_preferences)
        self.assertNotIn('data-i18n="sources.title"', source_preferences)
        self.assertNotIn('data-i18n="sources.description"', source_preferences)
        self.assertNotIn('data-i18n="sources.role.', source_preferences)
        self.assertIn('class="source-preference-link"', source_preferences)
        self.assertIn('href="{{ source_links[source] }}"', source_preferences)
        self.assertIn('class="source-apply-button"', template)
        self.assertIn('class="source-apply-icon"', template)
        self.assertIn('data-source-apply-label', template)
        self.assertIn(">Aplicar</span>", template)
        self.assertNotIn("Aplicar a filtros", template)
        self.assertIn("Restablecer", template)
        self.assertIn('data-source-preference="{{ source }}"', template)
        self.assertIn('data-source-value="prioritized"', template)
        self.assertIn('data-source-value="normal"', template)
        self.assertIn('data-source-value="hidden"', template)
        self.assertIn('"nav.sources": "Sources"', script)
        self.assertNotIn('"nav.sourcesDesc"', script)
        self.assertNotIn('"nav.todayDesc"', script)
        self.assertNotIn('"prefs.switchTheme"', script)
        self.assertNotIn('"prefs.themeDesc"', script)
        self.assertNotIn('"mobile.content"', script)
        self.assertNotIn('"sources.mobileDesc"', script)
        self.assertNotIn('"sources.description"', script)
        self.assertNotIn('"sources.kicker"', script)
        self.assertNotIn('"system.status"', script)
        self.assertNotIn('"system.loadError"', script)
        self.assertIn('"sources.apply": "Apply"', script)
        self.assertIn('"sources.applied": "Applied"', script)
        self.assertIn('"favorites.emptyBody": "Use the heart button on any article to save it here for follow-up."', script)
        self.assertIn('"sources.role.OpenAIBlog": "Official OpenAI and AI updates."', script)
        self.assertIn('SOURCE_PREFERENCE_STORAGE_KEY = "newser.sourcePreferences"', script)
        self.assertIn("function defaultSourcePreferences()", script)
        self.assertIn("function applySourcePreferencesToFilters()", script)
        self.assertIn("appliedSourcePreferences", script)
        self.assertIn("pendingLoad: false", script)
        self.assertIn("state.pendingLoad = true", script)
        self.assertIn("if (state.pendingLoad)", script)
        self.assertIn("const hasRenderedFeed = Boolean(feed.children.length)", script)
        self.assertIn("if (!hasRenderedFeed) document.body.classList.add(\"is-loading\")", script)
        self.assertIn("state.appliedSourcePreferences = { ...state.sourcePreferences }", script)
        self.assertIn("saveSourcePreferences();", script)
        self.assertIn("function syncSourceFilterVisibility()", script)
        self.assertIn("function visibleMultiSelectOptions(root)", script)
        self.assertIn("state.appliedSourcePreferences[input.value] === \"hidden\"", script)
        self.assertIn("input.disabled = hidden", script)
        self.assertIn("else if (wasHidden)", script)
        self.assertIn("if (row) row.hidden = hidden", script)
        self.assertIn('filter((input) => !input.disabled && !input.closest("[hidden]"))', script)
        self.assertIn("visibleMultiSelectOptions(root).forEach", script)
        self.assertIn("loadAll();", script)
        self.assertIn("loadSuggestions();", script)
        self.assertIn("function showSourceApplyFeedback(button)", script)
        self.assertIn('button.classList.add("is-confirmed")', script)
        self.assertIn("function resetSourcePreferences()", script)
        self.assertIn('button[data-source-value="prioritized"][aria-pressed="true"]', styles)
        self.assertIn('button[data-source-value="normal"][aria-pressed="true"]', styles)
        self.assertIn('button[data-source-value="hidden"][aria-pressed="true"]', styles)
        self.assertIn("--source-priority-bg", styles)
        self.assertIn("--source-hidden-bg", styles)
        self.assertIn("--radius-sm: 8px", styles)
        self.assertIn("--radius-md: 10px", styles)
        self.assertIn("--control-height: 40px", styles)
        self.assertNotIn('button[aria-pressed="true"]::before', styles)
        self.assertNotIn("--source-priority-tint", styles)
        self.assertNotIn("--source-priority-muted", styles)
        self.assertNotIn("--source-normal-bg", styles)
        self.assertNotIn("--source-hidden-tint", styles)
        self.assertNotIn("--source-hidden-muted", styles)
        self.assertIn('params.append("prioritized_fuentes", source)', script)
        self.assertIn('item.source_preference === "prioritized"', script)
        self.assertNotIn("loadSystemStatus", script)
        self.assertNotIn('fetchJson(withLanguage("/api/stats"))', script)
        self.assertNotIn('fetchJson(withLanguage("/api/refresh-status"))', script)
        self.assertIn("view-sources", script)
        sources_hide_block = styles.split("body.view-sources .today-only,", maxsplit=1)[1].split("{", maxsplit=1)[0]
        self.assertIn("body.view-sources .feed-controls", sources_hide_block)
        self.assertIn(".preference-nav-button", styles)
        source_hero_styles = styles.split(".source-preferences-hero {", maxsplit=1)[1].split("}", maxsplit=1)[0]
        self.assertIn("display: flex", source_hero_styles)
        self.assertIn("justify-content: flex-start", source_hero_styles)
        self.assertNotIn("grid-template-columns", source_hero_styles)
        preferences_styles = styles.split(".preferences-section {", maxsplit=1)[1].split("}", maxsplit=1)[0]
        self.assertIn("background: var(--panel-translucent)", preferences_styles)
        self.assertIn("border: 1px solid var(--line-strong)", preferences_styles)
        self.assertIn("display: grid", preferences_styles)
        self.assertIn("gap: 9px", preferences_styles)
        self.assertIn(".source-preferences-view", styles)
        self.assertIn(".source-apply-button.is-confirmed", styles)
        self.assertIn(".source-preference-link", styles)
        self.assertIn(".source-preference-toggle", styles)
        self.assertIn(".source-preference-badge", styles)

    def test_hot_topics_render_multi_source_details(self) -> None:
        script = Path("static/app.js").read_text(encoding="utf-8")
        styles = Path("static/app.css").read_text(encoding="utf-8")

        self.assertIn('"topics.empty": "No multi-source hot topics for this date yet."', script)
        self.assertIn('document.querySelector("#topics-panel")', script)
        self.assertIn("panel.hidden = true", script)
        self.assertIn("panel.hidden = false", script)
        self.assertNotIn('hotTopics.innerHTML = `<div class="empty">${i18n("topics.empty")}</div>`', script)
        self.assertIn("topic.sources", script)
        self.assertIn("topic.supporting_items", script)
        self.assertIn('"topics.supporting": "Supporting articles"', script)
        self.assertIn("function hideHotTopics()", script)
        self.assertIn("hideHotTopics();\n    feedAbortController?.abort();", script)
        self.assertIn("setSearchMode(searchActive);\n  hideHotTopics();", script)
        self.assertIn("hideHotTopics();\n    return;", script)
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
        self.assertIn('html[data-theme="light"] .brand img', styles)
        self.assertIn('html[data-theme="light"] .mobile-brand img', styles)
        self.assertIn("drop-shadow(0 1px 0 rgba(23, 33, 49, 0.72))", styles)
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
        self.assertNotIn('id="mobile-view-label"', template)
        self.assertNotIn('id="mobile-theme-toggle"', template)
        self.assertIn('id="mobile-drawer-backdrop"', template)
        self.assertIn('class="mobile-tabbar"', template)
        self.assertIn('data-view-target="more"', template)
        self.assertIn('id="mobile-more"', template)
        mobile_more = template.split('id="mobile-more"', maxsplit=1)[1].split('id="source-preferences"', maxsplit=1)[0]
        self.assertNotIn("Feed filters", mobile_more)
        self.assertNotIn("data-mobile-open-drawer", mobile_more)
        self.assertNotIn("mobile-more-hero", mobile_more)
        self.assertNotIn("Estado del sistema", mobile_more)
        self.assertNotIn("Contenido", mobile_more)
        preferences_card = mobile_more.split('data-i18n="prefs.title"', maxsplit=1)[1]
        self.assertIn('data-view-target="sources"', preferences_card)
        self.assertIn("Fuentes", mobile_more)
        self.assertIn("Apariencia", mobile_more)
        self.assertNotIn("About", mobile_more)
        self.assertNotIn("IT News Trend Analyzer for AI", mobile_more)
        self.assertIn("mobile-more-theme-toggle", mobile_more)
        self.assertIn("mobile-theme-toggle-control", mobile_more)
        self.assertIn('data-theme-choice="light"', mobile_more)
        self.assertIn('data-theme-choice="dark"', mobile_more)
        self.assertIn('class="sr-only" data-theme-state', mobile_more)
        self.assertNotIn("sidebar-theme-icon", mobile_more)
        self.assertNotIn("sidebar-theme-copy", mobile_more)
        self.assertNotIn("Cambiar entre modo oscuro y claro.", mobile_more)
        self.assertNotIn("mobile-more-theme-indicator", mobile_more)
        self.assertIn("function initMobileShell()", script)
        self.assertIn("function openMobileDrawer()", script)
        self.assertIn("function closeMobileDrawer()", script)
        self.assertIn('window.matchMedia("(max-width: 900px)")', script)
        self.assertIn("mobileMenuToggle.hidden = !todayActive", script)
        self.assertNotIn("mobileViewLabel", script)
        self.assertNotIn('"nav.todayShort"', script)
        self.assertNotIn("data-mobile-open-drawer", script)
        self.assertIn('state.view === "more"', script)
        self.assertIn("view-more", script)
        self.assertIn("mobile-drawer-open", script)
        self.assertIn("@media (max-width: 900px)", styles)
        self.assertIn(".mobile-appbar", styles)
        self.assertIn(".mobile-tabbar", styles)
        self.assertIn(".mobile-more-view", styles)
        self.assertIn(".mobile-more-theme-toggle", styles)
        self.assertIn(".mobile-theme-toggle-control", styles)
        self.assertIn('span[data-theme-choice="light"]', styles)
        self.assertIn('span[data-theme-choice="dark"]', styles)
        self.assertIn(".sr-only", styles)
        self.assertIn("const themeStateLabels", script)
        self.assertIn("[data-theme-state]", script)
        self.assertIn(".mobile-drawer-backdrop", styles)
        self.assertIn(".sidebar-theme-section", styles)
        mobile_styles = styles.rsplit("@media (max-width: 900px)", maxsplit=1)[1]
        self.assertIn(".mode-nav", mobile_styles)
        self.assertIn("display: none", mobile_styles.split(".mode-nav", maxsplit=1)[1].split("}", maxsplit=1)[0])
        self.assertIn(".sidebar-theme-section", mobile_styles)
        self.assertIn("display: none", mobile_styles.split(".sidebar-theme-section", maxsplit=1)[1].split("}", maxsplit=1)[0])
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
        self.assertIn("function formatScore", script)
        self.assertIn("github-star-count", script)
        self.assertIn("<svg viewBox", script)
        self.assertIn("article-heading", script)
        self.assertIn("article-visual", script)
        self.assertIn("article-star-metric", script)
        self.assertIn("renderTitleLabel(item.title)", script)
        self.assertIn("formatScore(item.score)", script)
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
