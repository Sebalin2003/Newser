from __future__ import annotations

import unittest
from contextlib import contextmanager
from datetime import date, datetime as real_datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch


class TestSchema(unittest.TestCase):
    def test_macro_resumen_has_brief_json_column(self) -> None:
        from sqlalchemy import inspect

        from src.database import engine, init_db

        init_db()
        columns = {column["name"] for column in inspect(engine).get_columns("macro_resumenes")}

        self.assertIn("brief_json", columns)

    def test_noticias_has_selected_score_columns(self) -> None:
        from sqlalchemy import inspect

        from src.database import engine, init_db

        init_db()
        columns = {column["name"] for column in inspect(engine).get_columns("noticias")}

        self.assertIn("selected_score", columns)
        self.assertIn("score_components_json", columns)
        self.assertIn("tags_json", columns)
        self.assertIn("selection_reason", columns)
        self.assertIn("discussion_url", columns)


class TestArticleScoring(unittest.TestCase):
    def test_ai_story_outscores_generic_startup_story(self) -> None:
        from datetime import datetime, timezone

        from src.scoring import calculate_item_score

        now = datetime(2026, 6, 18, 12, tzinfo=timezone.utc)
        ai_item = {
            "titulo": "OpenAI releases new agent model for developers",
            "descripcion_original": "The model improves coding workflows.",
            "fuente": "OpenAI Blog",
            "area_matcheada": "inteligencia_artificial",
            "fecha_ingesta": now,
        }
        generic_item = {
            "titulo": "Startup raises seed funding for marketplace app",
            "descripcion_original": "The company plans to hire.",
            "fuente": "Reuters",
            "area_matcheada": "startups_tecnologia",
            "fecha_ingesta": now,
        }

        self.assertGreater(
            calculate_item_score(ai_item, now=now).selected_score,
            calculate_item_score(generic_item, now=now).selected_score,
        )

    def test_trusted_source_boosts_score(self) -> None:
        from datetime import datetime, timezone

        from src.scoring import calculate_item_score

        now = datetime(2026, 6, 18, 12, tzinfo=timezone.utc)
        base = {
            "titulo": "AI developer tool improves inference workflow",
            "descripcion_original": "A technical release for model operations.",
            "area_matcheada": "inteligencia_artificial",
            "fecha_ingesta": now,
        }

        trusted = calculate_item_score({**base, "fuente": "GitHub Blog"}, now=now)
        unknown = calculate_item_score({**base, "fuente": "Random Blog"}, now=now)

        self.assertGreater(trusted.selected_score, unknown.selected_score)

    def test_freshness_decay_reduces_old_items(self) -> None:
        from datetime import datetime, timedelta, timezone

        from src.scoring import calculate_item_score

        now = datetime(2026, 6, 18, 12, tzinfo=timezone.utc)
        fresh = {
            "titulo": "Critical AI security vulnerability disclosed",
            "fuente": "Reuters",
            "area_matcheada": "ciberseguridad",
            "fecha_ingesta": now,
        }
        old = {**fresh, "fecha_ingesta": now - timedelta(days=5)}

        self.assertGreater(
            calculate_item_score(fresh, now=now).selected_score,
            calculate_item_score(old, now=now).selected_score,
        )


class TestFeedPublicationTime(unittest.TestCase):
    def test_formats_source_publication_time_in_utc(self) -> None:
        import app

        published_at = real_datetime(2026, 6, 19, 12, 34, tzinfo=timezone.utc)

        self.assertEqual(
            app._format_publication_time(published_at),
            "19/06/2026 12:34 UTC",
        )

    def test_handles_missing_source_publication_time(self) -> None:
        import app

        self.assertEqual(
            app._format_publication_time(None),
            "",
        )

    def test_uses_source_specific_time_labels(self) -> None:
        import app

        timestamp = real_datetime(2026, 6, 19, 12, 34, tzinfo=timezone.utc)

        self.assertEqual(
            app._feed_time_display({"Fuente": "Reuters", "Publicada": timestamp}),
            ("Publicado", "19/06/2026 12:34 UTC"),
        )
        self.assertEqual(
            app._feed_time_display({"Fuente": "GitHub Trending", "Ingestada": timestamp}),
            ("Detectado en tendencias", "19/06/2026 12:34 UTC"),
        )
        self.assertIsNone(app._feed_time_display({"Fuente": "OpenAI Blog", "Publicada": None}))


