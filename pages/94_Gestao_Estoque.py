import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pandas as pd
import streamlit as st

from app_core.inventory_import import (
    SUPPORTED_TYPES,
    apply_model_type_mapping,
    build_model_type_mapping,
    parse_inventory_report,
)
from app_core.ui import apply_branding, render_sidebar
import user_management_db as umdb

st.set_page_config(
    layout="wide",
    page_title="Gestão de Estoque e Preços",
    page_icon="📦",
)
apply_branding()

if "user_info" not in st.session_state:
    st.error("Acesso negado. Faça login para visualizar esta página.")
    st.stop()

if st.session_state.get("role", "Usuário").lower() != "admin":
    st.error("Esta página é restrita aos administradores.")
    st.stop()

render_sidebar()

st.title("Gestão de Estoque e Preços")
st.markdown(
    "Atualize o inventário de rastreadores a partir da exportação do sistema atual "
    "e gerencie preços e classificação dos equipamentos."
)

with st.expander(
    "Gerenciar Tabelas de Preços por Tipo de Equipamento",
    expanded=True,
):
    st.info(
        "Defina até três faixas de preço para cada tipo de equipamento."
    )

    pricing_config = umdb.get_pricing_config()
    tipo_equip_data = pricing_config.get("TIPO_EQUIPAMENTO", {})

    table_data = []
    for tipo, precos in tipo_equip_data.items():
        if isinstance(precos, (int, float)):
            value = float(precos)
            precos = {
                "price1": value,
                "price2": value,
                "price3": value,
            }
        elif not isinstance(precos, dict):
            precos = {}

        table_data.append(
            {
                "Tipo Equipamento": tipo,
                "Preço 1 (R$)": precos.get("price1", 0.0),
                "Preço 2 (R$)": precos.get("price2", 0.0),
                "Preço 3 (R$)": precos.get("price3", 0.0),
            }
        )

    df_prices = pd.DataFrame(table_data)

    edited_df = st.data_editor(
        df_prices,
        column_config={
            "Tipo Equipamento": st.column_config.TextColumn(
                "Tipo",
                disabled=True,
            ),
            "Preço 1 (R$)": st.column_config.NumberColumn(
                "Preço 1 (Padrão)",
                format="R$ %.2f",
                min_value=0.0,
            ),
            "Preço 2 (R$)": st.column_config.NumberColumn(
                "Preço 2",
                format="R$ %.2f",
                min_value=0.0,
            ),
            "Preço 3 (R$)": st.column_config.NumberColumn(
                "Preço 3",
                format="R$ %.2f",
                min_value=0.0,
            ),
        },
        use_container_width=True,
        hide_index=True,
        key="price_editor",
    )

    if st.button("Salvar Tabela de Preços", type="primary"):
        new_pricing_config = {}

        for _, row in edited_df.iterrows():
            tipo = row["Tipo Equipamento"]
            new_pricing_config[tipo] = {
                "price1": float(row["Preço 1 (R$)"]),
                "price2": float(row["Preço 2 (R$)"]),
                "price3": float(row["Preço 3 (R$)"]),
            }

        if umdb.update_pricing_config(
            {"TIPO_EQUIPAMENTO": new_pricing_config}
        ):
            st.success("Tabelas de preços atualizadas.")
            st.rerun()
        else:
            st.error("Não foi possível salvar os preços.")

st.markdown("---")

