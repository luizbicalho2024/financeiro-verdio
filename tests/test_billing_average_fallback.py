from __future__ import annotations

import ast
from pathlib import Path


def test_faturamento_has_average_contract_fallback() -> None:
    source = Path("pages/5_Faturamento_Verdio_Completo.py").read_text(
        encoding="utf-8"
    )
    assert "Média dos contratos cadastrados" in source
    assert "average_contract_prices" in source
    assert '"Origem Preço"' in source
    assert "Com preço médio" in source
    assert "contracts," in source


def test_cache_signature_includes_contracts() -> None:
    source = Path("pages/5_Faturamento_Verdio_Completo.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
    }
    batch = functions["_billing_batch_signature"]
    arg_names = [arg.arg for arg in batch.args.args]
    assert "contracts" in arg_names
    assert "average_contract_prices" in arg_names


def test_history_normalization_avoids_boolean_or_for_nullable_fields() -> None:
    source = Path("app_core/billing_history_service.py").read_text(
        encoding="utf-8"
    )
    assert "def _first_present(" in source
    assert '_first_present(item, "Data Ativação", "Data Ativacao")' in source
    assert '_first_present(item, "Nº Equipamento", "Equipamento")' in source
    assert 'item.get("Data Ativação") or item.get("Data Ativacao")' not in source


def test_save_error_is_available_to_bulk_ui() -> None:
    userdb = Path("user_management_db.py").read_text(encoding="utf-8")
    page = Path("pages/5_Faturamento_Verdio_Completo.py").read_text(
        encoding="utf-8"
    )
    assert "def get_last_billing_save_error()" in userdb
    assert "get_last_billing_save_error()" in page