class TestAutomaticFeedRefresh(unittest.TestCase):
    def test_staleness_uses_thirty_minute_threshold(self) -> None:
        import app

        now = real_datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)

        self.assertTrue(app._is_feed_stale(None, now))
        self.assertFalse(app._is_feed_stale(now - timedelta(minutes=29), now))
        self.assertTrue(app._is_feed_stale(now - timedelta(minutes=30), now))

    def test_fresh_feed_does_not_start_background_refresh(self) -> None:
        import app

        now = real_datetime.now(timezone.utc)
        with patch.object(app, "_latest_ingested_at", return_value=now), \
             patch.object(app.threading, "Thread") as thread:
            self.assertFalse(app._ensure_feed_refresh())

        thread.assert_not_called()

    def test_concurrent_stale_entries_start_one_background_refresh(self) -> None:
        import app

        if app._feed_refresh_lock.locked():
            app._feed_refresh_lock.release()
        stale = real_datetime.now(timezone.utc) - timedelta(hours=1)
        try:
            with patch.object(app, "_latest_ingested_at", return_value=stale), \
                 patch.object(app.threading, "Thread") as thread:
                self.assertTrue(app._ensure_feed_refresh())
                self.assertTrue(app._ensure_feed_refresh())

            thread.assert_called_once()
        finally:
            if app._feed_refresh_lock.locked():
                app._feed_refresh_lock.release()

    def test_feed_refresh_does_not_call_gemini_processing(self) -> None:
        import app

        with patch.object(app, "ejecutar_ingesta") as ingest, \
             patch.object(app, "score_recent_items") as score, \
             patch.object(app, "_cargar_config", return_value={}), \
             patch.object(app, "_clear_data_caches"), \
             patch.object(app, "ejecutar_procesamiento") as process:
            app._refresh_feed_data()

        ingest.assert_called_once_with()
        score.assert_called_once_with({}, hours=24)
        process.assert_not_called()

    def test_daily_brief_refreshes_feed_before_processing(self) -> None:
        import app

        calls = []
        with patch.object(app, "_refresh_feed_data", side_effect=lambda: calls.append("refresh")), \
             patch.object(app, "ejecutar_procesamiento", side_effect=lambda: calls.append("process")), \
             patch.object(app, "_clear_data_caches"):
            app._job_daily_brief()

        self.assertEqual(calls, ["refresh", "process"])


class TestGlobalNews(unittest.TestCase):
    def test_normalize_global_item_preserves_full_published_timestamp(self) -> None:
        from src.global_news import normalize_global_item

        iso_item = normalize_global_item(
            title="OpenAI publishes a new model update",
            source="OpenAI Blog",
            url="https://openai.com/index/example/",
            published_at="2026-06-19T12:34:56Z",
        )
        rss_item = normalize_global_item(
            title="GitHub publishes an engineering update",
            source="GitHub Blog",
            url="https://github.blog/engineering/example/",
            published_at="Thu, 19 Jun 2026 09:34:56 -0300",
        )
        missing_item = normalize_global_item(
            title="Reuters technology update",
            source="Reuters",
            url="https://www.reuters.com/technology/example/",
        )

        self.assertEqual(iso_item.published_at, "2026-06-19T12:34:56+00:00")
        self.assertEqual(rss_item.published_at, "2026-06-19T12:34:56+00:00")
        self.assertIsNone(missing_item.published_at)

    def test_normalize_global_item_rejects_untrusted_source_and_dedupes_urls(self) -> None:
        from src.global_news import dedupe_global_items, normalize_global_item

        trusted = normalize_global_item(
            title="GitHub improves Copilot context handling",
            source="GitHub Blog",
            url="https://github.blog/ai-and-ml/example",
            excerpt="Copilot reduces context waste.",
            category="Developer Tools",
            score=5,
        )
        untrusted = normalize_global_item(
            title="Random rumor",
            source="Random Blog",
            url="https://example.com/rumor",
        )
        duplicate = normalize_global_item(
            title="Same story",
            source="GitHub Blog",
            url="https://github.blog/ai-and-ml/example",
            score=1,
        )

        self.assertIsNone(untrusted)
        self.assertIsNotNone(trusted)
        self.assertEqual(
            [item.url for item in dedupe_global_items([trusted, duplicate])],
            ["https://github.blog/ai-and-ml/example"],
        )

    def test_looks_like_it_story_does_not_match_ai_inside_words(self) -> None:
        from src.global_news import looks_like_it_story

        self.assertFalse(
            looks_like_it_story(
                "Brasil busca um recomeço contra o Haiti após estreia expor falhas",
                "https://www.reuters.com/sports/soccer/example/",
            )
        )
        self.assertFalse(
            looks_like_it_story(
                "ATUALIZA 2 BC corta Selic e sugere mais tempo para atingir meta de inflação",
                "https://www.reuters.com/pt/negocio/example/",
            )
        )
        self.assertTrue(
            looks_like_it_story(
                "Meta head of product for AI for work transformation is leaving",
                "https://www.reuters.com/world/meta-head-product-ai-work-transformation-2026-06-17/",
            )
        )


