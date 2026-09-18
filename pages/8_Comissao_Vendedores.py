from __future__ import annotations

import io
import os
import sys
from typing import Any

import pandas as pd
import streamlit as st

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app_core.simulator_pricing import (
    CONTRACT_MARGIN_FLOOR_PERCENT,
    calculate_contract_margin,
    contract_product_values,
    first_three_billings,
    get_simulator_db_name,
    get_simulator_pricing,
    item_mix_from_billing_items,
    parse_period_key,
    product_price_cost,
    resolve_product_name,
    select_plan_name,
)
from app_core.ui import apply_branding, render_sidebar
from mongo_config import db
import user_management_db as umdb

st.set_page_config(
    layout="wide",
    page_title="Premiação de Vendedores",
    page_icon="💰",
)
apply_branding()

if "user_info" not in st.session_state:
    st.error("Acesso negado. Faça login para continuar.")
    st.stop()

if st.session_state.get("role", "Usuário").lower() != "admin":
    st.error("Esta página é restrita aos administradores.")
    st.stop()

render_sidebar()


def get_contracts() -> dict[str, dict]:
    try:
        return {
            document.id: document.to_dict()
            for document in db.collection("client_contracts").stream()
        }
    except Exception as exc:
        st.error(f"Não foi possível carregar os contratos: {exc}")
        return {}


def get_legacy_seller_mappings() -> dict[str, str]:
    try:
        document = db.collection("settings").document("seller_mappings").get()
        data = document.to_dict() if document.exists else {}
        return {
            str(key).strip(): str(value).strip()
            for key, value in (data or {}).items()
            if str(value).strip()
        }
    except Exception:
        return {}


def get_commission_settings() -> dict[str, Any]:
    defaults = {"bonus_ativacao": 50.0}
    try:
        document = db.collection("settings").document("commission_rules").get()
        data = document.to_dict() if document.exists else {}
        result = defaults.copy()
        result.update(data or {})
        return result
    except Exception:
        return defaults


def save_commission_settings(data: dict[str, Any]) -> bool:
    try:
        db.collection("settings").document("commission_rules").set(
            data, merge=True
        )
        return True
    except Exception as exc:
        st.error(f"Não foi possível salvar os parâmetros: {exc}")
        return False


def get_tier_percent(unit_value: float, base_value: float) -> float:
    """Mantém a política de faixas já usada pelo Financeiro."""
    if base_value <= 0:
        return 0.0
    ratio = unit_value / base_value
    if ratio < 0.80:
        return 0.0
    if ratio < 1.00:
        return 0.02
    if ratio < 1.20:
        return 0.15
    return 0.30


def _float(item: dict[str, Any], *keys: str, default: float = 0.0) -> float:
    for key in keys:
        if key not in item:
            continue
        try:
            return float(item.get(key) or 0.0)
        except (TypeError, ValueError):
            continue
    return float(default)


def _text(item: dict[str, Any], *keys: str, default: str = "") -> str:
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return default


def billing_items(record: dict[str, Any]) -> list[dict[str, Any]]:
    details = record.get("itens_detalhados")
    if isinstance(details, list) and details:
        return [item for item in details if isinstance(item, dict)]
    run_id = record.get("latest_run_id")
    if run_id:
        return umdb.get_billing_run_items(str(run_id))
    return []


def contract_reference_price(
    contract: dict[str, Any],
    pricing: dict[str, Any],
    plan: str,
    product: str,
) -> float:
    snapshot = contract.get("precos_tabela_produtos", {}) or {}
    if product in snapshot:
        try:
            value = float(snapshot.get(product) or 0.0)
            if value > 0:
                return value
        except (TypeError, ValueError):
            pass
    sale, _ = product_price_cost(pricing, plan, product)
    return sale


st.title("Premiação de Vendedores — Verdio")
st.markdown(
    "A apuração passa a seguir duas etapas: **(1) contrato** e **(2) faturamento dos três "
    "primeiros meses**. A etapa de contrato exige margem mínima de **15%**."
)

try:
    pricing = get_simulator_pricing()
except Exception as exc:
    st.error(
        "Não foi possível carregar os preços/custos oficiais do Simulador. "
        f"Detalhe: {exc}"
    )
    st.stop()

st.caption(
    f"Fonte de preços/produtos: **{get_simulator_db_name()}.pricing_config/global_prices**. "
    "Contratos novos preservam um snapshot econômico para que reajustes futuros não alterem a margem histórica."
)

