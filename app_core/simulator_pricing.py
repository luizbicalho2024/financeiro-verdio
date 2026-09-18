from __future__ import annotations

import os
import re
import unicodedata
from datetime import datetime
from typing import Any, Iterable

import streamlit as st
from pymongo import MongoClient


DEFAULT_SIMULATOR_DB = "simulador_db"
CONTRACT_MARGIN_FLOOR_PERCENT = 15.0


def _secret(*names: str, default: str = "") -> str:
    for name in names:
        try:
            value = st.secrets.get(name)
        except Exception:
            value = None
        if value in (None, ""):
            value = os.getenv(name)
        if value not in (None, ""):
            return str(value).strip()
    return default


@st.cache_resource(show_spinner=False)
def get_simulator_client() -> MongoClient:
    """Retorna o cliente Mongo usado para ler o catálogo do Simulador.

    Por padrão reutiliza a mesma conexão do Financeiro. Caso os apps usem
    clusters distintos, basta definir SIMULADOR_MONGO_CONNECTION_STRING.
    """
    uri = _secret("SIMULADOR_MONGO_CONNECTION_STRING")
    if not uri:
        # Import tardio: permite importar e testar as funcoes puras deste
        # modulo sem inicializar o MongoDB nem exigir Secrets locais.
        from mongo_config import get_mongo_client

        return get_mongo_client()

    client = MongoClient(
        uri,
        serverSelectionTimeoutMS=10_000,
        connectTimeoutMS=10_000,
        socketTimeoutMS=20_000,
        retryWrites=True,
        tz_aware=True,
        appname="financeiro-verdio-simulador-pricing",
    )
    client.admin.command("ping")
    return client


def get_simulator_db_name() -> str:
    return _secret("SIMULADOR_MONGO_DB", default=DEFAULT_SIMULATOR_DB) or DEFAULT_SIMULATOR_DB


@st.cache_data(ttl=300, show_spinner=False)
def get_simulator_pricing() -> dict[str, Any]:
    """Lê a fonte oficial de preços/produtos do Simulador de Telemetria."""
    client = get_simulator_client()
    database = client[get_simulator_db_name()]
    document = database["pricing_config"].find_one({"_id": "global_prices"})
    if not document:
        raise RuntimeError(
            "O documento simulador_db.pricing_config/global_prices não foi encontrado. "
            "Cadastre os preços em 'Preços e produtos' no Simulador."
        )
    document = dict(document)
    document.pop("_id", None)
    document["_source_database"] = get_simulator_db_name()
    return document


def clear_simulator_pricing_cache() -> None:
    get_simulator_pricing.clear()


def _norm(value: Any) -> str:
    text = "" if value is None else str(value)
    text = "".join(
        char
        for char in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(char)
    )
    text = re.sub(r"[^a-zA-Z0-9]+", " ", text).strip().lower()
    return re.sub(r"\s+", " ", text)


def _plan_months(plan_name: str) -> int | None:
    match = re.search(r"(\d+)", str(plan_name or ""))
    return int(match.group(1)) if match else None


def sorted_plan_names(pricing: dict[str, Any]) -> list[str]:
    plans = pricing.get("PLANOS_PJ", {})
    if not isinstance(plans, dict):
        return []
    return sorted(
        [str(name) for name in plans.keys()],
        key=lambda name: (_plan_months(name) is None, _plan_months(name) or 999999, name),
    )


def select_plan_name(pricing: dict[str, Any], contract_months: int | float | str) -> str | None:
    plans = sorted_plan_names(pricing)
    if not plans:
        return None
    try:
        months = max(1, int(contract_months))
    except (TypeError, ValueError):
        months = 12

    exact = [plan for plan in plans if _plan_months(plan) == months]
    if exact:
        return exact[0]

    with_months = [(plan, _plan_months(plan)) for plan in plans]
    with_months = [(plan, value) for plan, value in with_months if value is not None]
    if not with_months:
        return plans[0]
    return min(with_months, key=lambda item: (abs(item[1] - months), item[1]))[0]


def all_products(pricing: dict[str, Any]) -> list[str]:
    products: set[str] = set()
    for plan_products in pricing.get("PLANOS_PJ", {}).values():
        if isinstance(plan_products, dict):
            products.update(str(product) for product in plan_products.keys())
    return sorted(products)