class TestHybridPayload(unittest.TestCase):
    def test_build_hybrid_brief_payload_limits_sources_and_preserves_urls(self) -> None:
        from src.global_news import normalize_global_item
        from src.processor import build_hybrid_brief_payload

        global_items = [
            normalize_global_item(
                title=f"Reuters story {i}",
                source="Reuters",
                url=f"https://www.reuters.com/technology/story-{i}/",
                excerpt="A relevant IT story.",
                score=20 - i,
            )
            for i in range(12)
        ]
        local_items = [
            {
                "title": f"Repo {i}",
                "source": "GitHub Trending",
                "url": f"https://github.com/x/{i}",
                "selected_score": i,
                "tags": ["Developer Tools"],
                "selection_reason": "Seleccionado por relevancia tecnica.",
            }
            for i in range(20)
        ]

        payload = build_hybrid_brief_payload(global_items, local_items, date(2026, 6, 17))

        self.assertEqual(payload["date"], "2026-06-17")
        self.assertEqual(len(payload["global_news"]), 8)
        self.assertEqual(len(payload["developer_signals"]), 7)
        self.assertEqual(len(payload["source_records"]), 15)
        self.assertTrue(payload["global_news"][0]["url"].startswith("https://www.reuters.com/"))
        self.assertEqual(payload["developer_signals"][0]["score"], 19)

    def test_gemini_failure_does_not_use_low_volume_fallback_when_articles_exist(self) -> None:
        import src.processor as processor

        with patch.object(processor, "fetch_global_news", return_value=[]), \
            patch.object(processor, "_llamar_gemini", return_value=None), \
            patch.object(processor, "_persistir_macro_resumen") as persist, \
            patch.object(processor, "get_session") as get_session:
            article = type("Article", (), {
                "titulo": "Important IT story",
                "fuente": "Reuters",
                "url": "https://www.reuters.com/example",
                "resumen_ia": "Resumen no disponible",
                "descripcion_original": "A real story exists.",
                "area_matcheada": "ciberseguridad",
                "score": 100,
                "ranking": None,
                "fecha_ingesta": None,
            })()
            session = get_session.return_value.__enter__.return_value
            query = session.query.return_value
            query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [article, article, article]
            query.filter.return_value.first.return_value = None
            processor.LAST_GEMINI_ERROR = "Gemini respondio sin cuota disponible para `gemini-2.5-flash-lite`."

            result = processor.generar_macro_resumen_dia({})

        kwargs = persist.call_args.kwargs
        self.assertEqual(kwargs["modelo"], "gemini_error")
        self.assertIn("Gemini", kwargs["texto"])
        self.assertNotIn("Bajo volumen", kwargs["texto"])
        self.assertFalse(result["uso_api"])

    def test_gemini_error_macro_summary_is_retryable(self) -> None:
        import src.processor as processor

        existing = type("ExistingMacro", (), {"modelo": "gemini_error", "texto": "old quota error"})()
        article = type("Article", (), {
            "titulo": "Important IT story",
            "fuente": "Reuters",
            "url": "https://www.reuters.com/example",
            "resumen_ia": "Resumen no disponible",
            "descripcion_original": "A real story exists.",
            "area_matcheada": "ciberseguridad",
            "score": 100,
            "ranking": None,
            "fecha_ingesta": None,
        })()

        with patch.object(processor, "fetch_global_news", return_value=[]), \
            patch.object(processor, "_llamar_gemini", return_value='{"intro":"ok","items":[],"trend_judgment":"ok"}'), \
            patch.object(processor, "_persistir_macro_resumen") as persist, \
            patch.object(processor, "get_session") as get_session:
            session = get_session.return_value.__enter__.return_value
            query = session.query.return_value
            query.filter.return_value.first.return_value = existing
            query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [article, article, article]

            result = processor.generar_macro_resumen_dia({})

        session.delete.assert_called_once_with(existing)
        persist.assert_called_once()
        self.assertTrue(result["uso_api"])

    def test_macro_summary_uses_local_date_not_utc_date(self) -> None:
        import src.processor as processor

        class FakeDateTime:
            min = real_datetime.min

            @classmethod
            def now(cls, tz=None):
                if tz is timezone.utc:
                    return real_datetime(2026, 6, 19, 2, 30)
                return real_datetime(2026, 6, 18, 23, 30)

            @classmethod
            def combine(cls, day, value):
                return real_datetime.combine(day, value)

        article = type("Article", (), {
            "titulo": "Important IT story",
            "fuente": "Reuters",
            "url": "https://www.reuters.com/example",
            "resumen_ia": "Resumen no disponible",
            "descripcion_original": "A real story exists.",
            "area_matcheada": "ciberseguridad",
            "score": 100,
            "ranking": None,
            "fecha_ingesta": None,
        })()

        with patch.object(processor, "datetime", FakeDateTime), \
            patch.object(processor, "fetch_global_news", return_value=[]), \
            patch.object(processor, "_llamar_gemini", return_value='{"intro":"ok","items":[],"trend_judgment":"ok"}'), \
            patch.object(processor, "_persistir_macro_resumen") as persist, \
            patch.object(processor, "get_session") as get_session:
            session = get_session.return_value.__enter__.return_value
            query = session.query.return_value
            query.filter.return_value.first.return_value = None
            query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [article, article, article]

            processor.generar_macro_resumen_dia({})

        self.assertEqual(persist.call_args.kwargs["fecha"], date(2026, 6, 18))

    def test_processing_skips_individual_enrichment_when_gemini_check_fails(self) -> None:
        import src.processor as processor

        with patch.object(processor, "_verificar_gemini", return_value=False), \
            patch.object(processor, "cargar_config_procesador", return_value={"app": {"top_tendencias": 5, "max_noticias_ia": 10}, "areas_interes": {}}), \
            patch.object(processor, "calcular_tendencias", return_value=[]), \
            patch.object(processor, "clustering_diario", return_value={"clusters_generados": 0, "noticias_agrupadas": 0}), \
            patch.object(processor, "score_recent_items", return_value=0), \
            patch.object(processor, "enriquecer_con_ia") as enriquecer, \
            patch.object(processor, "generar_macro_resumen_dia", return_value={"macro_resumen_generado": True, "uso_api": False}):
            processor.ejecutar_procesamiento()

        enriquecer.assert_not_called()

    def test_processing_skips_individual_enrichment_when_budget_is_zero(self) -> None:
        import src.processor as processor

        with patch.object(processor, "_verificar_gemini", return_value=True), \
            patch.object(processor, "cargar_config_procesador", return_value={"app": {"top_tendencias": 5, "max_noticias_ia": 0}, "areas_interes": {}}), \
            patch.object(processor, "calcular_tendencias", return_value=[]), \
            patch.object(processor, "clustering_diario", return_value={"clusters_generados": 0, "noticias_agrupadas": 0}), \
            patch.object(processor, "score_recent_items", return_value=0), \
            patch.object(processor, "enriquecer_con_ia") as enriquecer, \
            patch.object(processor, "generar_macro_resumen_dia", return_value={"macro_resumen_generado": True, "uso_api": False}):
            result = processor.ejecutar_procesamiento()

        enriquecer.assert_not_called()
        self.assertEqual(result["noticias_enriquecidas"], 0)

    def test_processing_defaults_individual_enrichment_budget_to_zero(self) -> None:
        import src.processor as processor

        with patch.object(processor, "_verificar_gemini", return_value=True), \
            patch.object(processor, "cargar_config_procesador", return_value={"app": {"top_tendencias": 5}, "areas_interes": {}}), \
            patch.object(processor, "calcular_tendencias", return_value=[]), \
            patch.object(processor, "clustering_diario", return_value={"clusters_generados": 0, "noticias_agrupadas": 0}), \
            patch.object(processor, "score_recent_items", return_value=0), \
            patch.object(processor, "enriquecer_con_ia") as enriquecer, \
            patch.object(processor, "generar_macro_resumen_dia", return_value={"macro_resumen_generado": True, "uso_api": False}):
            result = processor.ejecutar_procesamiento()

        enriquecer.assert_not_called()
        self.assertEqual(result["noticias_enriquecidas"], 0)

    def test_gemini_rate_limit_fails_fast_without_retries(self) -> None:
        import src.processor as processor

        class FakeModel:
            calls = 0

            def generate_content(self, model, contents):
                self.calls += 1
                raise Exception("429 RESOURCE_EXHAUSTED quota exceeded")

        fake_model = FakeModel()
        fake_client = type("FakeClient", (), {"models": fake_model})()

        with patch.object(processor, "GEMINI_AVAILABLE", True), \
            patch.object(processor, "GEMINI_API_KEY", "key"), \
            patch.object(processor.google_genai, "Client", return_value=fake_client):
            result = processor._llamar_gemini("prompt")

        self.assertIsNone(result)
        self.assertEqual(fake_model.calls, 1)

    def test_gemini_availability_check_does_not_call_api(self) -> None:
        import src.processor as processor

        with patch.object(processor, "GEMINI_AVAILABLE", True), \
            patch.object(processor, "GEMINI_API_KEY", "key"), \
            patch.object(processor.google_genai, "Client") as client:
            result = processor._verificar_gemini()

        self.assertTrue(result)
        client.assert_not_called()

    def test_macro_cache_matches_same_selected_source_set(self) -> None:
        import json

        import src.processor as processor

        payload = {
            "source_records": [
                {
                    "name": "GitHub Blog",
                    "url": "https://github.blog/example",
                    "title": "Example",
                    "score": 88.0,
                    "score_version": processor.SCORE_VERSION,
                }
            ]
        }
        signature = processor._payload_signature(payload)
        existing = type("ExistingMacro", (), {
            "modelo": processor.GEMINI_MODEL,
            "brief_json": json.dumps({
                "source_signature": signature,
                "score_version": processor.SCORE_VERSION,
            }),
        })()

        self.assertTrue(processor._macro_cache_matches(existing, signature))


