import unittest

from src.contact_extractor import extract_contact_info


class ContactExtractorTests(unittest.TestCase):
    def test_extracts_phone_from_block_text(self):
        info = extract_contact_info("VISITAS GUIADAS: 947 288 719 COMO LLEGAR")

        self.assertEqual(info["phone"], "947 288 719")

    def test_extracts_address_from_block_text(self):
        info = extract_contact_info("Teatro Adultos. C/ Juan de Padilla, s/n. Burgos")

        self.assertEqual(info["address"], "C/ Juan de Padilla, s/n")

    def test_does_not_treat_camino_de_santiago_as_address(self):
        info = extract_contact_info(
            "Camino de Santiago Museo de la Evolucion Humana Casco Historico Arco de Santa Maria"
        )

        self.assertEqual(info["address"], "")

    def test_trims_address_before_schedule_noise(self):
        info = extract_contact_info(
            "Triana-Castillo de San Jorge. Plaza del Altozano s/n De lunes a domingo: 09:30-14:30h"
        )

        self.assertEqual(info["address"], "Plaza del Altozano s/n")

    def test_rejects_narrative_street_sentence(self):
        info = extract_contact_info(
            "La calle Betis se llena de casetas al mas puro estilo feria de Sevilla."
        )

        self.assertEqual(info["address"], "")

    def test_rejects_long_route_context_as_address(self):
        info = extract_contact_info(
            "Ruta. Plaza de la Encarnacion y calle Larana sirven como escenario principal "
            "de una ruta audiovisual por la ciudad."
        )

        self.assertEqual(info["address"], "")


if __name__ == "__main__":
    unittest.main()