with st.expander("Atualizar Estoque via Planilha", expanded=True):
    st.subheader("Importar exportação do estoque")

    st.caption(
        "Compatível com a exportação do sistema atual contendo campos como "
        "Modelo, Gateway, Equipamento, P/ Entrada, Status, Tipo Equipamento "
        "e Situação. Também aceita XLSX e CSV."
    )

    uploaded_file = st.file_uploader(
        "Selecione a planilha de estoque",
        type=["xls", "xlsx", "csv"],
        key="inventory_file",
    )

    if uploaded_file:
        try:
            df_stock, metadata = parse_inventory_report(
                uploaded_file.getvalue(),
                uploaded_file.name,
            )

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Registros válidos", metadata["rows_valid"])
            c2.metric(
                "Duplicados removidos",
                metadata["duplicates_removed"],
            )
            c3.metric(
                "Modelos",
                int(df_stock["Modelo"].nunique()),
            )
            c4.metric(
                "Cabeçalho encontrado",
                f"Linha {metadata['header_row']}",
            )

            st.markdown("#### 1. Classificação dos modelos")
            st.caption(
                "O campo 'Tipo Equipamento' da exportação original é preservado "
                "como informação de origem. Para faturamento, cada modelo precisa "
                "ser classificado como GPRS, SATELITE, CAMERA ou RADIO."
            )

            existing_model_types = umdb.get_unique_models_and_types()
            mapping = build_model_type_mapping(
                df_stock,
                existing_model_types,
            )

            edited_mapping = st.data_editor(
                mapping,
                hide_index=True,
                use_container_width=True,
                key=f"inventory_model_mapping_{uploaded_file.name}",
                column_config={
                    "Modelo": st.column_config.TextColumn(
                        "Modelo",
                        disabled=True,
                    ),
                    "Qtd Equipamentos": st.column_config.NumberColumn(
                        "Qtd.",
                        disabled=True,
                    ),
                    "Tipo origem": st.column_config.TextColumn(
                        "Tipo no sistema atual",
                        disabled=True,
                    ),
                    "Tipo": st.column_config.SelectboxColumn(
                        "Classificação para faturamento",
                        options=[""] + SUPPORTED_TYPES,
                        required=False,
                    ),
                    "Origem da sugestão": st.column_config.TextColumn(
                        "Origem da sugestão",
                        disabled=True,
                    ),
                },
            )

            classified_stock = apply_model_type_mapping(
                df_stock,
                edited_mapping,
            )

            missing_models = sorted(
                classified_stock.loc[
                    classified_stock["Tipo"].eq(""),
                    "Modelo",
                ]
                .dropna()
                .unique()
                .tolist()
            )

            if missing_models:
                st.warning(
                    f"Ainda existem {len(missing_models)} modelo(s) sem tipo. "
                    "Classifique todos antes de salvar para evitar faturamento zerado."
                )

            st.markdown("#### 2. Pré-visualização do estoque")
            preview_columns = [
                column
                for column in [
                    "Nº Equipamento",
                    "Modelo",
                    "Tipo",
                    "Gateway",
                    "P/ Entrada",
                    "Status",
                    "Tipo Equipamento Origem",
                    "Situação",
                ]
                if column in classified_stock.columns
            ]

            st.dataframe(
                classified_stock[preview_columns],
                use_container_width=True,
                hide_index=True,
                height=420,
            )

            type_summary = (
                classified_stock["Tipo"]
                .replace("", "SEM CLASSIFICAÇÃO")
                .value_counts()
                .rename_axis("Tipo")
                .reset_index(name="Quantidade")
            )

            st.dataframe(
                type_summary,
                use_container_width=True,
                hide_index=True,
            )

            save_inventory = st.button(
                "Processar e Salvar Estoque no MongoDB",
                type="primary",
                disabled=bool(missing_models),
            )

            if save_inventory:
                with st.spinner("Atualizando estoque no MongoDB..."):
                    count = umdb.update_tracker_inventory(
                        classified_stock,
                        source_file=uploaded_file.name,
                    )

                if count is not None:
                    st.success(
                        f"{count} rastreador(es) foram salvos/atualizados."
                    )
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error("Não foi possível atualizar o estoque.")

        except Exception as exc:
            st.error(f"Não foi possível processar o arquivo: {exc}")

st.markdown("---")

st.subheader("Editar Tipo por Modelo de Rastreador")

model_types = umdb.get_unique_models_and_types()
tipos_disponiveis = SUPPORTED_TYPES.copy()

if not model_types:
    st.info(
        "Nenhum modelo foi encontrado. Faça o upload de uma planilha de estoque."
    )
else:
    st.info(
        "A alteração é aplicada a todos os rastreadores do mesmo modelo."
    )

    updates_to_perform = {}
    cols = st.columns(3)
    col_index = 0

    for model, current_type in sorted(model_types.items()):
        current_type = str(current_type or "").upper().strip()

        options = tipos_disponiveis.copy()
        if current_type and current_type not in options:
            options.append(current_type)

        default_index = (
            options.index(current_type)
            if current_type in options
            else 0
        )

        with cols[col_index]:
            new_type = st.selectbox(
                f"Modelo: {model}",
                options=options,
                index=default_index,
                key=f"model_{model}",
            )

            if new_type != current_type:
                updates_to_perform[model] = new_type

        col_index = (col_index + 1) % 3

    if st.button("Salvar Alterações de Tipo", type="primary"):
        if not updates_to_perform:
            st.warning("Nenhuma alteração foi realizada.")
        else:
            with st.spinner("Aplicando alterações em massa..."):
                success, failed = umdb.update_type_for_models(
                    updates_to_perform
                )

            if success:
                st.success(
                    f"{success} modelo(s) foram atualizados."
                )
                st.cache_data.clear()
                st.rerun()

            if failed:
                st.error(
                    "Falha nos modelos: " + ", ".join(failed)
                )

st.markdown("---")

st.subheader("Estoque Atual de Rastreadores")

with st.spinner("Carregando estoque do MongoDB..."):
    stock_data = umdb.get_tracker_inventory()

if stock_data:
    df_stock_db = pd.DataFrame(stock_data)

    display_columns = [
        column
        for column in [
            "Nº Equipamento",
            "Modelo",
            "Tipo",
            "Gateway",
            "P/ Entrada",
            "Status",
            "Tipo Equipamento Origem",
            "Situação",
            "source_file",
            "updated_at",
        ]
        if column in df_stock_db.columns
    ]

    if display_columns:
        df_stock_db = df_stock_db[display_columns]

    st.dataframe(
        df_stock_db,
        use_container_width=True,
        hide_index=True,
        height=520,
    )
else:
    st.info("Nenhum rastreador encontrado no banco.")
