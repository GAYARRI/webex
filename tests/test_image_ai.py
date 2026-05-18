import os
import unittest
from unittest.mock import patch

from src.image_ai import _image_data_url, _is_bad_vision_candidate, analyze_images_with_vision
from src.models import Entity, PageExtraction


def _page(images=None):
    return PageExtraction(
        url="https://example.com",
        title="Example",
        description=None,
        language="es",
        main_text="Texto",
        raw_text="Texto",
        images=images or [{"url": "https://example.com/a.jpg", "alt": "A", "source": "page"}],
        status="ok",
    )


class ImageAiTests(unittest.TestCase):
    def test_report_explains_missing_api_key(self):
        page = PageExtraction(
            url="https://example.com",
            title="Example",
            description=None,
            language="es",
            main_text="Texto",
            raw_text="Texto",
            images=[{"url": "https://example.com/a.jpg", "alt": "A", "source": "page"}],
            status="ok",
        )

        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False):
            _, report = analyze_images_with_vision([Entity(name="A")], page, model="gpt-5.4-mini")

        self.assertEqual(report["status"], "skipped")
        self.assertEqual(report["strategy"], "heuristic-first")
        self.assertIn("OPENAI_API_KEY", report["errors"][0])

    def test_filters_bad_vision_candidates(self):
        self.assertTrue(_is_bad_vision_candidate("https://example.com/logo-burgos-pequeno"))
        self.assertTrue(_is_bad_vision_candidate("https://example.com/googleplay-en-3"))
        self.assertFalse(_is_bad_vision_candidate("https://example.com/catedral-burgos.jpg"))

    def test_image_data_url_encodes_downloaded_image(self):
        class Response:
            content = b"abc"
            headers = {"content-type": "image/jpeg"}

            def raise_for_status(self):
                return None

        with patch("src.image_ai.requests.get", return_value=Response()):
            data_url = _image_data_url("https://example.com/a.jpg")

        self.assertEqual(data_url, "data:image/jpeg;base64,YWJj")


class FallbackStrategyTests(unittest.TestCase):
    def test_fallback_skipped_when_all_entities_have_images(self):
        entities = [Entity(name="A", images=["https://example.com/a.jpg"])]
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=False):
            result_entities, report = analyze_images_with_vision(
                entities, _page(), model="gpt-5.4-mini", strategy="fallback"
            )
        self.assertEqual(report["status"], "skipped")
        self.assertTrue(any("ya tienen imágenes" in e for e in report["errors"]))
        self.assertEqual(result_entities[0].images, ["https://example.com/a.jpg"])

    def test_fallback_skipped_when_no_api_key(self):
        entities = [Entity(name="A")]
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False):
            _, report = analyze_images_with_vision(
                entities, _page(), model="gpt-5.4-mini", strategy="fallback"
            )
        self.assertEqual(report["status"], "skipped")
        self.assertIn("OPENAI_API_KEY", report["errors"][0])

    def test_fallback_only_processes_entities_without_images(self):
        entities = [
            Entity(name="Con imagen", images=["https://example.com/img.jpg"]),
            Entity(name="Sin imagen"),
        ]
        assigned_url = "https://example.com/found.jpg"

        def fake_classify(images, entity_index, model):
            return [{"image_url": assigned_url, "entity": "Sin imagen", "reason": "matches"}], None

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=False):
            with patch("src.image_ai._classify_image_batch", side_effect=fake_classify):
                result_entities, report = analyze_images_with_vision(
                    entities,
                    _page(images=[{"url": assigned_url, "alt": "Found", "source": "page"}]),
                    model="gpt-5.4-mini",
                    strategy="fallback",
                )

        names_with_images = {e.name for e in result_entities if e.images}
        self.assertIn("Sin imagen", names_with_images)
        self.assertIn("Con imagen", names_with_images)
        self.assertEqual(result_entities[0].images, ["https://example.com/img.jpg"])

    def test_fallback_report_strategy_field(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=False):
            _, report = analyze_images_with_vision(
                [Entity(name="A", images=["https://example.com/x.jpg"])],
                _page(),
                model="gpt-5.4-mini",
                strategy="fallback",
            )
        self.assertEqual(report["strategy"], "fallback")


if __name__ == "__main__":
    unittest.main()
