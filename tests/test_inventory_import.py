from __future__ import annotations

import unittest

from app_core.inventory_import import (
    normalize_equipment,
    normalize_identifier,
    parse_inventory_report,
)


class InventoryImportTests(unittest.TestCase):
    def test_numeric_excel_imei_is_preserved(self):
        value = 862193027848308.0

        normalized, scientific, lossy = normalize_identifier(value)

        self.assertEqual(normalized, "862193027848308")
        self.assertFalse(scientific)
        self.assertFalse(lossy)

    def test_leading_zero_text_identifier_is_preserved(self):
        self.assertEqual(normalize_equipment("02634331"), "02634331")

    def test_precise_scientific_text_can_be_normalized(self):
        normalized, scientific, lossy = normalize_identifier(
            "8.62311062523715E+14"
        )

        self.assertEqual(normalized, "862311062523715")
        self.assertTrue(scientific)
        self.assertFalse(lossy)

    def test_lossy_scientific_csv_is_rejected(self):
        csv_data = """RelatÃ³rio;;;;;;;;
Modelo;Gateway;NÂº Equipamento;NÂº SÃ©rie;P/ Entrada;Kit;Status;Tipo Equipamento;SituaÃ§Ã£o
GV55;10016;"8,62193E+14";"8,62193E+14";0;NÃƒO;DisponÃ­vel;Comum;Habilitado
GV55;10016;"8,62193E+14";"8,62193E+14";0;NÃƒO;DisponÃ­vel;Comum;Habilitado
""".encode("latin1", errors="replace")

        with self.assertRaisesRegex(
            ValueError,
            "identificador abreviado/sem precisÃ£o suficiente",
        ):
            parse_inventory_report(csv_data, "estoque.csv")

    def test_full_serial_can_recover_lossy_equipment_column(self):
        csv_data = """Modelo;Gateway;NÂº Equipamento;NÂº SÃ©rie;P/ Entrada;Status;Tipo Equipamento;SituaÃ§Ã£o
GV55;10016;"8,62193E+14";862193027848308;0;DisponÃ­vel;Comum;Habilitado
""".encode("latin1")

        frame, metadata = parse_inventory_report(csv_data, "estoque.csv")

        self.assertEqual(metadata["rows_valid"], 1)
        self.assertEqual(
            frame.iloc[0]["NÂº Equipamento"],
            "862193027848308",
        )

    def test_true_duplicate_full_identifier_is_deduplicated(self):
        csv_data = """Modelo;Gateway;NÂº Equipamento;P/ Entrada;Status
RST Mini LC 4G;9908;9601092;0;IndisponÃ­vel
RST Mini LC 4G;9908;9601092;0;DisponÃ­vel
""".encode("latin1")

        frame, metadata = parse_inventory_report(csv_data, "estoque.csv")

        self.assertEqual(metadata["rows_read"], 2)
        self.assertEqual(metadata["rows_valid"], 1)
        self.assertEqual(metadata["duplicates_removed"], 1)
        self.assertEqual(frame.iloc[0]["Status"], "Dispon\u00edvel")


if __name__ == "__main__":
    unittest.main()