def billing_type_for_product(product_name: str) -> str:
    normalized = _norm(product_name)
    if any(token in normalized for token in ("gprs", "gsm")):
        return "GPRS"
    if "satelit" in normalized:
        return "SATELITE"
    if any(token in normalized for token in ("videomonitor", "camera", "dms", "adas")):
        return "CAMERA"
    if "can" in normalized or "telemetria" in normalized:
        return "CAN"
    if "rfid" in normalized or "identificador" in normalized:
        return "RFID"
    if "radio" in normalized:
        return "RADIO"
    return re.sub(r"\s+", "_", normalized.upper())[:40] or "OUTRO"


def resolve_product_name(label: Any, pricing: dict[str, Any]) -> str | None:
    products = all_products(pricing)
    if not products:
        return None

    normalized_label = _norm(label)
    if not normalized_label:
        return None

    exact = { _norm(product): product for product in products }
    if normalized_label in exact:
        return exact[normalized_label]

    target_type = billing_type_for_product(str(label))
    for product in products:
        if billing_type_for_product(product) == target_type:
            return product

    label_tokens = set(normalized_label.split())
    scored: list[tuple[int, str]] = []
    for product in products:
        product_tokens = set(_norm(product).split())
        score = len(label_tokens & product_tokens)
        if score:
            scored.append((score, product))
    if scored:
        scored.sort(key=lambda item: (-item[0], item[1]))
        return scored[0][1]
    return None


def product_price_cost(
    pricing: dict[str, Any],
    plan_name: str,
    product_name: str,
) -> tuple[float, float]:
    plans = pricing.get("PLANOS_PJ", {})
    costs = pricing.get("CUSTOS_PJ", {})
    sale = float((plans.get(plan_name, {}) or {}).get(product_name, 0.0) or 0.0)
    cost = float((costs.get(plan_name, {}) or {}).get(product_name, 0.0) or 0.0)
    return sale, cost