class TestCorpusSearch(unittest.TestCase):
    def setUp(self) -> None:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        import app
        from src.database import Base

        self.app = app
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

        self.session_patch = patch.object(app, "get_session", temporary_session)
        self.session_patch.start()
        app._buscar_corpus.clear()
        app._sugerir_corpus.clear()

    def tearDown(self) -> None:
        self.app._buscar_corpus.clear()
        self.app._sugerir_corpus.clear()
        self.session_patch.stop()
        self.engine.dispose()

    def _add_article(
        self,
        article_id: str,
        title: str,
        description: str,
        summary: str,
        source: str,
        area: str,
        score: float,
    ) -> None:
        from src.database import Noticia

        with self.session_factory() as session:
            session.add(Noticia(
                id=article_id,
                titulo=title,
                url=f"https://example.test/{article_id}",
                fuente=source,
                descripcion_original=description,
                resumen_ia=summary,
                area_matcheada=area,
                fecha_ingesta=real_datetime(2026, 6, 19, 12, 0),
                selected_score=score,
            ))
            session.commit()

    def test_search_matches_title_description_and_summary(self) -> None:
        self._add_article("title", "Needle in title", "", "", "Reuters", "general", 70)
        self._add_article("description", "Other", "Needle in description", "", "Hacker News", "general", 80)
        self._add_article("summary", "Other", "", "Needle in summary", "GitHub Blog", "general", 90)

        result = self.app._buscar_corpus("needle")

        self.assertEqual(result["id"].tolist(), ["summary", "description", "title"])

    def test_search_respects_source_and_area_filters(self) -> None:
        self._add_article("keep", "AI release", "", "", "OpenAI Blog", "inteligencia_artificial", 90)
        self._add_article("wrong-source", "AI release", "", "", "Reuters", "inteligencia_artificial", 95)
        self._add_article("wrong-area", "AI release", "", "", "OpenAI Blog", "general", 96)

        result = self.app._buscar_corpus(
            "AI",
            fuentes=("OpenAI Blog",),
            areas_keys=("inteligencia_artificial",),
        )

        self.assertEqual(result["id"].tolist(), ["keep"])

    def test_suggestions_are_limited_and_sorted_by_score(self) -> None:
        for index, score in enumerate([62, 98, 74, 91, 80, 86]):
            self._add_article(
                f"suggestion-{index}",
                f"Agent result {index}",
                "",
                "",
                "GitHub Blog",
                "inteligencia_artificial",
                score,
            )

        suggestions = self.app._sugerir_corpus("agent")

        self.assertEqual(len(suggestions), 5)
        self.assertEqual([item["score"] for item in suggestions], [98.0, 91.0, 86.0, 80.0, 74.0])

    def test_suggestions_require_two_characters(self) -> None:
        self._add_article("short-query", "AI release", "", "", "OpenAI Blog", "inteligencia_artificial", 90)

        self.assertEqual(self.app._sugerir_corpus("a"), [])


