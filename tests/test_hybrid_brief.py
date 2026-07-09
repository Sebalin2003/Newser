from __future__ import annotations

import unittest
from contextlib import contextmanager
from datetime import date, datetime as real_datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch


class TestSchema(unittest.TestCase):
    def test_database_url_normalizes_supabase_postgres_urls(self) -> None:
        from src.database import engine_kwargs, normalize_database_url

        self.assertEqual(
            normalize_database_url("postgres://user:pass@example.test/postgres"),
            "postgresql+psycopg://user:pass@example.test/postgres",
        )
        self.assertEqual(
            normalize_database_url("postgresql://user:pass@example.test/postgres"),
            "postgresql+psycopg://user:pass@example.test/postgres",
        )
        self.assertEqual(engine_kwargs("sqlite:///news_analyzer.db")["connect_args"], {"check_same_thread": False})
        self.assertTrue(engine_kwargs("postgresql+psycopg://user:pass@example.test/postgres")["pool_pre_ping"])

    def test_macro_resumen_has_brief_json_column(self) -> None:
        from sqlalchemy import inspect

        from src.database import engine, init_db

        init_db()
        columns = {column["name"] for column in inspect(engine).get_columns("macro_resumenes")}

        self.assertIn("brief_json", columns)
        self.assertIn("texto_en", columns)
        self.assertIn("brief_json_en", columns)
        self.assertIn("modelo_en", columns)
        self.assertIn("fecha_generacion_en", columns)

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
        self.assertIn("resumen_ia_en", columns)
        self.assertIn("github_total_stars", columns)
        self.assertIn("github_stars_period", columns)
        self.assertIn("github_period_label", columns)
        self.assertIn("github_metrics_updated_at", columns)
        self.assertIn("github_fresh_date", columns)

    def test_postgres_schema_path_runs_additive_column_migrations(self) -> None:
        source = Path("src/database.py").read_text(encoding="utf-8")
        migration_body = source.split("def migrar_schema()", maxsplit=1)[1].split("# ---------------------------------------------------------------------------", maxsplit=1)[0]

        self.assertNotIn("return\n\n    inspector = inspect(engine)", migration_body)
        self.assertIn('datetime_type = "DATETIME" if sqlite else "TIMESTAMP"', migration_body)
        self.assertIn('"github_total_stars": "github_total_stars INTEGER"', migration_body)
        self.assertIn('"github_metrics_updated_at": f"github_metrics_updated_at {datetime_type}"', migration_body)
        self.assertIn('_add_missing_columns("noticias", existing_cols, nuevas_columnas)', migration_body)


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

    def test_consumer_airpods_story_is_not_ranked_as_ai(self) -> None:
        from datetime import datetime, timezone

        from src.scoring import calculate_item_score

        now = datetime(2026, 6, 28, 16, tzinfo=timezone.utc)
        item = {
            "titulo": "LibrePods: AirPods liberated",
            "descripcion_original": (
                "LibrePods busca liberar a los Apple AirPods de su ecosistema "
                "cerrado mediante ingenierÃ­a inversa y firmware de cÃ³digo abierto."
            ),
            "fuente": "Hacker News",
            "area_matcheada": "ai_agents",
            "fecha_ingesta": now,
            "score": 150,
            "num_comentarios": 41,
        }

        result = calculate_item_score(item, now=now)

        self.assertLessEqual(result.selected_score, 48)
        self.assertNotIn("AI", result.tags)
        self.assertLess(result.components["relevance_quality"], 35)

    def test_strong_ai_and_security_stories_still_score_highly(self) -> None:
        from datetime import datetime, timezone

        from src.scoring import calculate_item_score

        now = datetime(2026, 6, 28, 16, tzinfo=timezone.utc)
        ai_item = {
            "titulo": "OpenAI releases new agent model for developers",
            "descripcion_original": "The LLM improves inference and coding workflows.",
            "fuente": "OpenAI Blog",
            "area_matcheada": "ai_agents",
            "fecha_ingesta": now,
        }
        security_item = {
            "titulo": "Critical security vulnerability disclosed in developer platform",
            "descripcion_original": "Researchers published exploit details and mitigation guidance.",
            "fuente": "Reuters",
            "area_matcheada": "cybersecurity",
            "fecha_ingesta": now,
        }

        self.assertGreaterEqual(calculate_item_score(ai_item, now=now).selected_score, 80)
        self.assertGreaterEqual(calculate_item_score(security_item, now=now).selected_score, 70)

    def test_github_trending_metadata_does_not_create_developer_tools_tag(self) -> None:
        from datetime import datetime, timezone

        from src.scoring import calculate_item_score

        now = datetime(2026, 7, 8, 12, tzinfo=timezone.utc)
        item = {
            "titulo": "[GitHub] owner/repo \u2b5010,000 (+1,000 stars today)",
            "descripcion_original": "",
            "fuente": "GitHub Trending",
            "area_matcheada": "general",
            "fecha_ingesta": now,
            "ranking": 1,
        }

        result = calculate_item_score(item, now=now)

        self.assertNotIn("Developer Tools", result.tags)
        self.assertEqual(result.components["popularity"], 100.0)
        self.assertLessEqual(result.selected_score, 48)

    def test_popular_github_trending_repo_with_weak_relevance_is_capped(self) -> None:
        from datetime import datetime, timezone

        from src.scoring import calculate_item_score

        now = datetime(2026, 7, 8, 12, tzinfo=timezone.utc)
        item = {
            "titulo": "[GitHub] owner/repo \u2b5010,000 (+1,000 stars today)",
            "descripcion_original": "A popular collection of notes.",
            "fuente": "GitHub Trending",
            "area_matcheada": "developer_tools",
            "fecha_ingesta": now,
            "ranking": 1,
        }

        result = calculate_item_score(item, now=now)

        self.assertNotIn("Developer Tools", result.tags)
        self.assertEqual(result.components["popularity"], 100.0)
        self.assertLessEqual(result.selected_score, 48)

    def test_relevant_github_trending_repo_still_scores_highly(self) -> None:
        from datetime import datetime, timezone

        from src.scoring import calculate_item_score

        now = datetime(2026, 7, 8, 12, tzinfo=timezone.utc)
        item = {
            "titulo": "[GitHub] owner/repo \u2b5010,000 (+1,000 stars today)",
            "descripcion_original": "Open source AI agent SDK for developer workflows and model inference.",
            "fuente": "GitHub Trending",
            "area_matcheada": "developer_tools",
            "fecha_ingesta": now,
            "ranking": 1,
        }

        result = calculate_item_score(item, now=now)

        self.assertGreaterEqual(result.selected_score, 80)
        self.assertIn("AI", result.tags)
        self.assertEqual(result.components["popularity"], 100.0)

    def test_ingestion_keyword_matching_does_not_match_ai_inside_airpods(self) -> None:
        from src.relevance import classify_relevance

        areas = {
            "ai_agents": ["ai", "agent", "openai"],
            "developer_tools": ["developer", "open source", "api"],
        }

        relevant, area = classify_relevance(
            "LibrePods: AirPods liberated",
            "Open source firmware for Android bluetooth earbuds.",
            areas,
        )

        self.assertFalse(relevant)
        self.assertEqual(area, "")

        relevant_ai, area_ai = classify_relevance(
            "OpenAI releases an AI agent SDK",
            "A developer API for model workflows.",
            areas,
        )
        self.assertTrue(relevant_ai)
        self.assertEqual(area_ai, "ai_agents")

    def test_book_library_story_is_not_developer_tools_news(self) -> None:
        from datetime import datetime, timezone

        from src.relevance import classify_relevance
        from src.scoring import calculate_item_score

        areas = {
            "developer_tools": ["developer", "software library", "python library", "javascript library", "api"],
        }
        title = "Dua Lipa opens library for banned and censored books in Portugal"

        relevant, area = classify_relevance(title, "", areas)
        base_item = {
            "titulo": title,
            "descripcion_original": "",
            "fuente": "Hacker News",
            "fecha_ingesta": datetime(2026, 7, 7, 12, tzinfo=timezone.utc),
            "score": 157,
            "num_comentarios": 157,
        }
        scored = calculate_item_score(
            {
                **base_item,
                "area_matcheada": "general",
            },
            now=datetime(2026, 7, 7, 13, tzinfo=timezone.utc),
        )
        stored_false_positive = calculate_item_score(
            {**base_item, "area_matcheada": "developer_tools"},
            now=datetime(2026, 7, 7, 13, tzinfo=timezone.utc),
        )

        self.assertFalse(relevant)
        self.assertEqual(area, "")
        self.assertNotIn("Developer Tools", scored.tags)
        self.assertLessEqual(scored.selected_score, 58)
        self.assertNotIn("Developer Tools", stored_false_positive.tags)
        self.assertLessEqual(stored_false_positive.selected_score, 48)


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

    def test_normalize_global_item_accepts_hugging_face_blog_urls(self) -> None:
        from src.global_news import normalize_global_item

        item = normalize_global_item(
            title="LeRobot v0.6.0 improves robotics training workflows",
            source="Hugging Face Blog",
            url="https://huggingface.co/blog/lerobot-v0-6",
            excerpt="A release for datasets, models, and training.",
        )
        spoofed = normalize_global_item(
            title="Fake Hugging Face story",
            source="Hugging Face Blog",
            url="https://example.com/blog/lerobot-v0-6",
        )

        self.assertIsNotNone(item)
        self.assertEqual(item.source, "Hugging Face Blog")
        self.assertIsNone(spoofed)

    def test_fetch_global_news_reads_hugging_face_blog_cards(self) -> None:
        import src.global_news as global_news

        class Response:
            text = """
            <a href="/blog/lerobot-v0-6">
                <article>
                    <h3>LeRobot v0.6.0 improves robotics training workflows</h3>
                    <p>Datasets, models, and training updates for developers.</p>
                    <time datetime="2026-07-01T10:00:00Z">Jul 1, 2026</time>
                </article>
            </a>
            """

            def raise_for_status(self):
                return None

        with patch.object(global_news, "_fetch_reuters_sitemap", return_value=[]), \
             patch.object(global_news.feedparser, "parse", return_value=type("Parsed", (), {"entries": []})()), \
             patch.object(global_news.requests, "get", return_value=Response()):
            items = global_news.fetch_global_news(max_items=5)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].source, "Hugging Face Blog")
        self.assertEqual(items[0].url, "https://huggingface.co/blog/lerobot-v0-6")
        self.assertEqual(items[0].published_at, "2026-07-01T10:00:00+00:00")

    def test_looks_like_it_story_does_not_match_ai_inside_words(self) -> None:
        from src.global_news import looks_like_it_story

        self.assertFalse(
            looks_like_it_story(
                "Brasil busca um recomeÃ§o contra o Haiti apÃ³s estreia expor falhas",
                "https://www.reuters.com/sports/soccer/example/",
            )
        )
        self.assertFalse(
            looks_like_it_story(
                "ATUALIZA 2 BC corta Selic e sugere mais tempo para atingir meta de inflaÃ§Ã£o",
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

    def test_web_services_exposes_hugging_face_source_and_counts_it_as_global_news(self) -> None:
        import src.web_services as web_services

        class CountQuery:
            def count(self):
                return 10

            def filter(self, *_args):
                return self

        class LatestQuery:
            def order_by(self, *_args):
                return self

            def limit(self, *_args):
                return self

            def scalar(self):
                return real_datetime(2026, 7, 1, 10, 0)

        class SourceQuery:
            def all(self):
                return [
                    ("Reuters",),
                    ("GitHub Blog",),
                    ("OpenAI Blog",),
                    ("Hugging Face Blog",),
                    ("Hugging Face Blog",),
                    ("Hacker News",),
                ]

        class Session:
            def query(self, column):
                if column is web_services.Noticia.fuente:
                    return SourceQuery()
                if column is web_services.Noticia.fecha_ingesta:
                    return LatestQuery()
                return CountQuery()

        @contextmanager
        def fake_session():
            yield Session()

        with patch.object(web_services, "get_session", side_effect=fake_session):
            stats = web_services.get_stats()

        self.assertIn("Hugging Face Blog", web_services.SOURCES)
        self.assertEqual(stats["global_news_count"], 5)

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

    def test_macro_summary_prompt_uses_selected_language(self) -> None:
        import src.processor as processor

        captured_prompts: list[str] = []
        article = type("Article", (), {
            "titulo": "Important IT story",
            "fuente": "Reuters",
            "url": "https://www.reuters.com/example",
            "resumen_ia": "Resumen no disponible",
            "descripcion_original": "A real story exists.",
            "area_matcheada": "cybersecurity",
            "selected_score": 90,
            "score": 90,
            "ranking": None,
            "fecha_ingesta": None,
            "tags_json": "[]",
            "selection_reason": "",
            "score_version": processor.SCORE_VERSION,
        })()

        def fake_llamar(prompt, *_args, **_kwargs):
            captured_prompts.append(prompt)
            return '{"intro":"ok","items":[],"trend_reading":"ok"}'

        with patch.object(processor, "fetch_global_news", return_value=[]), \
             patch.object(processor, "_llamar_gemini", side_effect=fake_llamar), \
             patch.object(processor, "_persistir_macro_resumen") as persist, \
             patch.object(processor, "get_session") as get_session:
            session = get_session.return_value.__enter__.return_value
            query = session.query.return_value
            query.filter.return_value.first.return_value = None
            query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [article, article, article]

            processor.generar_macro_resumen_dia({}, language="en")

        self.assertIn("executive brief in English", captured_prompts[0])
        self.assertIn("Use natural English", captured_prompts[0])
        self.assertEqual(persist.call_args.kwargs["language"], "en")

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
            patch.object(processor, "GEMINI_MODEL", "gemini-3.1-flash-lite"), \
            patch.object(processor.google_genai, "Client", return_value=fake_client):
            result = processor._llamar_gemini("prompt")

        self.assertIsNone(result)
        self.assertEqual(fake_model.calls, 2)
        self.assertIn("gemini-2.5-flash-lite", processor.LAST_GEMINI_ERROR)

    def test_gemini_default_model_and_fallback_order(self) -> None:
        import src.processor as processor

        with patch.object(processor, "GEMINI_MODEL", processor.DEFAULT_GEMINI_MODEL):
            self.assertEqual(processor.GEMINI_MODEL, "gemini-3.1-flash-lite")
            self.assertEqual(
                processor._gemini_candidate_models(),
                ["gemini-3.1-flash-lite", "gemini-2.5-flash-lite"],
            )

    def test_gemini_env_override_stays_first_with_safe_fallbacks(self) -> None:
        import src.processor as processor

        with patch.object(processor, "GEMINI_MODEL", "custom-model"):
            self.assertEqual(
                processor._gemini_candidate_models(),
                ["custom-model", "gemini-3.1-flash-lite", "gemini-2.5-flash-lite"],
            )

    def test_gemini_deprecated_env_model_is_not_used(self) -> None:
        import importlib
        import os
        import src.processor as processor

        previous = os.environ.get("GEMINI_MODEL")
        try:
            os.environ["GEMINI_MODEL"] = "gemini-2.0-flash"
            reloaded = importlib.reload(processor)
            self.assertEqual(reloaded.GEMINI_MODEL, "gemini-3.1-flash-lite")
            self.assertNotIn("gemini-2.0-flash", reloaded._gemini_candidate_models())
        finally:
            if previous is None:
                os.environ.pop("GEMINI_MODEL", None)
            else:
                os.environ["GEMINI_MODEL"] = previous
            importlib.reload(processor)

    def test_article_summary_prompt_no_longer_requests_sentiment(self) -> None:
        import src.processor as processor

        prompt = processor._PROMPT_RESUMEN.format(titulo="Example title")

        self.assertIn("'resumen'", prompt)
        self.assertIn("máximo 3 frases", prompt)
        self.assertNotIn("sentimiento", prompt.lower())
        self.assertNotIn("positivo", prompt.lower())
        self.assertNotIn("negativo", prompt.lower())

    def test_article_summary_prompt_uses_selected_language(self) -> None:
        import src.processor as processor

        spanish = processor.build_article_summary_prompt("Example title", "es")
        english = processor.build_article_summary_prompt("Example title", "en")

        self.assertIn("español", spanish)
        self.assertIn("English", english)
        self.assertIn("Headline", english)

    def test_interactive_gemini_uses_fast_generation_config(self) -> None:
        import src.processor as processor

        class FakeModel:
            def __init__(self) -> None:
                self.kwargs = None

            def generate_content(self, **kwargs):
                self.kwargs = kwargs
                return type("Response", (), {"text": '{"resumen":"ok"}'})()

        fake_model = FakeModel()
        fake_client = type("FakeClient", (), {"models": fake_model})()

        with patch.object(processor, "GEMINI_AVAILABLE", True), \
            patch.object(processor, "GEMINI_API_KEY", "key"), \
            patch.object(processor.google_genai, "Client", return_value=fake_client):
            result = processor._llamar_gemini("prompt", interactive=True)

        self.assertEqual(result, '{"resumen":"ok"}')
        self.assertIn("config", fake_model.kwargs)
        config = fake_model.kwargs["config"]
        self.assertEqual(config.max_output_tokens, 180)
        self.assertEqual(config.response_mime_type, "application/json")
        self.assertEqual(config.thinking_config.thinking_budget, 0)

    def test_gemini_fallback_succeeds_after_primary_quota_error(self) -> None:
        import src.processor as processor

        class FakeModel:
            calls: list[str] = []

            def generate_content(self, model, contents):
                self.calls.append(model)
                if model == "gemini-3.1-flash-lite":
                    raise Exception("429 RESOURCE_EXHAUSTED quota exceeded")
                return type("Response", (), {"text": "ok"})()

        fake_model = FakeModel()
        fake_client = type("FakeClient", (), {"models": fake_model})()

        with patch.object(processor, "GEMINI_AVAILABLE", True), \
            patch.object(processor, "GEMINI_API_KEY", "key"), \
            patch.object(processor, "GEMINI_MODEL", "gemini-3.1-flash-lite"), \
            patch.object(processor.google_genai, "Client", return_value=fake_client):
            result = processor._llamar_gemini("prompt")

        self.assertEqual(result, "ok")
        self.assertEqual(fake_model.calls, ["gemini-3.1-flash-lite", "gemini-2.5-flash-lite"])
        self.assertEqual(processor.LAST_GEMINI_MODEL, "gemini-2.5-flash-lite")

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

    def test_github_worker_uses_stable_repo_id(self) -> None:
        import src.ingestor as ingestor

        class Response:
            text = """
            <article class="Box-row">
                <h2><a href="/owner/repo">owner / repo</a></h2>
                <p>Developer SDK for AI agents.</p>
                <a href="/owner/repo/stargazers">8,000</a>
                <span class="d-inline-block float-sm-right">1,000 stars today</span>
                <span itemprop="programmingLanguage">Python</span>
            </article>
            """

            def raise_for_status(self):
                return None

        with patch.object(ingestor.requests, "get", return_value=Response()):
            noticias, _metrics = ingestor._worker_github(
                {"nombre": "GitHub Trending"},
                {"timeout_request": 15},
                {"developer_tools": ["developer", "sdk", "ai agents"]},
                dias_ventana=1,
            )

        self.assertEqual(len(noticias), 1)
        self.assertEqual(noticias[0].id, ingestor._calcular_hash("owner/repo", "https://github.com/owner/repo"))
        self.assertEqual(noticias[0].github_total_stars, 8000)
        self.assertEqual(noticias[0].github_stars_period, 1000)
        self.assertEqual(noticias[0].github_period_label, "today")
        self.assertEqual(noticias[0].score, 1000)
        self.assertIsNotNone(noticias[0].github_metrics_updated_at)
        self.assertIsNotNone(noticias[0].github_fresh_date)

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
            normalize_global_item(
                title="LeRobot v0.6.0 improves robotics training workflows",
                source="Hugging Face Blog",
                url="https://huggingface.co/blog/lerobot-v0-6",
                excerpt="Datasets, models, and training updates for developers.",
                category="AI",
                score=7,
            ),
        ]

        noticias = _noticias_desde_global_items([item for item in items if item is not None])

        self.assertEqual([n.fuente for n in noticias], ["Reuters", "GitHub Blog", "OpenAI Blog", "Hugging Face Blog"])
        self.assertEqual(noticias[0].area_matcheada, "cybersecurity")
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
        self.assertEqual(existing.github_fresh_date, date(2026, 6, 24))

    def test_github_trending_duplicate_url_reuses_existing_row(self) -> None:
        import src.ingestor as ingestor
        from src.database import Noticia

        existing = Noticia(
            id="old-daily-id",
            titulo="[GitHub] calesthio/OpenMontage (+100 stars this week)",
            url="https://github.com/calesthio/OpenMontage",
            fuente="GitHub Trending",
            descripcion_original="Old description",
            fecha_ingesta=real_datetime(2026, 6, 23, 12, 0),
            ranking=18,
            selected_score=91,
        )
        incoming = Noticia(
            id="new-stable-id",
            titulo="[GitHub] calesthio/OpenMontage (+3,703 stars today)",
            url="https://github.com/calesthio/OpenMontage",
            fuente="GitHub Trending",
            descripcion_original="Current description",
            area_matcheada="inteligencia_artificial",
            fecha_ingesta=real_datetime(2026, 6, 24, 18, 40),
            ranking=1,
        )
        added = []

        @contextmanager
        def fake_session():
            class Query:
                def filter(self, *_args):
                    return self

                def first(self):
                    return existing

            class Session:
                def get(self, *_args):
                    return None

                def query(self, *_args):
                    return Query()

                def add(self, noticia):
                    added.append(noticia)

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
            result = ingestor.ejecutar_ingesta()

        self.assertEqual(added, [])
        self.assertEqual(result["nuevas_persistidas"], 0)
        self.assertEqual(result["duplicadas_omitidas"], 1)
        self.assertEqual(existing.titulo, incoming.titulo)
        self.assertEqual(existing.ranking, 1)
        self.assertIsNone(existing.selected_score)

    def test_same_day_github_refresh_updates_metrics_without_bumping_freshness(self) -> None:
        import src.ingestor as ingestor
        from src.database import Noticia

        original_fresh_time = real_datetime(2026, 6, 24, 12, 0)
        existing = Noticia(
            id="github-trending",
            titulo="[GitHub] calesthio/OpenMontage (+100 stars today)",
            url="https://github.com/calesthio/openmontage",
            fuente="GitHub Trending",
            descripcion_original="Old description",
            fecha_ingesta=original_fresh_time,
            github_fresh_date=date(2026, 6, 24),
            github_total_stars=4000,
            github_stars_period=100,
            github_period_label="today",
            github_metrics_updated_at=real_datetime(2026, 6, 24, 12, 0),
            ranking=18,
            selected_score=91,
        )
        incoming = Noticia(
            id="github-trending",
            titulo="[GitHub] calesthio/OpenMontage (+200 stars today)",
            url="https://github.com/calesthio/OpenMontage",
            fuente="GitHub Trending",
            descripcion_original="Current description",
            area_matcheada="inteligencia_artificial",
            fecha_ingesta=real_datetime(2026, 6, 24, 18, 40),
            github_fresh_date=date(2026, 6, 24),
            github_total_stars=4500,
            github_stars_period=200,
            github_period_label="today",
            github_metrics_updated_at=real_datetime(2026, 6, 24, 18, 40),
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

        self.assertEqual(existing.fecha_ingesta, original_fresh_time)
        self.assertEqual(existing.github_total_stars, 4500)
        self.assertEqual(existing.github_stars_period, 200)
        self.assertEqual(existing.ranking, 1)
        self.assertIsNone(existing.selected_score)

    def test_duplicate_github_cleanup_preserves_favorite_and_latest_metrics(self) -> None:
        import src.ingestor as ingestor
        from src.database import Noticia

        kept = Noticia(
            id="favorite-old",
            titulo="[GitHub] owner/repo (+10 stars today)",
            url="https://github.com/owner/repo",
            fuente="GitHub Trending",
            fecha_ingesta=real_datetime(2026, 6, 24, 9, 0),
            github_fresh_date=date(2026, 6, 24),
            github_total_stars=100,
            github_stars_period=10,
            github_metrics_updated_at=real_datetime(2026, 6, 24, 9, 0),
            is_favorite=1,
            resumen_ia="Saved summary",
        )
        duplicate = Noticia(
            id="latest-duplicate",
            titulo="[GitHub] Owner/Repo (+80 stars today)",
            url="https://github.com/Owner/Repo/",
            fuente="GitHub Trending",
            fecha_ingesta=real_datetime(2026, 6, 24, 11, 0),
            github_fresh_date=date(2026, 6, 24),
            github_total_stars=180,
            github_stars_period=80,
            github_metrics_updated_at=real_datetime(2026, 6, 24, 11, 0),
            ranking=2,
        )
        deleted = []

        class Query:
            def filter(self, *_args):
                return self

            def all(self):
                return [kept, duplicate]

        class Session:
            def query(self, *_args):
                return Query()

            def delete(self, noticia):
                deleted.append(noticia)

        removed = ingestor._merge_duplicate_github_repos(Session())

        self.assertEqual(removed, 1)
        self.assertEqual(deleted, [duplicate])
        self.assertEqual(kept.is_favorite, 1)
        self.assertEqual(kept.resumen_ia, "Saved summary")
        self.assertEqual(kept.github_total_stars, 180)
        self.assertEqual(kept.github_stars_period, 80)
        self.assertEqual(kept.ranking, 2)

if __name__ == "__main__":
    unittest.main()
