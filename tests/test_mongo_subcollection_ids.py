from __future__ import annotations

import ast
import hashlib
from pathlib import Path


def _load_storage_id_helper():
    path = Path("mongo_config.py")
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    nodes = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_subcollection_storage_id"
    ]
    assert len(nodes) == 1

    module = ast.Module(body=nodes, type_ignores=[])
    ast.fix_missing_locations(module)

    namespace = {"hashlib": hashlib}
    exec(compile(module, str(path), "exec"), namespace)
    return namespace["_subcollection_storage_id"]


def test_subcollection_ids_are_unique_between_parents() -> None:
    helper = _load_storage_id_helper()

    first = helper(
        "billing_runs__items",
        "billing_runs",
        "run-a",
        "000000",
    )
    second = helper(
        "billing_runs__items",
        "billing_runs",
        "run-b",
        "000000",
    )

    assert first != second
    assert first.startswith("subdoc_")
    assert second.startswith("subdoc_")


def test_root_document_id_is_preserved() -> None:
    helper = _load_storage_id_helper()
    assert helper("billing_runs", None, None, "abc123") == "abc123"


def test_mongo_compat_preserves_logical_subdocument_id() -> None:
    source = Path("mongo_config.py").read_text(encoding="utf-8")

    assert 'payload["__mongo_document_id"] = self.id' in source
    assert 'document.get("__mongo_document_id")' in source
    assert 'query["_id"] = {"$in": [self._storage_id(), self.id]}' in source
    assert "existing_storage_id or self._storage_id()" in source


def test_billing_item_ids_can_remain_logical_sequence() -> None:
    source = Path("app_core/billing_history_service.py").read_text(
        encoding="utf-8"
    )
    assert 'document(f"{item_index:06d}")' in source