def pricing_matrix(pricing: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    plans = sorted_plan_names(pricing)
    install = pricing.get("INSTALACAO_PJ", {}) or {}
    for product in all_products(pricing):
        row: dict[str, Any] = {
            "Produto": product,
            "Tipo faturamento": billing_type_for_product(product),
        }
        for plan in plans:
            sale, cost = product_price_cost(pricing, plan, product)
            margin = ((sale - cost) / sale * 100.0) if sale > 0 and cost > 0 else None
            row[f"Preço {plan}"] = sale
            row[f"Custo {plan}"] = cost
            row[f"Margem {plan}"] = margin
        installation = install.get(product, {}) if isinstance(install, dict) else {}
        row["Instalação venda"] = float((installation or {}).get("preco_venda", 0.0) or 0.0)
        row["Instalação custo"] = float((installation or {}).get("custo", 0.0) or 0.0)
        rows.append(row)
    return rows


def legacy_equipment_pricing(pricing: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Compatibilidade com páginas legadas do Financeiro.

    price1/price2/price3 seguem a ordem dos prazos do Simulador (ex.: 12/24/36).
    As telas novas usam PLANOS_PJ diretamente e não dependem desses aliases.
    """
    plans = sorted_plan_names(pricing)
    aliases: dict[str, dict[str, Any]] = {}
    for product in all_products(pricing):
        billing_type = billing_type_for_product(product)
        if billing_type == "OUTRO":
            continue
        values: list[float] = []
        plan_values: dict[str, float] = {}
        for plan in plans:
            sale, _ = product_price_cost(pricing, plan, product)
            values.append(sale)
            plan_values[plan] = sale
        while len(values) < 3:
            values.append(values[-1] if values else 0.0)
        aliases[billing_type] = {
            "price1": values[0],
            "price2": values[1],
            "price3": values[2],
            "product": product,
            "plans": plan_values,
        }
    return aliases


def contract_product_values(
    contract: dict[str, Any],
    pricing: dict[str, Any],
) -> tuple[dict[str, float], dict[str, int]]:
    prices = {
        str(key): float(value or 0.0)
        for key, value in (contract.get("precos_produtos", {}) or {}).items()
    }
    quantities = {
        str(key): max(0, int(value or 0))
        for key, value in (contract.get("quantidades_produtos", {}) or {}).items()
    }

    legacy_prices = contract.get("precos_por_tipo", {}) or {}
    for product in all_products(pricing):
        if product not in prices:
            billing_type = billing_type_for_product(product)
            raw = legacy_prices.get(billing_type)
            if raw is None:
                raw = legacy_prices.get(product)
            if raw is not None:
                prices[product] = float(raw or 0.0)
        quantities.setdefault(product, 0)
    return prices, quantities


def legacy_contract_prices(product_prices: dict[str, float]) -> dict[str, float]:
    result: dict[str, float] = {}
    for product, value in product_prices.items():
        billing_type = billing_type_for_product(product)
        if billing_type and float(value or 0.0) > 0:
            result[billing_type] = float(value)
    return result


def item_mix_from_billing_items(
    items: Iterable[dict[str, Any]],
    pricing: dict[str, Any],
) -> dict[str, int]:
    mix: dict[str, int] = {}
    for item in items or []:
        category = str(item.get("Categoria") or item.get("categoria") or "").strip().lower()
        if category == "suspenso":
            continue
        label = (
            item.get("Tipo")
            or item.get("tipo")
            or item.get("Modelo")
            or item.get("modelo")
            or ""
        )
        product = resolve_product_name(label, pricing)
        if product:
            mix[product] = mix.get(product, 0) + 1
    return mix


def calculate_contract_margin(
    pricing: dict[str, Any],
    contract_months: int,
    product_prices: dict[str, float],
    product_quantities: dict[str, int] | None = None,
    fallback_mix: dict[str, int] | None = None,
) -> dict[str, Any]:
    plan = select_plan_name(pricing, contract_months)
    if not plan:
        return {
            "plan": None,
            "margin_percent": None,
            "revenue": 0.0,
            "cost": 0.0,
            "costs_complete": False,
            "used_mix": {},
        }

    configured = {
        product: float(price or 0.0)
        for product, price in product_prices.items()
        if float(price or 0.0) > 0
    }
    quantities = {product: max(0, int(qty or 0)) for product, qty in (product_quantities or {}).items()}
    if not any(quantities.get(product, 0) > 0 for product in configured):
        quantities = {product: max(0, int(qty or 0)) for product, qty in (fallback_mix or {}).items()}
    if not any(quantities.get(product, 0) > 0 for product in configured):
        quantities = {product: 1 for product in configured}

    total_revenue = 0.0
    total_cost = 0.0
    costs_complete = True
    used_mix: dict[str, int] = {}

    for product, contract_price in configured.items():
        qty = quantities.get(product, 0)
        if qty <= 0:
            continue
        _, cost = product_price_cost(pricing, plan, product)
        if cost <= 0:
            costs_complete = False
        total_revenue += contract_price * qty
        total_cost += cost * qty
        used_mix[product] = qty

    margin_percent = None
    if total_revenue > 0 and costs_complete:
        margin_percent = ((total_revenue - total_cost) / total_revenue) * 100.0

    return {
        "plan": plan,
        "margin_percent": margin_percent,
        "revenue": total_revenue,
        "cost": total_cost,
        "costs_complete": costs_complete,
        "used_mix": used_mix,
    }


def parse_period_key(record: dict[str, Any]) -> str | None:
    period_key = str(record.get("period_key") or "").strip()
    match = re.search(r"(20\d{2})[-/](0?[1-9]|1[0-2])", period_key)
    if match:
        return f"{int(match.group(1)):04d}-{int(match.group(2)):02d}"

    period_text = str(record.get("periodo_relatorio") or "").strip()
    months_pt = {
        "janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5, "junho": 6,
        "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
    }
    normalized_period = _norm(period_text)
    year_match = re.search(r"(20\d{2})", normalized_period)
    if year_match:
        for month_name, month_number in months_pt.items():
            if month_name in normalized_period:
                return f"{int(year_match.group(1)):04d}-{month_number:02d}"

    generated = record.get("data_geracao")
    if isinstance(generated, datetime):
        return generated.strftime("%Y-%m")
    try:
        parsed = datetime.fromisoformat(str(generated).replace("Z", "+00:00"))
        return parsed.strftime("%Y-%m")
    except Exception:
        return None


def first_three_billings(
    history: Iterable[dict[str, Any]],
    client_name: str,
    contract_start: str | None = None,
) -> list[dict[str, Any]]:
    target = _norm(client_name)
    start_key = None
    if contract_start:
        match = re.match(r"(20\d{2})-(0?[1-9]|1[0-2])", str(contract_start))
        if match:
            start_key = f"{int(match.group(1)):04d}-{int(match.group(2)):02d}"

    candidates: list[tuple[str, dict[str, Any]]] = []
    seen: set[str] = set()
    for record in history:
        if _norm(record.get("cliente")) != target:
            continue
        key = parse_period_key(record)
        if not key or key in seen:
            continue
        if start_key and key < start_key:
            continue
        candidates.append((key, record))
        seen.add(key)

    candidates.sort(key=lambda item: item[0])
    return [record for _, record in candidates[:3]]
