import unittest

from src.web_extractor import ensure_url, parse_html


class WebExtractorTests(unittest.TestCase):
    def test_ensure_url_adds_https_when_missing(self):
        self.assertEqual(ensure_url("example.com"), "https://example.com")
        self.assertEqual(ensure_url("http://example.com"), "http://example.com")

    def test_parse_html_extracts_basic_fields(self):
        page = parse_html(
            "https://example.com",
            """
            <html lang="es">
              <head>
                <title>Pagina de prueba</title>
                <meta name="description" content="Descripcion de prueba">
              </head>
              <body>
                <main><h1>Museo de prueba</h1><p>Contenido principal.</p></main>
                <img src="/a.jpg" alt="Imagen A">
              </body>
            </html>
            """,
        )

        self.assertEqual(page.title, "Pagina de prueba")
        self.assertEqual(page.description, "Descripcion de prueba")
        self.assertEqual(page.language, "es")
        self.assertIn("Museo de prueba", page.main_text)
        self.assertEqual(page.images[0]["url"], "https://example.com/a.jpg")

    def test_parse_html_filters_social_icons_and_svg(self):
        page = parse_html(
            "https://example.com",
            """
            <html><body>
              <img src="/Twitter+X+1.png" alt="">
              <img src="/icon.svg" alt="">
              <img src="/clock.png" class="info_icons" alt="">
              <img src="/small.jpg" width="24" height="24" alt="">
              <img src="/catedral-burgos.jpg" alt="Catedral">
            </body></html>
            """,
        )

        self.assertEqual(len(page.images), 1)
        self.assertEqual(page.images[0]["url"], "https://example.com/catedral-burgos.jpg")


if __name__ == "__main__":
    unittest.main()
