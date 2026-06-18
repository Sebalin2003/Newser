from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import patch


class TestSchema(unittest.TestCase):
    def test_macro_resumen_has_brief_json_column(self) -> None:
        from sqlalchemy import inspect

        from src.database import engine, init_db

        init_db()
        columns = {column["name"] for column in inspect(engine).get_columns("macro_resumenes")}

        self.assertIn("brief_json", columns)


class TestGlobalNews(unittest.TestCase):
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
                "score": i,
            }
            for i in range(20)
        ]

        payload = build_hybrid_brief_payload(global_items, local_items, date(2026, 6, 17))

        self.assertEqual(payload["date"], "2026-06-17")
        self.assertEqual(len(payload["global_news"]), 10)
        self.assertEqual(len(payload["developer_signals"]), 15)
        self.assertTrue(payload["global_news"][0]["url"].startswith("https://www.reuters.com/"))

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

    def test_processing_skips_individual_enrichment_when_gemini_check_fails(self) -> None:
        import src.processor as processor

        with patch.object(processor, "_verificar_gemini", return_value=False), \
            patch.object(processor, "cargar_config_procesador", return_value={"app": {"top_tendencias": 5, "max_noticias_ia": 10}, "areas_interes": {}}), \
            patch.object(processor, "calcular_tendencias", return_value=[]), \
            patch.object(processor, "clustering_diario", return_value={"clusters_generados": 0, "noticias_agrupadas": 0}), \
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


class TestGlobalNewsIngestion(unittest.TestCase):
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
        self.assertTrue(noticias[1].titulo.startswith("[Global]"))


class TestBriefUi(unittest.TestCase):
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
