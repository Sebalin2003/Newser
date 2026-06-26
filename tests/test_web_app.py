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

from src.database import Base, MacroResumen, Noticia
from src import database, web_services


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

        self.session_patch = patch.object(web_services, "get_session", temporary_session)
        self.session_patch.start()

    def tearDown(self) -> None:
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
    ) -> None:
        now = datetime.now(timezone.utc)
        with self.session_factory() as session:
            session.add(
                Noticia(
                    id=article_id,
                    titulo=title,
                    url=f"https://example.test/{article_id}",
                    fuente=source,
                    descripcion_original=f"{title} description",
                    resumen_ia="Resumen no disponible",
                    area_matcheada=area,
                    fecha_publicacion=published_at or now,
                    fecha_ingesta=now,
                    selected_score=score,
                    tags_json=json.dumps(["agents"]),
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

    def test_hot_topics_require_three_distinct_sources_and_pick_highest_score(self) -> None:
        today = datetime.now(timezone.utc).date().isoformat()
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

    def test_feed_filters_do_not_change_date_level_hot_topics(self) -> None:
        today = datetime.now(timezone.utc).date().isoformat()
        self.add_article("openai-r", "OpenAI agent launch details", "Reuters", "ai_agents", 80)
        self.add_article("openai-o", "OpenAI agent launch details for teams", "OpenAI Blog", "ai_agents", 90)
        self.add_article("openai-h", "OpenAI agent launch details discussion", "Hacker News", "ai_agents", 75)
        self.add_article("visible-only", "Different GitHub repository", "GitHub Trending", "developer_tools", 99)

        result = web_services.get_feed(fecha=today, fuentes=["GitHub Trending"])

        self.assertEqual([item["id"] for item in result["items"]], ["visible-only"])
        self.assertEqual(result["hot_topics"][0]["topic"], "OpenAI")
        self.assertEqual(result["hot_topics"][0]["source_count"], 3)

    def test_hot_topics_sort_by_source_count_then_score(self) -> None:
        today = datetime.now(timezone.utc).date()
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
        today = datetime.now(timezone.utc).date()
        self.add_article("only-one", "OpenAI standalone update", "OpenAI Blog", "ai_agents", 90)
        self.add_article("only-two-a", "Security incident report", "Reuters", "cybersecurity", 80)
        self.add_article("only-two-b", "Security incident analysis", "Hacker News", "cybersecurity", 81)

        self.assertEqual(web_services.get_hot_topics(today), [])

    def test_brief_returns_structured_json_when_available(self) -> None:
        today = datetime.now(timezone.utc).date()
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

    def test_suggestions_require_two_characters_and_limit_results(self) -> None:
        today = datetime.now(timezone.utc).date().isoformat()
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

    def test_favorite_columns_are_declared(self) -> None:
        columns = {column["name"] for column in inspect(self.engine).get_columns("noticias")}

        self.assertIn("is_favorite", columns)
        self.assertIn("favorited_at", columns)

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

        with patch.object(web_app.web_services, "get_feed", return_value={"items": [], "count": 0, "hot_topics": []}):
            response = TestClient(web_app.app).get("/api/feed")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 0)

    def test_summary_route_returns_clear_error_status(self) -> None:
        from fastapi.testclient import TestClient
        import web_app

        with patch.object(
            web_app.web_services,
            "generate_summary",
            return_value={"ok": False, "reason": "GEMINI_API_KEY is missing."},
        ):
            response = TestClient(web_app.app).post("/api/articles/article-1/summary")

        self.assertEqual(response.status_code, 400)
        self.assertIn("GEMINI_API_KEY", response.json()["reason"])

    def test_refresh_status_route_returns_stable_json(self) -> None:
        from fastapi.testclient import TestClient
        import web_app

        with patch.object(web_app.web_services, "get_refresh_status", return_value={"updating": False}):
            response = TestClient(web_app.app).get("/api/refresh-status")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"updating": False})

    def test_daily_briefs_route_returns_items(self) -> None:
        from fastapi.testclient import TestClient
        import web_app

        with patch.object(web_app.web_services, "get_past_daily_briefs", return_value={"items": []}):
            response = TestClient(web_app.app).get("/api/daily-briefs")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"items": []})

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
        finally:
            if scheduler.running:
                scheduler.shutdown(wait=False)


