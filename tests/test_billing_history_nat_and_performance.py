from __future__ import annotations

import ast
from datetime import date, datetime, timezone
import math
from pathlib import Path

import pandas as pd


def _load_serializer():
    source_path = Path("app_core/billing_history_service.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    wanted = {"_safe_text", "_serialize"}
    selected_nodes = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in wanted
    ]

    if {node.name for node in selected_nodes} != wanted:
        raise AssertionError("Não foi possível localizar _safe_text/_serialize no módulo.")

    module = ast.Module(body=selected_nodes, type_ignores=[])
    ast.fix_missing_locations(module)

    namespace = {
        "Any": object,
        "date": date,
        "datetime": datetime,
        "timezone": timezone,
        "math": math,
    }
    exec(compile(module, str(source_path), "exec"), namespace)
    return namespace["_serialize"]


def test_billing_serializer_converts_pandas_nat_to_none() -> None:
    serializer = _load_serializer()
    assert serializer(pd.NaT) is None


def test_billing_serializer_converts_timestamp_to_datetime() -> None:
    serializer = _load_serializer()
    value = serializer(pd.Timestamp("2025-01-10 12:30:00"))
    assert value is not None
    assert value.tzinfo is not None


def test_faturamento_page_has_session_batch_cache_and_lazy_exports() -> None:
    source = Path("pages/5_Faturamento_Verdio_Completo.py").read_text(
        encoding="utf-8"
    )

    assert "billing_processed_batch_cache" in source
    assert "Lote reaproveitado da memória da sessão" in source
    assert "Preparar Excel e PDFs" in source
    assert "Adicionar novos equipamentos ao estoque e recalcular" in source
    assert 'col_pdf.download_button(' not in source
    assert 'col_excel.download_button(' not in source


def test_bulk_history_save_suppresses_per_client_ui_spam() -> None:
    page = Path("pages/5_Faturamento_Verdio_Completo.py").read_text(
        encoding="utf-8"
    )
    userdb = Path("user_management_db.py").read_text(encoding="utf-8")

    assert "notify=False" in page
    assert "notify: bool = True" in userdb
