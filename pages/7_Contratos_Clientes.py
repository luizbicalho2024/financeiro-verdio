from __future__ import annotations

import calendar
import os
import sys
from datetime import date, datetime

import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app_core.simulator_pricing import (
    CONTRACT_MARGIN_FLOOR_PERCENT,
    all_products,
    billing_type_for_product,
    calculate_contract_margin,
    contract_product_values,
    get_simulator_db_name,
    get_simulator_pricing,
    legacy_contract_prices,
    product_price_cost,
    select_plan_name,
    sorted_plan_names,
)
from app_core.ui import apply_branding, render_sidebar
from mongo_config import db

st.set_page_config(
    layout="wide",
    page_title="Contratos e Preços por Cliente",
    page_icon="📝",
)
apply_branding()

if "user_info" not in st.session_state:
    st.error("Acesso negado. Faça login para visualizar esta página.")
    st.stop()

if st.session_state.get("role", "Usuário").lower() != "admin":
    st.error("Esta página é restrita aos administradores.")
    st.stop()

render_sidebar()


def add_months(source_date: date, months: int) -> date:
    month = source_date.month - 1 + months
    year = source_date.year + month // 12
    month = month % 12 + 1
    day = min(source_date.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def get_contracts() -> dict[str, dict]:
    try:
        return {
            document.id: document.to_dict()
            for document in db.collection("client_contracts").stream()
        }
    except Exception as exc:
        st.error(f"Erro ao buscar contratos: {exc}")
        return {}


def save_contract(client_id: str, data: dict) -> bool:
    try:
        db.collection("client_contracts").document(client_id).set(data)
        return True
    except Exception as exc:
        st.error(f"Erro ao salvar contrato: {exc}")
        return False


def delete_contract(client_id: str) -> bool:
    try:
        db.collection("client_contracts").document(client_id).delete()
        return True
    except Exception as exc:
        st.error(f"Erro ao excluir contrato: {exc}")
        return False


def _parse_date(value: str | None, fallback: date | None = None) -> date:
    fallback = fallback or datetime.today().date()
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except Exception:
        return fallback


def _plan_months(plan_name: str) -> int:
    digits = "".join(char for char in str(plan_name) if char.isdigit())
    return max(1, int(digits or 12))


st.title("COMERCIAL - Gestão de Contratos Verdio")
st.markdown(
    "O contrato agora concentra o **vendedor**, o **mix contratado**, os preços negociados "
    "e a margem usada na política de premiação."
)

try:
    pricing = get_simulator_pricing()
except Exception as exc:
    st.error(
        "Não foi possível carregar a fonte oficial de preços do Simulador. "
        f"Detalhe: {exc}"
    )
    st.stop()

plans = sorted_plan_names(pricing)
products = all_products(pricing)
if not plans or not products:
    st.error("O Simulador não possui planos/produtos PJ configurados.")
    st.stop()

st.caption(
    f"Fonte oficial de preços e custos: **{get_simulator_db_name()}.pricing_config / global_prices**. "
    "A página não mantém uma tabela paralela."
)

contracts = get_contracts()

tab_list, tab_edit = st.tabs(
    ["Lista de Contratos Vigentes", "Novo / Editar Contrato"]
)

with tab_list:
    st.subheader("Painel de Contratos")
    if not contracts:
        st.info("Nenhum contrato cadastrado na base de dados.")
    else:
        rows = []
        today = datetime.today().date()

        for document_id, contract in contracts.items():
            expiration = _parse_date(contract.get("vencimento_contrato"))
            status = "Vigente" if expiration >= today else "Vencido"
            margin = contract.get("margem_contrato_percentual")
            costs_complete = bool(contract.get("custos_completos", margin is not None))
            eligible = (
                costs_complete
                and margin is not None
                and float(margin) >= CONTRACT_MARGIN_FLOOR_PERCENT
            )

            product_prices, product_quantities = contract_product_values(
                contract, pricing
            )
            configured = [
                f"{product}: {product_quantities.get(product, 0)} un. × R$ {price:.2f}"
                for product, price in product_prices.items()
                if price > 0 and product_quantities.get(product, 0) > 0
            ]

            rows.append(
                {
                    "Cliente": contract.get("cliente", document_id),
                    "Vendedor": contract.get("vendedor", ""),
                    "Assinatura/Termo": _parse_date(
                        contract.get("ultima_atualizacao_termo")
                    ).strftime("%d/%m/%Y"),
                    "Prazo (meses)": int(
                        contract.get("prazo_contrato_meses", 12) or 12
                    ),
                    "Plano de referência": contract.get(
                        "plano_preco_simulador", ""
                    ),
                    "Vencimento": expiration.strftime("%d/%m/%Y"),
                    "Status": status,
                    "Margem (%)": float(margin) if margin is not None else None,
                    "Premiação contrato": (
                        "Elegível"
                        if eligible
                        else "Não elegível / margem pendente"
                    ),
                    "Mix contratado": " | ".join(configured) or "Não informado",
                }
            )

        contracts_df = pd.DataFrame(rows)
        contracts_df["Vencimento_Date"] = pd.to_datetime(
            contracts_df["Vencimento"], format="%d/%m/%Y", errors="coerce"
        )
        contracts_df = contracts_df.sort_values(
            by="Vencimento_Date", na_position="last"
        ).drop(columns=["Vencimento_Date"])

        table_col, chart_col = st.columns([2.6, 1])
        with table_col:
            st.dataframe(
                contracts_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Margem (%)": st.column_config.NumberColumn(
                        format="%.2f%%"
                    )
                },
            )

        with chart_col:
            status_counts = (
                contracts_df["Status"]
                .value_counts()
                .rename_axis("Status")
                .reset_index(name="Quantidade")
            )
            fig = px.pie(
                status_counts,
                values="Quantidade",
                names="Status",
                title="Status geral",
                hole=0.4,
            )
            fig.update_traces(textposition="inside", textinfo="percent+label")
            fig.update_layout(
                showlegend=False,
                margin=dict(t=40, b=0, l=0, r=0),
            )
            st.plotly_chart(fig, use_container_width=True)

        st.markdown("---")
        st.subheader("Ações avançadas")
        selected_delete = st.selectbox(
            "Contrato para excluir",
            ["-- SELECIONE --"] + sorted(contracts.keys()),
        )
        if st.button("Excluir Contrato", type="primary"):
            if selected_delete == "-- SELECIONE --":
                st.warning("Selecione um contrato.")
            elif delete_contract(selected_delete):
                st.success("Contrato excluído.")
                st.rerun()