class TestSidebarFilters(unittest.TestCase):
    def setUp(self) -> None:
        import app

        self.app = app

    def test_date_window_defaults_to_today_and_rejects_outside_range(self) -> None:
        today = date(2026, 6, 24)

        self.assertEqual(self.app._filter_date_bounds(today), (date(2026, 6, 18), today))
        self.assertEqual(self.app._parse_filter_date("2026-06-17", today), today)
        self.assertEqual(self.app._parse_filter_date("invalid", today), today)
        self.assertEqual(self.app._parse_filter_date("2026-06-20", today), date(2026, 6, 20))

    def test_source_aware_date_filter_uses_publication_or_trending_detection(self) -> None:
        df = self.app.pd.DataFrame([
            {
                "id": "article",
                "Fuente": "Reuters",
                "Área": "general",
                "Publicada": "2026-06-23T22:00:00Z",
                "Ingestada": "2026-06-24T14:00:00Z",
                "Selected Score": 90,
            },
            {
                "id": "trending",
                "Fuente": "GitHub Trending",
                "Área": "general",
                "Publicada": None,
                "Ingestada": "2026-06-24T14:00:00Z",
                "Selected Score": 80,
            },
        ])

        result = self.app._filter_and_sort_feed(df, {"fecha": date(2026, 6, 24)})

        self.assertEqual(result["id"].tolist(), ["trending"])

    def test_sort_mode_uses_score_or_recency_with_stable_tie_breaker(self) -> None:
        df = self.app.pd.DataFrame([
            {
                "id": "high-score",
                "Fuente": "Reuters",
                "Área": "general",
                "Publicada": "2026-06-24T12:00:00Z",
                "Ingestada": "2026-06-24T12:05:00Z",
                "Selected Score": 95,
            },
            {
                "id": "recent",
                "Fuente": "Reuters",
                "Área": "general",
                "Publicada": "2026-06-24T15:00:00Z",
                "Ingestada": "2026-06-24T15:05:00Z",
                "Selected Score": 80,
            },
        ])
        filters = {"fecha": date(2026, 6, 24)}

        score_sorted = self.app._filter_and_sort_feed(df, filters)
        recent_sorted = self.app._filter_and_sort_feed(df, {**filters, "orden": "Más reciente"})

        self.assertEqual(score_sorted["id"].tolist(), ["high-score", "recent"])
        self.assertEqual(recent_sorted["id"].tolist(), ["recent", "high-score"])


