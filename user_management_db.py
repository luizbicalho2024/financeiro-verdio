from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Iterable

import pandas as pd
import streamlit as st
from mongo_config import db

log = logging.getLogger("financeiro_verdio.database")
DB_BATCH_LIMIT = 450


def _current_user_email() -> str:
    return str(st.session_state.get("user_info", {}).get("email", "sistema") or "sistema").strip().lower()


def _chunks(items: list[Any], size: int = DB_BATCH_LIMIT) -> Iterable[list[Any]]:
    for start in range(0, len(items), size):
        yield items[start:start + size]


# --- LOGS E AUDITORIA -----------------------------------------------------
def log_action(level: str, user: str, message: str, details: Any = None) -> bool:
    try:
        db.collection("system_logs").add(
            {
                "timestamp": datetime.now(timezone.utc),
                "level": str(level or "INFO").upper(),
                "user": str(user or "sistema"),
                "message": str(message or ""),
                "details": details if details is not None else {},
            }
        )
        return True
    except Exception:
        log.exception("Não foi possível registrar log de auditoria.")
        return False


def get_system_logs(limit: int = 2000) -> list[dict[str, Any]]:
    try:
        safe_limit = max(1, min(int(limit), 10000))
        query = (
            db.collection("system_logs")
            .order_by("timestamp", direction="DESCENDING")
            .limit(safe_limit)
        )
        result = []
        for document in query.stream():
            data = document.to_dict()
            data["_id"] = document.id
            result.append(data)
        return result
    except Exception:
        log.exception("Erro ao buscar logs do sistema.")
        st.error("Não foi possível carregar os logs do sistema.")
        return []


# --- FATURAMENTO E HISTÓRICO ---------------------------------------------
def get_billing_history(limit: int = 5000) -> list[dict[str, Any]]:
    try:
        safe_limit = max(1, min(int(limit), 20000))
        query = (
            db.collection("billing_history")
            .order_by("data_geracao", direction="DESCENDING")
            .limit(safe_limit)
        )
        history: list[dict[str, Any]] = []
        for document in query.stream():
            data = document.to_dict()
            data["_id"] = document.id
            history.append(data)
        return history
    except Exception:
        log.exception("Erro ao buscar histórico de faturamento.")
        st.error("Não foi possível carregar o histórico de faturamento.")
        return []


def get_recent_billing(limit: int = 6) -> list[dict[str, Any]]:
    return get_billing_history(limit=max(1, min(int(limit), 20)))


def get_last_billing_for_client(client_name: str) -> dict[str, Any] | None:
    try:
        query = (
            db.collection("billing_history")
            .where("cliente", "==", str(client_name))
            .order_by("data_geracao", direction="DESCENDING")
            .limit(1)
        )
        for document in query.stream():
            data = document.to_dict()
            data["_id"] = document.id
            return data
        return None
    except Exception:
        log.exception("Erro ao buscar último faturamento do cliente %s", client_name)
        return None


