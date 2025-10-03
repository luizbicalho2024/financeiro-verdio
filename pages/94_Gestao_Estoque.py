# pages/4_Gestao_Estoque.py
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import streamlit as st
import pandas as pd
import user_management_db as umdb

st.set_page_config(layout="wide", page_title="Gestão de Estoque e Preços", page_icon="📦")

# --- VERIFICAÇÃO DE LOGIN E PERMISSÃO ---
if "user_info" not in st.session_state:
    st.error("🔒 Acesso Negado! Por favor, faça login para visualizar esta página.")
    st.stop()

if st.session_state.get("role", "Usuário").lower() != "admin":
    st.error("🚫 Você não tem permissão para acessar esta página. Apenas Administradores.")
    st.stop()

# --- BARRA LATERAL PADRONIZADA ---
st.sidebar.image("imgs/v-c.png", width=120)
st.sidebar.title(f"Olá, {st.session_state.get('name', 'N/A')}! 👋")
st.sidebar.markdown("---")
if st.sidebar.button("Logout"):
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.switch_page("1_Home.py")

# --- TÍTULO DA PÁGINA ---
st.title("📦 Gestão de Estoque e Preços")
st.markdown("Atualize o estoque de rastreadores e gerencie os preços de faturamento por tipo de equipamento.")

# --- SEÇÃO DE PREÇOS ---
with st.expander("Gerenciar Preços por Tipo de Equipamento", expanded=True):
    pricing_config = umdb.get_pricing_config()
    
    # Garante que a estrutura de preços exista
    if "TIPO_EQUIPAMENTO" not in pricing_config:
        pricing_config["TIPO_EQUIPAMENTO"] = {}

    col1, col2, col3, col4 = st.columns(4)
    prices = {
        "GPRS": col1.number_input("Preço GPRS", min_value=0.0, value=float(pricing_config["TIPO_EQUIPAMENTO"].get("GPRS", 59.90)), format="%.2f"),
        "SATELITE": col2.number_input("Preço SATÉLITE", min_value=0.0, value=float(pricing_config["TIPO_EQUIPAMENTO"].get("SATELITE", 159.90)), format="%.2f"),
        "CAMERA": col3.number_input("Preço CÂMERA", min_value=0.0, value=float(pricing_config["TIPO_EQUIPAMENTO"].get("CAMERA", 0.0)), format="%.2f"),
        "RADIO": col4.number_input("Preço RÁDIO", min_value=0.0, value=float(pricing_config["TIPO_EQUIPAMENTO"].get("RADIO", 0.0)), format="%.2f"),
    }
    
    if st.button("Salvar Preços", type="primary"):
        if umdb.update_pricing_config({"TIPO_EQUIPAMENTO": prices}):
            st.success("Preços atualizados com sucesso!")
            st.rerun()
        else:
            st.error("Ocorreu um erro ao salvar os preços.")


st.markdown("---")

# --- SEÇÃO DE UPLOAD DE ESTOQUE ---
st.subheader("Atualizar Estoque de Rastreadores")
uploaded_file = st.file_uploader("Selecione a planilha de estoque (.xlsx)", type=['xlsx'])

if uploaded_file:
    try:
        df_stock = pd.read_excel(uploaded_file, header=11, dtype={'Nº Equipamento': str, 'Nº Série': str})
        
        # Prioriza 'Nº Equipamento', se não existir, usa 'Nº Série'
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
                        # Limpa o cache para forçar a recarga do estoque na próxima vez
                        st.cache_data.clear()
                    else:
                        st.error("Ocorreu um erro ao atualizar o estoque.")

    except Exception as e:
        st.error(f"Ocorreu um erro ao processar o arquivo: {e}")

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