class WebUiStaticTests(unittest.TestCase):
    def test_new_filter_controls_replace_refresh_and_order_select(self) -> None:
        template = Path("templates/index.html").read_text(encoding="utf-8")
        script = Path("static/app.js").read_text(encoding="utf-8")

        self.assertIn("data-multiselect", template)
        self.assertIn("Select all", template)
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

    def test_daily_briefs_mode_ui_is_present(self) -> None:
        template = Path("templates/index.html").read_text(encoding="utf-8")
        script = Path("static/app.js").read_text(encoding="utf-8")
        styles = Path("static/app.css").read_text(encoding="utf-8")

        self.assertIn("Today&rsquo;s Updates", template)
        self.assertIn(r"Today\u2019s Updates", script)
        self.assertIn('aria-label="Today’s Updates"', template)
        self.assertIn("Daily Briefs", template)
        self.assertIn("Favorites", template)
        self.assertIn("Workspace", template)
        self.assertIn("Feed controls", template)
        self.assertIn("System status", template)
        self.assertIn('data-view-target="today"', template)
        self.assertIn('data-view-target="briefs"', template)
        self.assertIn('data-view-target="favorites"', template)
        self.assertIn('id="daily-briefs"', template)
        self.assertIn('id="favorites"', template)
        self.assertIn('id="favorites-feed"', template)
        self.assertIn("favorites-feed-list", template)
        self.assertIn("Executive summary", template)
        self.assertIn("Previous daily briefs", template)
        self.assertIn("previous 7 days", template)
        self.assertIn("loadDailyBriefs", script)
        self.assertIn("loadFavorites", script)
        self.assertIn('fetchJson("/api/brief")', script)
        self.assertIn("/api/daily-briefs", script)
        self.assertIn("/api/favorites", script)
        self.assertIn("/favorite", script)
        self.assertIn("favorite-button", script)
        self.assertIn("Add to favorites", script)
        self.assertIn("Remove from favorites", script)
        favorite_markup = script.split('const favoriteButton = `', maxsplit=1)[1].split("  return `", maxsplit=1)[0]
        self.assertNotIn("<span>", favorite_markup)
        self.assertIn("M8 13.8", script)
        self.assertIn("Use the heart button", script)
        self.assertIn("/static/app.js?v=selected-date-title-v1", template)
        self.assertIn("/static/app.css?v=selected-date-title-v1", template)
        topbar = template.split('class="topbar"', maxsplit=1)[1].split('id="status"', maxsplit=1)[0]
        self.assertNotIn("Command center", topbar)
        self.assertIn('id="topbar-date"', template)
        self.assertIn("topbarTitle.textContent", script)
        self.assertIn("function updateTopbarTitle()", script)
        self.assertIn("formatFeedDate(selectedDate)", script)
        self.assertNotIn("topbarEyebrow", script)
        self.assertIn('search.value = ""', script)
        self.assertIn("archive-empty", script)
        self.assertIn(".mode-nav", styles)
        self.assertIn(".topbar-date", styles)
        archive_window_styles = styles.split(".archive-window {", maxsplit=1)[1].split("}", maxsplit=1)[0]
        self.assertIn("text-align: center", archive_window_styles)
        self.assertIn(".favorites-view", styles)
        self.assertIn(".favorites-feed-list", styles)
        self.assertIn(".favorite-button", styles)
        self.assertIn("border-radius: 50%", styles)
        self.assertIn("background: rgba(255, 80, 134, 0.13)", styles)
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
        self.assertIn('id="system-status"', template)
        self.assertIn("Operations overview", template)
        self.assertIn('id="system-health"', template)
        self.assertIn('id="system-metrics"', template)
        self.assertIn('id="source-breakdown"', template)
        self.assertIn('state.view === "system"', script)
        self.assertIn("loadSystemStatus", script)
        self.assertIn('fetchJson("/api/stats")', script)
        self.assertIn('fetchJson("/api/refresh-status")', script)
        self.assertIn("renderSourceBreakdown", script)
        self.assertIn("view-system", script)
        self.assertIn(".system-status-view", styles)
        self.assertIn(".system-health-grid", styles)
        self.assertIn(".source-breakdown", styles)

    def test_hot_topics_render_multi_source_details(self) -> None:
        script = Path("static/app.js").read_text(encoding="utf-8")
        styles = Path("static/app.css").read_text(encoding="utf-8")

        self.assertIn("No multi-source hot topics for this date yet.", script)
        self.assertIn("topic.sources", script)
        self.assertIn("topic.supporting_items", script)
        self.assertIn("Supporting articles", script)
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
        self.assertIn("IT News Trend Analyzer", brand_block)
        self.assertIn("width: 92px", styles)
        self.assertIn('id="sidebar-toggle"', template)
        self.assertIn('class="nav-icon"', template)
        self.assertNotIn("data-short=", template)
        self.assertIn("body.sidebar-collapsed .nav-button > span:not(.nav-icon)", styles)
        self.assertIn("body.sidebar-collapsed .nav-icon", styles)
        self.assertIn(".nav-button[data-view-target=\"favorites\"] .nav-icon path", styles)
        self.assertIn("function setSidebarCollapsed", script)
        self.assertIn("function initSidebar", script)
        self.assertIn("newser.sidebarCollapsed.mobile", script)
        self.assertIn("newser.sidebarCollapsed.desktop", script)
        self.assertIn("const shouldCollapse = saved === null ? isMobile", script)
        self.assertIn("body.sidebar-collapsed", styles)
        self.assertIn("grid-template-columns: 92px minmax(0, 1fr)", styles)
        self.assertIn("height: calc(72px + env(safe-area-inset-top, 0px))", styles)

    def test_github_star_titles_use_svg_icon(self) -> None:
        script = Path("static/app.js").read_text(encoding="utf-8")
        styles = Path("static/app.css").read_text(encoding="utf-8")

        self.assertIn("function renderTitleLabel", script)
        self.assertIn("function splitStarTitle", script)
        self.assertIn("function renderStarCount", script)
        self.assertIn("github-star-count", script)
        self.assertIn("<svg viewBox", script)
        self.assertIn("article-title-row", script)
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
        self.assertIn("grid-template-columns: 300px minmax(0, 1fr)", styles)
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