def log_faturamento(
    faturamento_data: dict[str, Any],
    detalhes_itens: list[Any] | None = None,
    *,
    notify: bool = True,
) -> bool:
    """Salva o snapshot vigente e preserva revisões diferentes em uma trilha imutável.

    Downloads repetidos do mesmo faturamento não criam novas revisões. Se os dados
    mudarem para o mesmo cliente/período, uma nova revisão é criada em billing_runs
    e billing_history passa a apontar para a versão vigente.
    """
    try:
        from app_core.billing_history_service import billing_payload_hash, persist_billing_analytics, prepare_history_details

        payload = dict(faturamento_data or {})
        cliente = str(payload.get("cliente") or "").strip()
        periodo = str(payload.get("periodo_relatorio") or "").strip()
        user_email = _current_user_email()

        if not cliente or not periodo:
            raise ValueError("Cliente e período são obrigatórios para salvar o faturamento.")

        clean_details = detalhes_itens if isinstance(detalhes_itens, list) else []
        snapshot_hash = billing_payload_hash(payload, clean_details)

        existing_docs = list(
            db.collection("billing_history")
            .where("cliente", "==", cliente)
            .where("periodo_relatorio", "==", periodo)
            .stream()
        )

        primary_data: dict[str, Any] = {}
        if existing_docs:
            primary_data = existing_docs[0].to_dict() or {}
            if str(primary_data.get("snapshot_hash") or "") == snapshot_hash:
                log_action(
                    "INFO",
                    user_email,
                    f"Faturamento idêntico já estava salvo para {cliente} ({periodo}).",
                    {"cliente": cliente, "periodo": periodo, "snapshot_hash": snapshot_hash},
                )
                if notify:
                    st.toast(
                        "Este faturamento já estava salvo; nenhuma revisão duplicada foi criada.",
                        icon="✅",
                    )
                return True

        previous_revision = int(primary_data.get("revision", 1 if existing_docs else 0) or 0)
        revision = previous_revision + 1
        now = datetime.now(timezone.utc)

        payload.update(
            {
                "cliente": cliente,
                "periodo_relatorio": periodo,
                "data_geracao": now,
                "gerado_por": user_email,
                "revision": revision,
                "snapshot_hash": snapshot_hash,
                "schema_version": 2,
            }
        )
        history_details, details_external = prepare_history_details(clean_details)
        if history_details:
            payload["itens_detalhados"] = history_details
        elif clean_details:
            payload["itens_detalhados"] = []
        payload["itens_em_subcolecao"] = bool(details_external)
        payload["itens_detalhados_count"] = len(clean_details)

        analytics_meta = persist_billing_analytics(
            payload,
            clean_details,
            user_email=user_email,
            revision=revision,
            snapshot_hash=snapshot_hash,
            create_run=True,
            source="billing",
        )
        for key, value in analytics_meta.items():
            if value is not None:
                payload[key] = value

        if existing_docs:
            primary = existing_docs[0]
            primary.reference.set(payload)
            for duplicate in existing_docs[1:]:
                duplicate.reference.delete()
            if len(existing_docs) > 1:
                log_action(
                    "WARNING",
                    user_email,
                    "Registros duplicados de faturamento vigente foram consolidados.",
                    {"cliente": cliente, "periodo": periodo, "duplicados_removidos": len(existing_docs) - 1},
                )
        else:
            db.collection("billing_history").add(payload)

        summary = {key: value for key, value in payload.items() if key != "itens_detalhados"}
        log_action(
            "INFO",
            user_email,
            f"Faturamento salvo para {cliente} ({periodo}) — revisão {revision}.",
            summary,
        )
        if notify:
            st.toast(f"Histórico salvo — revisão {revision}.", icon="✅")
        return True
    except Exception:
        log.exception("Erro ao salvar histórico de faturamento.")
        if notify:
            st.error("Não foi possível salvar o histórico de faturamento.")
        return False


def get_billing_runs(limit: int = 5000) -> list[dict[str, Any]]:
    try:
        safe_limit = max(1, min(int(limit), 20000))
        query = (
            db.collection("billing_runs")
            .order_by("data_geracao", direction="DESCENDING")
            .limit(safe_limit)
        )
        runs: list[dict[str, Any]] = []
        for document in query.stream():
            data = document.to_dict() or {}
            data.setdefault("run_id", document.id)
            data["_id"] = document.id
            runs.append(data)
        return runs
    except Exception:
        log.exception("Erro ao buscar revisões imutáveis de faturamento.")
        return []


def get_billing_run_items(run_id: str, limit: int = 20000) -> list[dict[str, Any]]:
    try:
        safe_limit = max(1, min(int(limit), 50000))
        query = (
            db.collection("billing_runs")
            .document(str(run_id))
            .collection("items")
            .order_by("item_index", direction="ASCENDING")
            .limit(safe_limit)
        )
        items: list[dict[str, Any]] = []
        for document in query.stream():
            data = document.to_dict() or {}
            data["_id"] = document.id
            items.append(data)
        return items
    except Exception:
        log.exception("Erro ao buscar itens da revisão %s.", run_id)
        return []


