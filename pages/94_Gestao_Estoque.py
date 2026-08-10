# pages/94_Gestao_Estoque.py
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app_core.ui import apply_branding, render_sidebar

import streamlit as st
import pandas as pd
import user_management_db as umdb

st.set_page_config(layout="wide", page_title="Gestão de Estoque e Preços", page_icon="📦")
apply_branding()

# --- VERIFICAÇÃO DE LOGIN E PERMISSÃO ---
if "user_info" not in st.session_state:
    st.error("🔒 Acesso Negado! Por favor, faça login para visualizar esta página.")
    st.stop()

if st.session_state.get("role", "Usuário").lower() != "admin":
    st.error("🚫 Você não tem permissão para acessar esta página. Apenas Administradores.")
    st.stop()

# --- BARRA LATERAL PADRONIZADA ---
render_sidebar()

# --- TÍTULO DA PÁGINA ---
st.title("📦 Gestão de Estoque e Preços")
st.markdown("Atualize o estoque de rastreadores e gerencie os preços e tipos de equipamentos.")

# --- SEÇÃO DE PREÇOS (MELHORIA: 3 PREÇOS POR EQUIPAMENTO) ---
with st.expander("Gerenciar Tabelas de Preços por Tipo de Equipamento", expanded=True):
    st.info("Agora você pode definir até 3 faixas de preço para cada tipo de equipamento.")
    
    pricing_config = umdb.get_pricing_config()
    tipo_equip_data = pricing_config.get("TIPO_EQUIPAMENTO", {})

    # Preparar dados para o Data Editor
    table_data = []
    for tipo, precos in tipo_equip_data.items():
        # --- CORREÇÃO DE BUG (Compatibilidade) ---
        # Se vier um número solto (cache/banco antigo), converte para dict na hora
        if isinstance(precos, (int, float)):
            val = float(precos)
            precos = {"price1": val, "price2": val, "price3": val}
        # Se por algum motivo não for dict, cria um vazio para não quebrar o .get
        elif not isinstance(precos, dict):
            precos = {}
        # -----------------------------------------

        row = {
            "Tipo Equipamento": tipo,
            "Preço 1 (R$)": precos.get("price1", 0.0),
            "Preço 2 (R$)": precos.get("price2", 0.0),
            "Preço 3 (R$)": precos.get("price3", 0.0),
        }
        table_data.append(row)
    
    df_prices = pd.DataFrame(table_data)
    
    # Editor de Dados Editável
    edited_df = st.data_editor(
        df_prices,
        column_config={
            "Tipo Equipamento": st.column_config.TextColumn("Tipo", disabled=True),
            "Preço 1 (R$)": st.column_config.NumberColumn("Preço 1 (Padrão)", format="R$ %.2f", min_value=0.0),
            "Preço 2 (R$)": st.column_config.NumberColumn("Preço 2", format="R$ %.2f", min_value=0.0),
            "Preço 3 (R$)": st.column_config.NumberColumn("Preço 3", format="R$ %.2f", min_value=0.0),
        },
        use_container_width=True,
        hide_index=True,
        key="price_editor"
    )

    if st.button("💾 Salvar Tabela de Preços", type="primary"):
        # Converter de volta para o formato do dicionário do Firestore
        new_pricing_config = {}
        for index, row in edited_df.iterrows():
            tipo = row["Tipo Equipamento"]
            new_pricing_config[tipo] = {
                "price1": float(row["Preço 1 (R$)"]),
                "price2": float(row["Preço 2 (R$)"]),
                "price3": float(row["Preço 3 (R$)"]),
            }
        
        if umdb.update_pricing_config({"TIPO_EQUIPAMENTO": new_pricing_config}):
            st.success("Tabelas de preços atualizadas com sucesso!")
            st.rerun()
        else:
            st.error("Ocorreu um erro ao salvar os preços.")

st.markdown("---")

