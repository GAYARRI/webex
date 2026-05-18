import os
import unittest
from unittest.mock import patch

from src.image_ai import _image_data_url, _is_bad_vision_candidate, analyze_images_with_vision
from src.models import Entity, PageExtraction


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


if __name__ == "__main__":
    unittest.main()
