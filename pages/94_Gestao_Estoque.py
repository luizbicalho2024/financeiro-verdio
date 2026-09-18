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
from app_core.simulator_pricing import (
    clear_simulator_pricing_cache,
    get_simulator_db_name,
    get_simulator_pricing,
    pricing_matrix,
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
    "e consulte preços sincronizados com o Simulador, além da classificação dos equipamentos."
)

with st.expander(
    "Preços e produtos sincronizados com o Simulador",
    expanded=True,
):
    st.info(
        "Esta seção é somente leitura. Produtos, preços, custos e instalação vêm "
        "diretamente da aba 'Preços e produtos' do Simulador de Telemetria."
    )

    try:
        simulator_pricing = get_simulator_pricing()
        price_rows = pricing_matrix(simulator_pricing)
        if not price_rows:
            st.warning("Nenhum produto PJ foi encontrado no Simulador.")
        else:
            df_prices = pd.DataFrame(price_rows)
            column_config = {}
            for column in df_prices.columns:
                if column.startswith("Preço ") or column.startswith("Custo ") or column.startswith("Instalação "):
                    column_config[column] = st.column_config.NumberColumn(
                        format="R$ %.2f"
                    )
                elif column.startswith("Margem "):
                    column_config[column] = st.column_config.NumberColumn(
                        format="%.2f%%"
                    )

            st.dataframe(
                df_prices,
                use_container_width=True,
                hide_index=True,
                column_config=column_config,
            )
            st.caption(
                "Fonte: "
                f"{get_simulator_db_name()}.pricing_config / global_prices. "
                "Para alterar qualquer valor, faça a edição no Simulador."
            )

        if st.button("Atualizar preços do Simulador agora"):
            clear_simulator_pricing_cache()
            st.cache_data.clear()
            st.rerun()
    except Exception as exc:
        st.error(
            "Não foi possível ler os preços do Simulador. "
            f"Detalhe: {exc}"
        )

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