with tab_edit:
    st.subheader("Configuração do contrato")

    client_options = ["-- NOVO CLIENTE --"] + sorted(contracts.keys())
    selected_client = st.selectbox(
        "Selecione um cliente existente ou crie um novo:",
        client_options,
    )

    if selected_client == "-- NOVO CLIENTE --":
        client_name = st.text_input("Nome do novo cliente")
        current = {}
    else:
        client_name = selected_client
        st.text_input("Nome do cliente", value=client_name, disabled=True)
        current = contracts.get(selected_client, {})

    if client_name.strip():
        current_months = int(current.get("prazo_contrato_meses", 12) or 12)
        current_plan = (
            current.get("plano_preco_simulador")
            or select_plan_name(pricing, current_months)
            or plans[0]
        )
        if current_plan not in plans:
            current_plan = select_plan_name(pricing, current_months) or plans[0]

        selected_plan = st.selectbox(
            "Plano/prazo usado como referência do Simulador",
            plans,
            index=plans.index(current_plan),
            help=(
                "Os preços e custos de referência vêm diretamente do Simulador. "
                "O preço do contrato pode ser diferente; ele é o valor efetivamente negociado."
            ),
        )
        contract_months = _plan_months(selected_plan)

        current_prices, current_quantities = contract_product_values(
            current, pricing
        )
        pricing_rows = []
        for product in products:
            base_price, base_cost = product_price_cost(
                pricing, selected_plan, product
            )
            saved_price = float(current_prices.get(product, 0.0) or 0.0)
            pricing_rows.append(
                {
                    "Produto": product,
                    "Tipo faturamento": billing_type_for_product(product),
                    "Preço tabela (R$)": base_price,
                    "Custo referência (R$)": base_cost,
                    "Preço contrato (R$)": (
                        saved_price if saved_price > 0 else base_price
                    ),
                    "Quantidade": int(
                        current_quantities.get(product, 0) or 0
                    ),
                }
            )

        with st.form("contract_form"):
            st.markdown("### Responsável comercial e vigência")
            date_col, seller_col, expiration_col = st.columns([1, 1.4, 1])

            with date_col:
                signature_date = st.date_input(
                    "Data do termo/assinatura",
                    value=_parse_date(
                        current.get("ultima_atualizacao_termo")
                    ),
                    format="DD/MM/YYYY",
                )

            with seller_col:
                seller_name = st.text_input(
                    "Nome do vendedor",
                    value=str(current.get("vendedor", "") or ""),
                    placeholder="Ex.: João da Silva",
                    help=(
                        "Este campo passa a ser a fonte principal da página de comissão."
                    ),
                )

            expiration = add_months(signature_date, contract_months)
            with expiration_col:
                st.info(
                    f"**Vencimento**\n\n{expiration.strftime('%d/%m/%Y')}"
                )

            st.markdown("### Produtos, preços e quantidades contratadas")
            st.caption(
                "Informe a quantidade efetivamente contratada. A margem do contrato "
                "é ponderada pelo mix de produtos e usa o custo do plano selecionado."
            )

            editor = st.data_editor(
                pd.DataFrame(pricing_rows),
                hide_index=True,
                use_container_width=True,
                num_rows="fixed",
                column_config={
                    "Produto": st.column_config.TextColumn(disabled=True),
                    "Tipo faturamento": st.column_config.TextColumn(
                        disabled=True
                    ),
                    "Preço tabela (R$)": st.column_config.NumberColumn(
                        format="R$ %.2f", disabled=True
                    ),
                    "Custo referência (R$)": st.column_config.NumberColumn(
                        format="R$ %.2f", disabled=True
                    ),
                    "Preço contrato (R$)": st.column_config.NumberColumn(
                        min_value=0.0, format="R$ %.2f"
                    ),
                    "Quantidade": st.column_config.NumberColumn(
                        min_value=0,
                        step=1,
                        format="%d",
                    ),
                },
                key=f"contract_mix_{selected_client}_{selected_plan}",
            )

            submitted = st.form_submit_button(
                "Salvar contrato",
                type="primary",
                use_container_width=True,
            )

        if submitted:
            if not client_name.strip():
                st.error("O nome do cliente é obrigatório.")
            elif not seller_name.strip():
                st.error("Informe o vendedor responsável pelo contrato.")
            else:
                product_prices = {
                    str(row["Produto"]): float(
                        row["Preço contrato (R$)"] or 0.0
                    )
                    for _, row in editor.iterrows()
                }
                product_quantities = {
                    str(row["Produto"]): max(
                        0, int(row["Quantidade"] or 0)
                    )
                    for _, row in editor.iterrows()
                }

                active_products = [
                    product
                    for product, quantity in product_quantities.items()
                    if quantity > 0
                ]
                if not active_products:
                    st.error(
                        "Informe a quantidade de pelo menos um produto contratado."
                    )
                    st.stop()

                margin_result = calculate_contract_margin(
                    pricing,
                    contract_months,
                    product_prices,
                    product_quantities,
                )
                margin = margin_result["margin_percent"]
                costs_complete = bool(margin_result["costs_complete"])
                eligible = (
                    costs_complete
                    and margin is not None
                    and float(margin) >= CONTRACT_MARGIN_FLOOR_PERCENT
                )

                table_snapshot = {}
                cost_snapshot = {}
                for product in products:
                    base_price, base_cost = product_price_cost(
                        pricing, selected_plan, product
                    )
                    table_snapshot[product] = base_price
                    cost_snapshot[product] = base_cost

                payload = {
                    "cliente": client_name.strip(),
                    "vendedor": seller_name.strip(),
                    "ultima_atualizacao_termo": signature_date.strftime(
                        "%Y-%m-%d"
                    ),
                    "prazo_contrato_meses": contract_months,
                    "vencimento_contrato": expiration.strftime("%Y-%m-%d"),
                    "plano_preco_simulador": selected_plan,
                    "precos_produtos": product_prices,
                    "quantidades_produtos": product_quantities,
                    # Compatibilidade com o faturamento atual.
                    "precos_por_tipo": legacy_contract_prices(product_prices),
                    # Snapshot econômico: contratos antigos não mudam de margem
                    # quando a tabela do Simulador for reajustada no futuro.
                    "precos_tabela_produtos": table_snapshot,
                    "custos_produtos": cost_snapshot,
                    "margem_contrato_percentual": (
                        float(margin) if margin is not None else None
                    ),
                    "custos_completos": costs_complete,
                    "margem_minima_premiacao_percentual": (
                        CONTRACT_MARGIN_FLOOR_PERCENT
                    ),
                    "elegivel_premiacao_contrato": eligible,
                    "pricing_source": {
                        "database": get_simulator_db_name(),
                        "collection": "pricing_config",
                        "document": "global_prices",
                    },
                    "atualizado_em": datetime.now().strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                }

                if save_contract(client_name.strip(), payload):
                    if not costs_complete:
                        st.warning(
                            "Contrato salvo, mas existem custos zerados no Simulador. "
                            "A etapa de premiação do contrato ficará inelegível até a margem poder ser comprovada."
                        )
                    elif eligible:
                        st.success(
                            f"Contrato salvo. Margem calculada: {margin:.2f}% — "
                            "elegível para a etapa de premiação do contrato."
                        )
                    else:
                        st.warning(
                            f"Contrato salvo. Margem calculada: {margin:.2f}% — "
                            f"abaixo do piso de {CONTRACT_MARGIN_FLOOR_PERCENT:.0f}% e, portanto, "
                            "não elegível para a etapa de premiação do contrato."
                        )
                    st.rerun()
