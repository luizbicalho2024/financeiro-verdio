from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from app_core.inventory_import import (
    _read_raw,
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
        csv_data = """Relatório;;;;;;;;
Modelo;Gateway;Nº Equipamento;Nº Série;P/ Entrada;Kit;Status;Tipo Equipamento;Situação
GV55;10016;"8,62193E+14";"8,62193E+14";0;NÃO;Disponível;Comum;Habilitado
GV55;10016;"8,62193E+14";"8,62193E+14";0;NÃO;Disponível;Comum;Habilitado
""".encode("latin1", errors="replace")

        with self.assertRaisesRegex(
            ValueError,
            "identificador abreviado/sem precisão suficiente",
        ):
            parse_inventory_report(csv_data, "estoque.csv")

    def test_full_serial_can_recover_lossy_equipment_column(self):
        csv_data = """Modelo;Gateway;Nº Equipamento;Nº Série;P/ Entrada;Status;Tipo Equipamento;Situação
GV55;10016;"8,62193E+14";862193027848308;0;Disponível;Comum;Habilitado
""".encode("latin1")

        frame, metadata = parse_inventory_report(csv_data, "estoque.csv")

        self.assertEqual(metadata["rows_valid"], 1)
        self.assertEqual(
            frame.iloc[0]["Nº Equipamento"],
            "862193027848308",
        )

    def test_true_duplicate_full_identifier_is_deduplicated(self):
        csv_data = """Modelo;Gateway;Nº Equipamento;P/ Entrada;Status
RST Mini LC 4G;9908;9601092;0;Indisponível
RST Mini LC 4G;9908;9601092;0;Disponível
""".encode("latin1")

        frame, metadata = parse_inventory_report(csv_data, "estoque.csv")

        self.assertEqual(metadata["rows_read"], 2)
        self.assertEqual(metadata["rows_valid"], 1)
        self.assertEqual(metadata["duplicates_removed"], 1)
        self.assertEqual(frame.iloc[0]["Status"], "Disponível")

    def test_column_names_match_gestao_estoque_contract(self):
        csv_data = (
            "Modelo;Gateway;Nº Equipamento;Nº Série;"
            "P/ Entrada;Status;Tipo Equipamento;Situação\n"
            "RST Mini LC 4G;9908;9601092;9601092;0;"
            "Disponível;Comum;Habilitado\n"
        ).encode("latin1")

        frame, metadata = parse_inventory_report(csv_data, "estoque.csv")

        self.assertEqual(metadata["rows_valid"], 1)
        self.assertIn("Nº Equipamento", frame.columns)
        self.assertIn("Nº Série", frame.columns)
        self.assertIn("Situação", frame.columns)
        self.assertNotIn("NÂº Equipamento", frame.columns)
        self.assertEqual(frame.iloc[0]["Nº Equipamento"], "9601092")

    @patch("xlrd.open_workbook")
    def test_corrupted_xls_reader_uses_recovery_mode(self, open_workbook):
        fake_sheet = Mock()
        fake_sheet.nrows = 2
        fake_sheet.row_values.side_effect = [
            ["Modelo", "Nº Equipamento"],
            ["GV55", 862193027848308.0],
        ]

        fake_workbook = Mock()
        fake_workbook.nsheets = 1
        fake_workbook.sheet_by_index.return_value = fake_sheet
        open_workbook.return_value = fake_workbook

        frame = _read_raw(b"arquivo-xls-simulado", "estoque.xls")

        self.assertEqual(len(frame), 2)
        self.assertTrue(
            open_workbook.call_args.kwargs["ignore_workbook_corruption"]
        )
        self.assertEqual(int(frame.iloc[1, 1]), 862193027848308)


if __name__ == "__main__":
    unittest.main()