commission_settings = get_commission_settings()
with st.expander("Parâmetros e política", expanded=False):
    left, right = st.columns([2.2, 1])
    with left:
        st.markdown(
            """
**Etapa 1 — Contrato**
- prêmio por ativação/unidade contratada;
- somente elegível quando a margem contratual comprovada for **>= 15%**;
- custo não cadastrado impede a comprovação da margem.

**Etapa 2 — Faturas 1, 2 e 3**
- usa o valor realmente faturado no Histórico de Faturamento;
- a faixa é definida pelo valor unitário contratado comparado ao preço-base do Simulador;
- `< 80% = 0%`, `80% a <100% = 2%`, `100% a <120% = 15%`, `>=120% = 30%`;
- a comissão incide sobre o valor efetivamente faturado, inclusive quando houver pró-rata.
            """
        )
    with right:
        bonus_input = st.number_input(
            "Premiação de contrato por ativação (R$)",
            min_value=0.0,
            value=float(commission_settings.get("bonus_ativacao", 50.0) or 0.0),
            step=10.0,
        )
        st.text_input(
            "Margem mínima da etapa de contrato",
            value=f"{CONTRACT_MARGIN_FLOOR_PERCENT:.0f}%",
            disabled=True,
        )
        if st.button("Salvar valor da premiação", type="primary"):
            if save_commission_settings({"bonus_ativacao": bonus_input}):
                st.success("Parâmetro salvo.")
                st.rerun()

history = umdb.get_billing_history(limit=20000)
contracts = get_contracts()
legacy_sellers = get_legacy_seller_mappings()

if not contracts:
    st.warning(
        "Nenhum contrato cadastrado. Cadastre o contrato e o vendedor em Contratos Clientes."
    )
    st.stop()

contract_rows: list[dict[str, Any]] = []
invoice_rows: list[dict[str, Any]] = []
client_rows: list[dict[str, Any]] = []

missing_seller: list[str] = []

