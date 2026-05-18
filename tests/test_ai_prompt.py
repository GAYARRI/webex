import json
import unittest

from src.ai_client import _build_prompt
from src.models import PageExtraction


class AiPromptTests(unittest.TestCase):
    def test_prompt_includes_block_procedure_and_image_context(self):
        page = PageExtraction(
            url="https://example.com",
            title="Pagina",
            description="Descripcion",
            language="es",
            main_text="Texto principal",
            raw_text="Texto principal",
            images=[
                {
                    "url": "https://example.com/catedral.jpg",
                    "alt": "Catedral",
                    "context": "Bloque sobre Catedral de Burgos",
                    "source": "page",
                    "index": "1",
                }
            ],
            status="ok",
        )

        prompt = json.loads(_build_prompt(page))

        self.assertIn("procedure", prompt)
        self.assertIn("identity_contract", prompt)
        self.assertTrue(any("Elimina" in step for step in prompt["procedure"]))
        self.assertTrue(any("URL es solo evidencia" in step for step in prompt["identity_contract"]))
        self.assertEqual(prompt["page"]["images"][0]["context"], "Bloque sobre Catedral de Burgos")


if __name__ == "__main__":
    unittest.main()
