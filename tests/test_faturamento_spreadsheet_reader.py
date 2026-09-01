from __future__ import annotations

import pandas as pd

from app_core import spreadsheet_reader


def test_detects_ole_xls_by_binary_signature() -> None:
    payload = spreadsheet_reader.OLE_SIGNATURE + b"\x00" * 32
    assert spreadsheet_reader.detect_spreadsheet_kind(payload, "relatorio.xlsx") == "xls"


def test_detects_zip_xlsx_even_when_extension_is_xls() -> None:
    payload = b"PK\x03\x04" + b"\x00" * 32
    assert spreadsheet_reader.detect_spreadsheet_kind(payload, "relatorio.xls") == "xlsx"


def test_xls_reader_enables_xlrd_corruption_tolerance(monkeypatch) -> None:
    expected = pd.DataFrame([["ok"]])
    captured = {}

    def fake_read_excel(*args, **kwargs):
        captured.update(kwargs)
        return expected

    monkeypatch.setattr(spreadsheet_reader.pd, "read_excel", fake_read_excel)

    result = spreadsheet_reader.read_raw_spreadsheet(
        spreadsheet_reader.OLE_SIGNATURE + b"\x00" * 16,
        "faturamento.xls",
    )

    assert result.equals(expected)
    assert captured["engine"] == "xlrd"
    assert captured["header"] is None
    assert captured["engine_kwargs"]["ignore_workbook_corruption"] is True


def test_empty_upload_has_clear_error() -> None:
    try:
        spreadsheet_reader.read_raw_spreadsheet(b"", "vazio.xls")
    except ValueError as exc:
        assert "vazio" in str(exc).lower()
    else:
        raise AssertionError("Era esperado ValueError para arquivo vazio.")