for document_id, contract in contracts.items():
    client = str(contract.get("cliente", document_id) or document_id).strip()
    seller = str(contract.get("vendedor", "") or "").strip()
    if not seller:
        seller = legacy_sellers.get(client, "")
    if not seller:
        missing_seller.append(client)
        continue

    contract_months = int(contract.get("prazo_contrato_meses", 12) or 12)
    plan = (
        contract.get("plano_preco_simulador")
        or select_plan_name(pricing, contract_months)
    )
    if not plan:
        continue

    first_billings = first_three_billings(
        history,
        client,
        str(contract.get("ultima_atualizacao_termo") or ""),
    )
    first_items = billing_items(first_billings[0]) if first_billings else []
    fallback_mix = item_mix_from_billing_items(first_items, pricing)

    product_prices, product_quantities = contract_product_values(
        contract, pricing
    )

    stored_margin = contract.get("margem_contrato_percentual")
    stored_costs_complete = contract.get("custos_completos")
    if stored_margin is not None:
        try:
            margin_percent = float(stored_margin)
        except (TypeError, ValueError):
            margin_percent = None
        costs_complete = (
            bool(stored_costs_complete)
            if stored_costs_complete is not None
            else margin_percent is not None
        )
        used_mix = {
            product: quantity
            for product, quantity in product_quantities.items()
            if int(quantity or 0) > 0
        } or fallback_mix
    else:
        margin_result = calculate_contract_margin(
            pricing,
            contract_months,
            product_prices,
            product_quantities,
            fallback_mix,
        )
        margin_percent = margin_result["margin_percent"]
        costs_complete = bool(margin_result["costs_complete"])
        used_mix = margin_result["used_mix"]

    eligible_contract = (
        costs_complete
        and margin_percent is not None
        and margin_percent >= CONTRACT_MARGIN_FLOOR_PERCENT
    )

    contracted_quantity = sum(
        max(0, int(value or 0))
        for value in product_quantities.values()
    )
    if contracted_quantity <= 0:
        contracted_quantity = sum(
            max(0, int(value or 0))
            for value in fallback_mix.values()
        )
    if contracted_quantity <= 0 and first_billings:
        first_record = first_billings[0]
        contracted_quantity = int(
            first_record.get("terminais_cheio", 0) or 0
        ) + int(first_record.get("terminais_proporcional", 0) or 0)

    contract_prize = (
        contracted_quantity * float(bonus_input)
        if eligible_contract
        else 0.0
    )

    contract_rows.append(
        {
            "Vendedor": seller,
            "Cliente": client,
            "Plano": plan,
            "Quantidade contratada": contracted_quantity,
            "Margem contrato (%)": margin_percent,
            "Custos completos": "Sim" if costs_complete else "Não",
            "Elegível etapa contrato": "Sim" if eligible_contract else "Não",
            "Premiação contrato (R$)": contract_prize,
        }
    )

    invoice_commission_total = 0.0

    for billing_index, record in enumerate(first_billings, start=1):
        period = parse_period_key(record) or str(
            record.get("periodo_relatorio") or ""
        )
        details = billing_items(record)
        month_commission = 0.0

        if details:
            for item in details:
                category = _text(
                    item, "Categoria", "categoria"
                ).strip().lower()
                if category == "suspenso":
                    continue

                item_type = _text(
                    item,
                    "Tipo",
                    "tipo",
                    "Modelo",
                    "modelo",
                    default="",
                )
                product = resolve_product_name(item_type, pricing)
                billed = _float(
                    item,
                    "Valor a Faturar",
                    "valor_faturado",
                    "valor_a_faturar",
                    default=0.0,
                )
                contract_unit = _float(
                    item,
                    "Valor Unitario",
                    "Valor Unitário",
                    "valor_unitario",
                    default=0.0,
                )

                if product:
                    if contract_unit <= 0:
                        contract_unit = float(
                            product_prices.get(product, 0.0) or 0.0
                        )
                    base_price = contract_reference_price(
                        contract,
                        pricing,
                        plan,
                        product,
                    )
                else:
                    base_price = 0.0

                if contract_unit <= 0:
                    contract_unit = billed

                percent = get_tier_percent(contract_unit, base_price)
                commission = billed * percent
                month_commission += commission

                invoice_rows.append(
                    {
                        "Vendedor": seller,
                        "Cliente": client,
                        "Fatura": f"M{billing_index}",
                        "Período": period,
                        "Terminal": _text(
                            item,
                            "Terminal",
                            "terminal",
                            "Nº Equipamento",
                            "equipamento",
                            default="N/A",
                        ),
                        "Tipo origem": item_type,
                        "Produto Simulador": product or "Não mapeado",
                        "Valor unitário contrato (R$)": contract_unit,
                        "Preço-base Simulador (R$)": base_price,
                        "Valor faturado (R$)": billed,
                        "Faixa comissão (%)": percent * 100.0,
                        "Comissão fatura (R$)": commission,
                    }
                )
        else:
            # Compatibilidade com snapshots antigos sem item a item.
            billed_total = float(record.get("valor_total", 0.0) or 0.0)
            percent = 0.02
            month_commission = billed_total * percent
            invoice_rows.append(
                {
                    "Vendedor": seller,
                    "Cliente": client,
                    "Fatura": f"M{billing_index}",
                    "Período": period,
                    "Terminal": "RESUMO LEGADO",
                    "Tipo origem": "-",
                    "Produto Simulador": "-",
                    "Valor unitário contrato (R$)": 0.0,
                    "Preço-base Simulador (R$)": 0.0,
                    "Valor faturado (R$)": billed_total,
                    "Faixa comissão (%)": percent * 100.0,
                    "Comissão fatura (R$)": month_commission,
                }
            )

        invoice_commission_total += month_commission

    client_rows.append(
        {
            "Vendedor": seller,
            "Cliente": client,
            "Margem contrato (%)": margin_percent,
            "Elegível contrato": "Sim" if eligible_contract else "Não",
            "Premiação contrato (R$)": contract_prize,
            "Qtd. faturas apuradas": len(first_billings),
            "Comissão 3 primeiras faturas (R$)": invoice_commission_total,
            "Total premiação (R$)": contract_prize + invoice_commission_total,
        }
    )

if missing_seller:
    st.warning(
        f"{len(missing_seller)} contrato(s) estão sem vendedor e ficaram fora da apuração: "
        + ", ".join(sorted(missing_seller)[:15])
        + ("..." if len(missing_seller) > 15 else "")
    )

if not client_rows:
    st.info(
        "Nenhum contrato com vendedor possui dados suficientes para apuração."
    )
    st.stop()

df_clients = pd.DataFrame(client_rows)
df_contracts = pd.DataFrame(contract_rows)
df_invoices = pd.DataFrame(invoice_rows)

st.markdown("---")
filter_1, filter_2 = st.columns(2)
seller_options = ["Todos"] + sorted(df_clients["Vendedor"].dropna().unique())
selected_seller = filter_1.selectbox("Vendedor", seller_options)

client_options = ["Todos"] + sorted(df_clients["Cliente"].dropna().unique())
selected_client = filter_2.selectbox("Cliente", client_options)

mask_clients = pd.Series(True, index=df_clients.index)
if selected_seller != "Todos":
    mask_clients &= df_clients["Vendedor"].eq(selected_seller)
if selected_client != "Todos":
    mask_clients &= df_clients["Cliente"].eq(selected_client)
filtered_clients = df_clients[mask_clients].copy()

selected_pairs = set(
    zip(filtered_clients["Vendedor"], filtered_clients["Cliente"])
)
filtered_contracts = df_contracts[
    [
        (seller, client) in selected_pairs
        for seller, client in zip(
            df_contracts["Vendedor"], df_contracts["Cliente"]
        )
    ]
].copy()