def rebuild_billing_analytics_from_history() -> dict[str, int] | None:
    try:
        from app_core.billing_history_service import rebuild_analytics_from_history

        records = get_billing_history(limit=20000)
        result = rebuild_analytics_from_history(records, user_email=_current_user_email())
        log_action(
            "INFO",
            _current_user_email(),
            "Base analítica de churn reconstruída a partir do histórico de faturamento.",
            result,
        )
        return result
    except Exception:
        log.exception("Erro ao reconstruir analytics de faturamento.")
        st.error("Não foi possível reconstruir a base analítica.")
        return None


def close_billing_month(
    periodo_relatorio: str,
    *,
    total_clientes: int,
    total_terminais: int,
    faturamento_total: float,
) -> bool:
    try:
        from app_core.billing_history_service import close_billing_month as _close_billing_month

        payload = _close_billing_month(
            periodo_relatorio,
            total_clientes=total_clientes,
            total_terminais=total_terminais,
            faturamento_total=faturamento_total,
            closed_by=_current_user_email(),
        )
        log_action(
            "INFO",
            _current_user_email(),
            f"Fechamento mensal registrado para {periodo_relatorio}.",
            payload,
        )
        return True
    except Exception:
        log.exception("Erro ao registrar fechamento mensal de %s.", periodo_relatorio)
        st.error("O histórico foi salvo, mas não foi possível registrar o fechamento mensal.")
        return False


def delete_billing_history(history_id: str) -> bool:
    try:
        db.collection("billing_history").document(str(history_id)).delete()
        log_action(
            "WARNING",
            _current_user_email(),
            "Registro de histórico de faturamento excluído manualmente.",
            {"history_id": history_id},
        )
        return True
    except Exception:
        log.exception("Erro ao excluir histórico %s", history_id)
        st.error("Não foi possível excluir o registro de histórico.")
        return False


# --- ESTOQUE E PREÇOS -----------------------------------------------------
@st.cache_data(ttl=600, show_spinner=False)
def get_tracker_inventory() -> list[dict[str, Any]]:
    try:
        result = []
        for document in db.collection("trackers").stream():
            data = document.to_dict()
            data.setdefault("Nº Equipamento", document.id)
            result.append(data)
        return result
    except Exception:
        log.exception("Erro ao buscar inventário de rastreadores.")
        st.error("Não foi possível carregar o inventário de rastreadores.")
        return []


def update_tracker_inventory(
    df: pd.DataFrame,
    source_file: str | None = None,
) -> int | None:
    try:
        records: list[tuple[str, dict[str, Any]]] = []
        now = datetime.now(timezone.utc)

        extra_fields = [
            "Gateway",
            "P/ Entrada",
            "Status",
            "Tipo Equipamento Origem",
            "Situação",
        ]

        def clean_value(value: Any) -> Any:
            if value is None:
                return ""
            try:
                if pd.isna(value):
                    return ""
            except Exception:
                pass
            text = str(value).strip()
            return "" if text.lower() in {"nan", "nat", "none"} else text

        for _, row in df.iterrows():
            serial_number = clean_value(
                row.get("Nº Equipamento", "")
            )

            if not serial_number:
                continue

            data: dict[str, Any] = {
                "Nº Equipamento": serial_number,
                "Modelo": clean_value(row.get("Modelo", "")),
                "Tipo": clean_value(row.get("Tipo", "")).upper(),
                "updated_at": now,
            }

            for field in extra_fields:
                if field in df.columns:
                    data[field] = clean_value(row.get(field, ""))

            if source_file:
                data["source_file"] = str(source_file).strip()
                data["source_updated_at"] = now

            records.append((serial_number, data))

        for chunk in _chunks(records):
            batch = db.batch()
            for serial_number, data in chunk:
                reference = db.collection("trackers").document(
                    serial_number
                )
                batch.set(reference, data, merge=True)
            batch.commit()

        get_tracker_inventory.clear()
        get_unique_models_and_types.clear()

        log_action(
            "INFO",
            _current_user_email(),
            "Inventário de rastreadores atualizado.",
            {
                "registros": len(records),
                "arquivo_origem": source_file or "",
            },
        )
        return len(records)

    except Exception:
        log.exception("Erro ao atualizar inventário de rastreadores.")
        st.error(
            "Não foi possível salvar o inventário no banco de dados."
        )
        return None