# --- SEÇÃO DE UPLOAD DE ESTOQUE ---
with st.expander("Atualizar Estoque via Planilha", expanded=False):
    st.subheader("Carregar Nova Planilha de Estoque")
    uploaded_file = st.file_uploader("Selecione a planilha de estoque (.xlsx)", type=['xlsx'])

    if uploaded_file:
        try:
            df_stock = pd.read_excel(uploaded_file, header=11, dtype={'Nº Equipamento': str, 'Nº Série': str})
            
            if 'Nº Equipamento' not in df_stock.columns and 'Nº Série' in df_stock.columns:
                df_stock = df_stock.rename(columns={'Nº Série': 'Nº Equipamento'})

            required_cols = ['Nº Equipamento', 'Modelo', 'Tipo Equipamento']
            if not all(col in df_stock.columns for col in required_cols):
                st.error(f"A planilha precisa conter as colunas: {', '.join(required_cols)}. Verifique o cabeçalho na linha 12.")
            else:
                df_to_upload = df_stock[required_cols].copy()
                df_to_upload.dropna(subset=['Nº Equipamento'], inplace=True)
                df_to_upload = df_to_upload.rename(columns={'Tipo Equipamento': 'Tipo'})
                
                st.write("Pré-visualização dos dados a serem importados:")
                st.dataframe(df_to_upload.head())

                if st.button("Processar e Salvar no Banco de Dados"):
                    with st.spinner("Atualizando estoque... Isso pode levar alguns minutos."):
                        count = umdb.update_tracker_inventory(df_to_upload)
                        if count is not None:
                            st.success(f"{count} registros de rastreadores foram salvos/atualizados com sucesso!")
                            st.cache_data.clear()
                            st.rerun()
                        else:
                            st.error("Ocorreu um erro ao atualizar o estoque.")

        except Exception as e:
            st.error(f"Ocorreu um erro ao processar o arquivo: {e}")

st.markdown("---")

# --- NOVA SEÇÃO PARA EDITAR TIPO POR MODELO ---
st.subheader("Editar Tipo por Modelo de Rastreador")
model_types = umdb.get_unique_models_and_types()
tipos_disponiveis = ["GPRS", "SATELITE", "CAMERA", "RADIO"]

if not model_types:
    st.info("Nenhum modelo de rastreador encontrado no estoque. Faça o upload de uma planilha primeiro.")
else:
    st.info("Ajuste o tipo de equipamento para cada modelo. A alteração será aplicada a todos os rastreadores do mesmo modelo.")
    
    updates_to_perform = {}
    cols = st.columns(3)
    col_index = 0

    for model, current_type in sorted(model_types.items()):
        with cols[col_index]:
            try:
                # Garante que o tipo atual esteja na lista, mesmo que seja inválido
                if current_type not in tipos_disponiveis:
                    tipos_disponiveis.append(current_type)
                
                default_index = tipos_disponiveis.index(current_type)
            except ValueError:
                default_index = 0 # Padrão para o primeiro item se o tipo atual não for encontrado

            new_type = st.selectbox(f"Modelo: **{model}**", options=tipos_disponiveis, index=default_index, key=f"model_{model}")
            
            if new_type != current_type:
                updates_to_perform[model] = new_type
        
        col_index = (col_index + 1) % 3

    if st.button("Salvar Alterações de Tipo", type="primary"):
        if not updates_to_perform:
            st.warning("Nenhuma alteração de tipo foi feita.")
        else:
            with st.spinner("Aplicando alterações em massa..."):
                success, failed = umdb.update_type_for_models(updates_to_perform)
                if success:
                    st.success(f"Tipos de {success} modelo(s) foram atualizados com sucesso!")
                    st.cache_data.clear()
                    st.rerun()
                if failed:
                    st.error(f"Falha ao atualizar os seguintes modelos: {', '.join(failed)}")


st.markdown("---")

# --- SEÇÃO DE VISUALIZAÇÃO DO ESTOQUE ---
st.subheader("Estoque Atual de Rastreadores")
with st.spinner("Carregando estoque do banco de dados..."):
    stock_data = umdb.get_tracker_inventory()
    if stock_data:
        df_stock_db = pd.DataFrame(stock_data)
        st.dataframe(df_stock_db, use_container_width=True)
    else:
        st.info("Nenhum rastreador encontrado no banco de dados.")