class TestGlobalNewsIngestion(unittest.TestCase):
    def test_github_ingestion_schedules_only_daily_trending(self) -> None:
        import src.ingestor as ingestor

        scheduled_windows = []
        metrics = {
            "total_procesadas": 0,
            "fuentes_fallidas": 0,
            "nombres_fallidas": [],
            "no_relevantes": 0,
        }
        config = {
            "app": {"github_trending_dias_hoy": 1, "github_trending_dias_semanal": 7},
            "areas_interes": {},
            "fuentes": [{"nombre": "GitHub Trending", "tipo": "github_api"}],
        }

        def fake_worker(_source, _app, _areas, days):
            scheduled_windows.append(days)
            return [], metrics

        with patch.object(ingestor, "cargar_config", return_value=config), \
             patch.object(ingestor, "_worker_github", side_effect=fake_worker):
            ingestor.ejecutar_ingesta()

        self.assertEqual(scheduled_windows, [1])

    def test_hacker_news_algolia_failure_reports_specific_worker_name(self) -> None:
        import src.ingestor as ingestor

        with patch.object(ingestor.requests, "get", side_effect=Exception("network down")):
            _, metrics = ingestor._worker_hn_algolia(
                {"nombre": "Hacker News"},
                {"timeout_request": 1},
                {},
                dias_ventana=7,
            )

        self.assertEqual(metrics["fuentes_fallidas"], 1)
        self.assertEqual(metrics["nombres_fallidas"], ["Hacker News Algolia 7d"])

    def test_global_items_convert_to_local_noticias_with_source_names(self) -> None:
        from src.global_news import normalize_global_item
        from src.ingestor import _noticias_desde_global_items

        items = [
            normalize_global_item(
                title="Major hack campaign against Fortinet devices compromised organizations",
                source="Reuters",
                url="https://www.reuters.com/world/fortinet-example-2026-06-17/",
                excerpt="Researchers reported a credential campaign.",
                category="Cybersecurity",
                score=10,
                published_at="2026-06-19T12:34:56Z",
            ),
            normalize_global_item(
                title="Getting more from each token",
                source="GitHub Blog",
                url="https://github.blog/ai-and-ml/example",
                excerpt="Copilot improves context handling.",
                category="Developer Tools",
                score=9,
            ),
            normalize_global_item(
                title="Introducing LifeSciBench",
                source="OpenAI Blog",
                url="https://openai.com/index/example",
                excerpt="A benchmark for life sciences research tasks.",
                category="AI",
                score=8,
            ),
        ]

        noticias = _noticias_desde_global_items([item for item in items if item is not None])

        self.assertEqual([n.fuente for n in noticias], ["Reuters", "GitHub Blog", "OpenAI Blog"])
        self.assertEqual(noticias[0].area_matcheada, "ciberseguridad")
        self.assertEqual(noticias[0].fecha_publicacion, real_datetime(2026, 6, 19, 12, 34, 56))
        self.assertIsNone(noticias[1].fecha_publicacion)
        self.assertTrue(noticias[1].titulo.startswith("[Global]"))

    def test_duplicate_item_receives_missing_verified_publication_time(self) -> None:
        import src.ingestor as ingestor
        from src.database import Noticia

        existing = Noticia(
            id="existing",
            titulo="Existing story",
            url="https://www.reuters.com/technology/example/",
            fuente="Reuters",
            fecha_ingesta=real_datetime(2026, 6, 19, 12, 0),
        )
        incoming = Noticia(
            id="existing",
            titulo="Existing story",
            url="https://www.reuters.com/technology/example/",
            fuente="Reuters",
            fecha_publicacion=real_datetime(2026, 6, 19, 10, 30),
            fecha_ingesta=real_datetime(2026, 6, 19, 12, 0),
        )

        @contextmanager
        def fake_session():
            class Session:
                def get(self, *_args):
                    return existing

                def commit(self):
                    return None

            yield Session()

        metrics = {
            "total_procesadas": 1,
            "fuentes_fallidas": 0,
            "nombres_fallidas": [],
            "no_relevantes": 0,
        }
        config = {
            "app": {},
            "areas_interes": {},
            "fuentes": [{"nombre": "Global IT Brief", "tipo": "global_news"}],
        }

        with patch.object(ingestor, "cargar_config", return_value=config), \
             patch.object(ingestor, "_worker_global_news", return_value=([incoming], metrics)), \
             patch.object(ingestor, "get_session", side_effect=fake_session):
            ingestor.ejecutar_ingesta()

        self.assertEqual(existing.fecha_publicacion, real_datetime(2026, 6, 19, 10, 30))

    def test_duplicate_github_trending_item_refreshes_daily_metadata(self) -> None:
        import src.ingestor as ingestor
        from src.database import Noticia

        existing = Noticia(
            id="github-trending",
            titulo="[GitHub] old/repository (+1 stars this week)",
            url="https://github.com/old/repository",
            fuente="GitHub Trending",
            descripcion_original="Old description",
            fecha_ingesta=real_datetime(2026, 6, 23, 12, 0),
            ranking=18,
            selected_score=91,
        )
        incoming = Noticia(
            id="github-trending",
            titulo="[GitHub] calesthio/OpenMontage (+3,703 stars today)",
            url="https://github.com/calesthio/OpenMontage",
            fuente="GitHub Trending",
            descripcion_original="Current description",
            area_matcheada="inteligencia_artificial",
            fecha_ingesta=real_datetime(2026, 6, 24, 18, 40),
            ranking=1,
        )

        @contextmanager
        def fake_session():
            class Session:
                def get(self, *_args):
                    return existing

                def commit(self):
                    return None

            yield Session()

        metrics = {
            "total_procesadas": 1,
            "fuentes_fallidas": 0,
            "nombres_fallidas": [],
            "no_relevantes": 0,
        }
        config = {
            "app": {"github_trending_dias_hoy": 1},
            "areas_interes": {},
            "fuentes": [{"nombre": "GitHub Trending", "tipo": "github_api"}],
        }

        with patch.object(ingestor, "cargar_config", return_value=config), \
             patch.object(ingestor, "_worker_github", return_value=([incoming], metrics)), \
             patch.object(ingestor, "get_session", side_effect=fake_session):
            ingestor.ejecutar_ingesta()

        self.assertEqual(existing.titulo, incoming.titulo)
        self.assertEqual(existing.ranking, 1)
        self.assertEqual(existing.fecha_ingesta, real_datetime(2026, 6, 24, 18, 40))
        self.assertIsNone(existing.selected_score)