if not df_invoices.empty:
    filtered_invoices = df_invoices[
        [
            (seller, client) in selected_pairs
            for seller, client in zip(
                df_invoices["Vendedor"], df_invoices["Cliente"]
            )
        ]
    ].copy()
else:
    filtered_invoices = df_invoices.copy()

total_contract = float(
    filtered_clients["Premiação contrato (R$)"].sum()
)
total_invoices = float(
    filtered_clients["Comissão 3 primeiras faturas (R$)"].sum()
)
total_pay = float(filtered_clients["Total premiação (R$)"].sum())

metric_1, metric_2, metric_3, metric_4 = st.columns(4)
metric_1.metric("Premiação contratos", f"R$ {total_contract:,.2f}")
metric_2.metric("Comissão 3 primeiras faturas", f"R$ {total_invoices:,.2f}")
metric_3.metric("Total a pagar", f"R$ {total_pay:,.2f}")
metric_4.metric(
    "Contratos elegíveis",
    int(filtered_clients["Elegível contrato"].eq("Sim").sum()),
)

st.markdown("### Resumo por vendedor")
grouped = (
    filtered_clients.groupby("Vendedor", as_index=False)
    .agg(
        Clientes=("Cliente", "count"),
        Premiação_Contrato=("Premiação contrato (R$)", "sum"),
        Comissão_Faturas=("Comissão 3 primeiras faturas (R$)", "sum"),
        Total=("Total premiação (R$)", "sum"),
    )
    .rename(
        columns={
            "Premiação_Contrato": "Premiação contrato (R$)",
            "Comissão_Faturas": "Comissão faturas M1-M3 (R$)",
            "Total": "Total a pagar (R$)",
        }
    )
)
st.dataframe(
    grouped,
    hide_index=True,
    use_container_width=True,
    column_config={
        "Premiação contrato (R$)": st.column_config.NumberColumn(
            format="R$ %.2f"
        ),
        "Comissão faturas M1-M3 (R$)": st.column_config.NumberColumn(
            format="R$ %.2f"
        ),
        "Total a pagar (R$)": st.column_config.NumberColumn(
            format="R$ %.2f"
        ),
    },
)

tab_contract, tab_clients, tab_invoices = st.tabs(
    ["Etapa 1 — Contrato", "Consolidado por cliente", "Etapa 2 — Faturas M1-M3"]
)

with tab_contract:
    st.dataframe(
        filtered_contracts,
        hide_index=True,
        use_container_width=True,
        column_config={
            "Margem contrato (%)": st.column_config.NumberColumn(
                format="%.2f%%"
            ),
            "Premiação contrato (R$)": st.column_config.NumberColumn(
                format="R$ %.2f"
            ),
        },
    )

with tab_clients:
    st.dataframe(
        filtered_clients,
        hide_index=True,
        use_container_width=True,
        column_config={
            "Margem contrato (%)": st.column_config.NumberColumn(
                format="%.2f%%"
            ),
            "Premiação contrato (R$)": st.column_config.NumberColumn(
                format="R$ %.2f"
            ),
            "Comissão 3 primeiras faturas (R$)": (
                st.column_config.NumberColumn(format="R$ %.2f")
            ),
            "Total premiação (R$)": st.column_config.NumberColumn(
                format="R$ %.2f"
            ),
        },
    )

with tab_invoices:
    if filtered_invoices.empty:
        st.info("Não existem faturas detalhadas para os filtros selecionados.")
    else:
        st.dataframe(
            filtered_invoices,
            hide_index=True,
            use_container_width=True,
            column_config={
                "Valor unitário contrato (R$)": (
                    st.column_config.NumberColumn(format="R$ %.2f")
                ),
                "Preço-base Simulador (R$)": (
                    st.column_config.NumberColumn(format="R$ %.2f")
                ),
                "Valor faturado (R$)": (
                    st.column_config.NumberColumn(format="R$ %.2f")
                ),
                "Faixa comissão (%)": st.column_config.NumberColumn(
                    format="%.1f%%"
                ),
                "Comissão fatura (R$)": (
                    st.column_config.NumberColumn(format="R$ %.2f")
                ),
            },
        )


def to_excel() -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        grouped.to_excel(writer, index=False, sheet_name="Resumo Vendedor")
        filtered_clients.to_excel(
            writer, index=False, sheet_name="Por Cliente"
        )
        filtered_contracts.to_excel(
            writer, index=False, sheet_name="Etapa Contrato"
        )
        filtered_invoices.to_excel(
            writer, index=False, sheet_name="Faturas M1-M3"
        )
    return output.getvalue()


st.download_button(
    "Baixar apuração completa em Excel",
    data=to_excel(),
    file_name="premiacao_vendedores_verdio.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True,
)
