import unittest

from src.image_filters import is_image_url, is_noise_image


class ImageFilterTests(unittest.TestCase):
    def test_filters_svg_and_social_icons(self):
        self.assertTrue(is_noise_image("https://example.com/icon.svg"))
        self.assertTrue(is_noise_image("https://example.com/Twitter+X+1.png"))
        self.assertTrue(is_noise_image("https://example.com/facebook.png"))
        self.assertTrue(is_noise_image("https://example.com/whatsapp-svgrepo-blanco-2"))
        self.assertTrue(is_noise_image("https://example.com/LogoVidrieraBurgosBlanco.png"))
        self.assertTrue(is_noise_image("https://example.com/desliza.png"))
        self.assertTrue(is_noise_image("https://example.com/clock.png"))
        self.assertTrue(is_noise_image("https://example.com/map-pin.png"))
        self.assertTrue(is_noise_image("https://example.com/imagen.png", metadata="info_icons"))

    def test_keeps_content_images(self):
        self.assertFalse(is_noise_image("https://example.com/catedral-burgos.jpg"))
        self.assertFalse(is_noise_image("https://example.com/centro-biodiversidad-1"))

    def test_detects_image_urls(self):
        self.assertTrue(is_image_url("https://example.com/catedral.jpg"))
        self.assertTrue(is_image_url("https://example.com/documents/d/guest/catedral"))
        self.assertTrue(is_image_url("https://example.com/image?id=1&imagePreview=1"))
        self.assertFalse(is_image_url("https://example.com/es/que-ver/catedral"))


if __name__ == "__main__":
    unittest.main()