@st.cache_data(ttl=600, show_spinner=False)
def get_unique_models_and_types() -> dict[str, str]:
    try:
        trackers = get_tracker_inventory()
        if not trackers:
            return {}
        frame = pd.DataFrame(trackers)
        if "Modelo" not in frame.columns or "Tipo" not in frame.columns:
            return {}
        frame["Modelo"] = frame["Modelo"].fillna("").astype(str).str.strip()
        frame["Tipo"] = frame["Tipo"].fillna("").astype(str).str.upper().str.strip()
        frame = frame[frame["Modelo"] != ""]
        return frame.groupby("Modelo")["Tipo"].first().to_dict()
    except Exception:
        log.exception("Erro ao buscar modelos únicos.")
        return {}


def update_type_for_models(updates: dict[str, str]) -> tuple[int, list[str]]:
    success_count = 0
    failed_models: list[str] = []

    for model, new_type in updates.items():
        try:
            documents = list(db.collection("trackers").where("Modelo", "==", model).stream())
            if not documents:
                failed_models.append(model)
                continue

            for chunk in _chunks(documents):
                batch = db.batch()
                for document in chunk:
                    batch.update(
                        document.reference,
                        {
                            "Tipo": str(new_type or "").upper().strip(),
                            "updated_at": datetime.now(timezone.utc),
                        },
                    )
                batch.commit()
            success_count += 1
        except Exception:
            log.exception("Erro ao atualizar tipo do modelo %s", model)
            failed_models.append(model)

    get_tracker_inventory.clear()
    get_unique_models_and_types.clear()
    return success_count, failed_models


@st.cache_data(ttl=900, show_spinner=False)
def get_pricing_config() -> dict[str, Any]:
    defaults = {"GPRS": 59.90, "SATELITE": 159.90, "CAMERA": 0.0, "RADIO": 0.0}
    try:
        document = db.collection("settings").document("pricing").get()
        data = document.to_dict() if document.exists else {}
    except Exception:
        log.exception("Erro ao buscar configurações de preço.")
        data = {}

    equipment_types = data.get("TIPO_EQUIPAMENTO", {}) if isinstance(data, dict) else {}
    equipment_types = equipment_types if isinstance(equipment_types, dict) else {}
    normalized_types: dict[str, dict[str, float]] = {}

    for key in set(equipment_types.keys()) | set(defaults.keys()):
        value = equipment_types.get(key, defaults.get(key, 0.0))
        if isinstance(value, (int, float)):
            normalized_types[key] = {"price1": float(value), "price2": float(value), "price3": float(value)}
        elif isinstance(value, dict):
            normalized_types[key] = {
                "price1": float(value.get("price1", 0.0) or 0.0),
                "price2": float(value.get("price2", 0.0) or 0.0),
                "price3": float(value.get("price3", 0.0) or 0.0),
            }
        else:
            normalized_types[key] = {"price1": 0.0, "price2": 0.0, "price3": 0.0}

    return {"TIPO_EQUIPAMENTO": normalized_types}


def update_pricing_config(new_prices: dict[str, Any]) -> bool:
    try:
        payload = dict(new_prices or {})
        payload["updated_at"] = datetime.now(timezone.utc)
        db.collection("settings").document("pricing").set(payload, merge=True)
        get_pricing_config.clear()
        log_action("INFO", _current_user_email(), "Tabelas de preços atualizadas.")
        return True
    except Exception:
        log.exception("Erro ao atualizar preços.")
        st.error("Não foi possível atualizar as tabelas de preços.")
        return False
