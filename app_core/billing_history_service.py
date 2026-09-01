from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from datetime import date, datetime, timezone
from typing import Any, Iterable


from mongo_config import db

DB_BATCH_LIMIT = 420
MONTHS_PT = {
    "janeiro": 1,
    "fevereiro": 2,
    "marco": 3,
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
}


def _strip_accents(value: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", str(value or ""))
        if not unicodedata.combining(ch)
    )


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "nat", "none", "<na>"} else text


def _is_missing_value(value: Any) -> bool:
    if value is None:
        return True
    if value.__class__.__name__ in {"NaTType", "NAType"}:
        return True
    if isinstance(value, float):
        return math.isnan(value) or math.isinf(value)
    text = str(value).strip().lower()
    return text in {"", "nan", "nat", "none", "<na>"}


def _first_present(item: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = item.get(key)
        if not _is_missing_value(value):
            return value
    return None


def _safe_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return float(default)
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        number = float(value)
        return float(default) if math.isnan(number) or math.isinf(number) else number
    text = _safe_text(value).replace("R$", "").replace(" ", "")
    if not text:
        return float(default)
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        number = float(text)
        return float(default) if math.isnan(number) or math.isinf(number) else number
    except (TypeError, ValueError):
        return float(default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(round(_safe_float(value, float(default))))
    except (TypeError, ValueError):
        return int(default)


def _serialize(value: Any) -> Any:
    """Converte tipos comuns de pandas/numpy/datetime para valores aceitos pelo MongoDB e JSON."""
    if value is None:
        return None

    if value.__class__.__name__ in {"NaTType", "NAType"}:
        return None

    if isinstance(value, datetime):
        try:
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            return None
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return None if math.isnan(value) or math.isinf(value) else value
    if isinstance(value, dict):
        return {str(key): _serialize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_serialize(item) for item in value]

    # pandas / numpy sem importar dependências pesadas aqui.
    if hasattr(value, "to_pydatetime"):
        try:
            converted = value.to_pydatetime()
            if converted is not value:
                return _serialize(converted)
        except Exception:
            pass
    if hasattr(value, "item"):
        try:
            return _serialize(value.item())
        except Exception:
            pass

    text = _safe_text(value)
    return text or None


def normalize_detail_item(item: dict[str, Any], *, cliente: str, period_key: str, run_id: str) -> dict[str, Any]:
    categoria = _safe_text(item.get("Categoria"))
    return {
        "cliente": cliente,
        "period_key": period_key,
        "run_id": run_id,
        "terminal": _safe_text(item.get("Terminal")),
        "equipamento": _safe_text(
            _first_present(item, "Nº Equipamento", "Equipamento")
        ),
        "placa": _safe_text(item.get("Placa")),
        "frota": _safe_text(item.get("Frota")),
        "modelo": _safe_text(item.get("Modelo")),
        "tipo": _safe_text(item.get("Tipo")).upper(),
        "condicao": _safe_text(
            _first_present(item, "Condição", "Condicao")
        ),
        "categoria": categoria,
        "data_ativacao": _serialize(
            _first_present(item, "Data Ativação", "Data Ativacao")
        ),
        "data_desativacao": _serialize(
            _first_present(item, "Data Desativação", "Data Desativacao")
        ),
        "dias_ativos_mes": _safe_int(
            _first_present(item, "Dias Ativos Mês", "Dias Ativos Mes")
        ),
        "dias_ativos_calculado": _safe_int(item.get("Dias Ativos Calculado")),
        "suspenso_dias_mes": _safe_int(
            _first_present(item, "Suspenso Dias Mes", "Suspenso Dias Mês")
        ),
        "dias_a_faturar": _safe_int(item.get("Dias a Faturar")),
        "valor_unitario": round(_safe_float(item.get("Valor Unitario")), 2),
        "valor_faturado": round(_safe_float(item.get("Valor a Faturar")), 2),
        "updated_at": datetime.now(timezone.utc),
    }


def period_key_from_label(period_label: str) -> str:
    text = _strip_accents(_safe_text(period_label)).lower()
    match = re.search(r"\b([a-z]+)\s+de\s+(\d{4})\b", text)
    if match:
        month = MONTHS_PT.get(match.group(1))
        if month:
            return f"{int(match.group(2)):04d}-{month:02d}"

    numeric = re.search(r"\b(\d{4})[-/](\d{1,2})\b", text)
    if numeric:
        year = int(numeric.group(1))
        month = int(numeric.group(2))
        if 1 <= month <= 12:
            return f"{year:04d}-{month:02d}"

    return ""


def period_label_from_key(period_key: str) -> str:
    reverse = {month: name.capitalize() for name, month in MONTHS_PT.items()}
    try:
        year, month = (int(part) for part in period_key.split("-", 1))
        return f"{reverse.get(month, str(month))} de {year}"
    except Exception:
        return period_key


def _json_safe(value: Any) -> Any:
    serialized = _serialize(value)
    if isinstance(serialized, datetime):
        return serialized.isoformat()
    if isinstance(serialized, dict):
        return {str(k): _json_safe(v) for k, v in serialized.items()}
    if isinstance(serialized, (list, tuple)):
        return [_json_safe(v) for v in serialized]
    return serialized


def billing_payload_hash(summary: dict[str, Any], details: list[dict[str, Any]] | None = None) -> str:
    ignored = {"data_geracao", "gerado_por", "updated_at", "latest_run_id", "revision", "snapshot_hash"}
    normalized_summary = {
        str(k): _json_safe(v)
        for k, v in sorted((summary or {}).items(), key=lambda pair: str(pair[0]))
        if k not in ignored
    }
    normalized_details = []
    for item in details or []:
        clean = {str(k): _json_safe(v) for k, v in sorted(item.items(), key=lambda pair: str(pair[0]))}
        normalized_details.append(clean)
    normalized_details.sort(
        key=lambda item: (
            str(item.get("Terminal") or item.get("terminal") or ""),
            str(item.get("Nº Equipamento") or item.get("Equipamento") or item.get("equipamento") or ""),
        )
    )
    payload = json.dumps(
        {"summary": normalized_summary, "details": normalized_details},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()



def prepare_history_details(details: list[dict[str, Any]] | None, max_bytes: int = 8_000_000) -> tuple[list[dict[str, Any]], bool]:
    """Mantém billing_history com margem abaixo do limite de 16 MB do MongoDB.

    A cópia completa sempre fica em billing_runs/{run_id}/items e em snapshots.
    billing_history mantém os itens somente quando couberem com margem de segurança.
    """
    safe_details: list[dict[str, Any]] = []
    for item in details or []:
        if not isinstance(item, dict):
            continue
        safe_details.append({str(key): _json_safe(value) for key, value in item.items()})
    encoded = json.dumps(safe_details, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
    if len(encoded) <= max(32_000, int(max_bytes)):
        return safe_details, False
    return [], bool(safe_details)

def _chunks(items: list[Any], size: int = DB_BATCH_LIMIT) -> Iterable[list[Any]]:
    for start in range(0, len(items), size):
        yield items[start:start + size]


def _snapshot_doc_id(period_key: str, cliente: str, terminal: str, equipamento: str) -> str:
    raw = f"{period_key}|{cliente}|{terminal}|{equipamento}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest()


def _metrics_doc_id(period_key: str, cliente: str) -> str:
    digest = hashlib.sha1(cliente.strip().lower().encode("utf-8")).hexdigest()[:20]
    return f"{period_key}__{digest}"


def _category_flags(item: dict[str, Any]) -> tuple[bool, bool, bool, bool]:
    category = _strip_accents(_safe_text(item.get("categoria"))).lower()
    activated = "ativado no mes" in category or "ativado e desativado" in category
    deactivated = category == "desativado" or "ativado e desativado" in category
    suspended = category == "suspenso" or _safe_int(item.get("suspenso_dias_mes")) > 0
    active_end = not deactivated
    return activated, deactivated, suspended, active_end


def build_monthly_metrics(
    summary: dict[str, Any],
    normalized_items: list[dict[str, Any]],
    *,
    period_key: str,
    period_label: str,
    cliente: str,
    run_id: str,
    data_quality: str = "detalhado",
) -> dict[str, Any]:
    activations = deactivations = suspensions = active_end = 0
    for item in normalized_items:
        activated, deactivated, suspended, is_active_end = _category_flags(item)
        activations += int(activated)
        deactivations += int(deactivated)
        suspensions += int(suspended)
        active_end += int(is_active_end)

    if not normalized_items:
        # Histórico muito antigo pode não ter item a item. Mantemos os totais disponíveis,
        # sinalizando a qualidade para o Comercial não interpretar como dado exato.
        active_end = (
            _safe_int(summary.get("terminais_cheio"))
            + _safe_int(summary.get("terminais_proporcional"))
            + _safe_int(summary.get("terminais_suspensos"))
        )
        data_quality = "resumo_legado"

    return {
        "period_key": period_key,
        "periodo_relatorio": period_label,
        "cliente": cliente,
        "receita": round(_safe_float(summary.get("valor_total")), 2),
        "veiculos_faturados": len(normalized_items) if normalized_items else max(active_end, 0),
        "veiculos_ativos_fim_mes": max(active_end, 0),
        "ativacoes": activations,
        "desativacoes": deactivations,
        "suspensoes": suspensions,
        "terminais_cheio": _safe_int(summary.get("terminais_cheio")),
        "terminais_proporcional": _safe_int(summary.get("terminais_proporcional")),
        "terminais_suspensos": _safe_int(summary.get("terminais_suspensos")),
        "terminais_gprs": _safe_int(summary.get("terminais_gprs")),
        "terminais_satelitais": _safe_int(summary.get("terminais_satelitais")),
        "data_quality": data_quality,
        "source_run_id": run_id,
        "updated_at": datetime.now(timezone.utc),
        "schema_version": 2,
    }


def persist_billing_analytics(
    summary: dict[str, Any],
    details: list[dict[str, Any]] | None,
    *,
    user_email: str,
    revision: int,
    snapshot_hash: str,
    create_run: bool = True,
    source: str = "billing",
) -> dict[str, Any]:
    """Persiste revisão imutável, snapshots de terminais e métricas mensais.

    `billing_history` continua sendo o snapshot vigente. Esta função cria a trilha
    imutável e as projeções analíticas consumidas pelo Simulador Comercial.
    """
    payload = dict(summary or {})
    cliente = _safe_text(payload.get("cliente"))
    period_label = _safe_text(payload.get("periodo_relatorio"))
    period_key = _safe_text(payload.get("period_key")) or period_key_from_label(period_label)
    if not cliente or not period_key:
        raise ValueError("Cliente e período são obrigatórios para persistir analytics de faturamento.")

    now = datetime.now(timezone.utc)
    run_ref = db.collection("billing_runs").document()
    run_id = run_ref.id if create_run else f"backfill-{_metrics_doc_id(period_key, cliente)}"

    normalized_items = [
        normalize_detail_item(item, cliente=cliente, period_key=period_key, run_id=run_id)
        for item in (details or [])
        if isinstance(item, dict)
    ]

    if create_run:
        run_payload = {
            **{k: _serialize(v) for k, v in payload.items() if k != "itens_detalhados"},
            "run_id": run_id,
            "period_key": period_key,
            "periodo_relatorio": period_label or period_label_from_key(period_key),
            "cliente": cliente,
            "revision": int(revision),
            "snapshot_hash": snapshot_hash,
            "item_count": len(normalized_items),
            "data_geracao": now,
            "gerado_por": _safe_text(user_email) or "sistema",
            "source": source,
            "schema_version": 2,
        }
        run_ref.set(run_payload)

        for chunk_index, chunk in enumerate(_chunks(normalized_items)):
            batch = db.batch()
            offset = chunk_index * DB_BATCH_LIMIT
            for local_index, item in enumerate(chunk):
                item_index = offset + local_index
                item_doc = dict(item)
                item_doc["item_index"] = item_index
                ref = run_ref.collection("items").document(f"{item_index:06d}")
                batch.set(ref, item_doc)
            batch.commit()

    # Snapshot oficial por terminal/mês: reprocessamentos substituem somente a visão vigente,
    # enquanto billing_runs preserva todas as versões.
    snapshot_records: list[tuple[str, dict[str, Any]]] = []
    for item in normalized_items:
        doc_id = _snapshot_doc_id(
            period_key,
            cliente,
            _safe_text(item.get("terminal")),
            _safe_text(item.get("equipamento")),
        )
        snapshot_records.append((doc_id, item))

    for chunk in _chunks(snapshot_records):
        batch = db.batch()
        for doc_id, item in chunk:
            batch.set(db.collection("billing_terminal_snapshots").document(doc_id), item, merge=True)
        batch.commit()

    metrics = build_monthly_metrics(
        payload,
        normalized_items,
        period_key=period_key,
        period_label=period_label or period_label_from_key(period_key),
        cliente=cliente,
        run_id=run_id,
        data_quality="detalhado" if normalized_items else "resumo_legado",
    )
    db.collection("billing_monthly_metrics").document(_metrics_doc_id(period_key, cliente)).set(metrics, merge=True)

    return {
        "period_key": period_key,
        "latest_run_id": run_id if create_run else None,
        "revision": int(revision),
        "snapshot_hash": snapshot_hash,
        "analytics_updated_at": now,
    }


def close_billing_month(
    period_label: str,
    *,
    total_clientes: int,
    total_terminais: int,
    faturamento_total: float,
    closed_by: str,
) -> dict[str, Any]:
    period_key = period_key_from_label(period_label)
    if not period_key:
        raise ValueError(f"Não foi possível identificar o período: {period_label}")

    payload = {
        "period_key": period_key,
        "periodo_relatorio": period_label,
        "status": "closed",
        "total_clientes": int(total_clientes),
        "total_terminais": int(total_terminais),
        "faturamento_total": round(_safe_float(faturamento_total), 2),
        "closed_at": datetime.now(timezone.utc),
        "closed_by": _safe_text(closed_by) or "sistema",
        "schema_version": 2,
    }
    db.collection("billing_month_closures").document(period_key).set(payload, merge=True)
    return payload


def rebuild_analytics_from_history(records: list[dict[str, Any]], *, user_email: str) -> dict[str, int]:
    processed = detailed = legacy = failed = 0
    for record in records or []:
        try:
            payload = dict(record)
            payload.pop("_id", None)
            details = payload.pop("itens_detalhados", None)
            details = details if isinstance(details, list) else []
            digest = billing_payload_hash(payload, details)
            persist_billing_analytics(
                payload,
                details,
                user_email=user_email,
                revision=_safe_int(payload.get("revision"), 1) or 1,
                snapshot_hash=digest,
                create_run=False,
                source="history_backfill",
            )
            processed += 1
            if details:
                detailed += 1
            else:
                legacy += 1
        except Exception:
            failed += 1
    return {
        "processed": processed,
        "detailed": detailed,
        "legacy": legacy,
        "failed": failed,
    }