class TestBriefUi(unittest.TestCase):
    def test_manual_analysis_controls_are_absent(self) -> None:
        source = Path("app.py").read_text(encoding="utf-8")

        self.assertNotIn("Analizar período", source)
        self.assertNotIn("_render_pipeline_result", source)

    def test_hacker_news_comments_use_discussion_url_or_hn_article_url(self) -> None:
        from app import _comment_count, _discussion_url

        stored = type("Item", (), {
            "discussion_url": "https://news.ycombinator.com/item?id=123",
            "url": "https://example.test/article",
            "fuente": "Hacker News",
        })()
        legacy = type("Item", (), {
            "discussion_url": "",
            "url": "https://news.ycombinator.com/item?id=456",
            "fuente": "Hacker News",
        })()

        self.assertEqual(_discussion_url(stored), "https://news.ycombinator.com/item?id=123")
        self.assertEqual(_discussion_url(legacy), "https://news.ycombinator.com/item?id=456")
        self.assertEqual(_comment_count({"Comentarios": 164, "Comentarios URL": stored.discussion_url}), 164)
        self.assertEqual(_comment_count({"Comentarios": "", "Comentarios URL": stored.discussion_url}), 0)

    def test_main_uses_component_search_instead_of_native_text_input(self) -> None:
        source = Path("app.py").read_text(encoding="utf-8")
        component_source = Path("src/search_component.py").read_text(encoding="utf-8")

        self.assertIn("_render_corpus_search(filtros)", source)
        self.assertNotIn("st.text_input(", source)
        self.assertIn('type="text"', component_source)
        self.assertNotIn('type="search"', component_source)

    def test_main_has_no_historical_tab(self) -> None:
        source = Path("app.py").read_text(encoding="utf-8")

        self.assertNotIn("st.tabs(", source)
        self.assertNotIn("_render_tab_historico", source)

    def test_fuentes_catalogo_includes_global_sources(self) -> None:
        from app import FUENTES_CATALOGO

        self.assertIn("Reuters", FUENTES_CATALOGO)
        self.assertIn("GitHub Blog", FUENTES_CATALOGO)
        self.assertIn("OpenAI Blog", FUENTES_CATALOGO)

    def test_reuters_cards_do_not_render_fake_metric_footer(self) -> None:
        from app import _feed_card_metric_text

        self.assertIsNone(_feed_card_metric_text("Reuters", 0, None))
        self.assertEqual(_feed_card_metric_text("Hacker News", 42, None), "⬆️ 42 points")
        self.assertEqual(_feed_card_metric_text("GitHub Trending", 1200, None), "⭐ 1,200 stars today")

    def test_feed_cards_do_not_render_missing_description_placeholder(self) -> None:
        source = Path("app.py").read_text(encoding="utf-8")

        self.assertNotIn('st.caption("Sin descripción disponible.")', source)

    def test_normalizar_citas_brief_keeps_only_source_urls(self) -> None:
        from app import _normalizar_citas_brief

        item = {
            "title": "Fortinet credential campaign",
            "summary": "Attackers abused leaked credentials.",
            "why_it_matters": "MFA and rotation matter.",
            "sources": [
                {"name": "Reuters", "url": "https://www.reuters.com/world/example/"},
                {"name": "Invented", "url": "https://fake.example/story"},
            ],
        }
        allowed = {"https://www.reuters.com/world/example/"}

        normalized = _normalizar_citas_brief(item, allowed)

        self.assertEqual(
            normalized["sources"],
            [{"name": "Reuters", "url": "https://www.reuters.com/world/example/"}],
        )

if __name__ == "__main__":
    unittest.main()
