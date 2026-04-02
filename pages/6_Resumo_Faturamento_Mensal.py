# pages/10_Resumo_Faturamento_Mensal.py
import sys
import os
import re
import io
import pandas as pd
import numpy as np
import streamlit as st
from datetime import datetime

# Adiciona o caminho base para importar o banco de dados
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import user_management_db as umdb

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(layout="wide", page_title="Resumo Faturamento Mensal", page_icon="📊")

if "user_info" not in st.session_state:
    st.error("🔒 Acesso Negado! Por favor, faça login.")
    st.stop()

# --- BARRA LATERAL ---
st.sidebar.image("imgs/v-c.png", width=120)
st.sidebar.title("Resumo Mensal")
if st.sidebar.button("Voltar para Home"):
    st.switch_page("1_Home.py")

st.title("📊 Resumo de Faturamento Mensal")
st.markdown("Esta página processa a planilha global e calcula o faturamento bruto baseado no histórico de cada cliente.")

# --- FUNÇÕES DE PROCESSAMENTO ---
def extrair_periodo(file_bytes):
    try:
        df_meta = pd.read_excel(io.BytesIO(file_bytes), header=None, sheet_name=0)
        periodo_str = str(df_meta.iloc[8, 8]) # Célula I9
        match = re.search(r'(\d{2}[-/]\d{2}[-/]\d{4})', periodo_str)
        if match:
            data = pd.to_datetime(match.group(1).replace('-', '/'), dayfirst=True)
            meses_pt = {1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril", 5: "Maio", 6: "Junho", 
                        7: "Julho", 8: "Agosto", 9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"}
            return f"{meses_pt[data.month]} de {data.year}", data.month, data.year
    except:
        pass
    return "Período não identificado", datetime.now().month, datetime.now().year

def calcular_faturamento_cliente(df_cliente, report_month, report_year, inventory, default_pricing):
    if df_cliente.empty:
        return 0.0
    
    nome_cliente = df_cliente['Cliente'].iloc[0]
    
    # Busca preços históricos no banco de dados
    historico = umdb.get_last_billing_for_client(nome_cliente)
    if historico:
        prices = {
            "GPRS": historico.get("valor_unitario_gprs", default_pricing.get("GPRS", 0)),
            "SATELITE": historico.get("valor_unitario_satelital", default_pricing.get("SATELITE", 0))
        }
    else:
        prices = default_pricing

    # Prepara inventário
    df_inv = pd.DataFrame(inventory)
    
    # --- CORREÇÃO DO ERRO DE MERGE: Forçar tipo string e limpar espaços ---
    df_cliente['Nº Equipamento'] = df_cliente['Nº Equipamento'].astype(str).str.strip()
    df_inv['Nº Equipamento'] = df_inv['Nº Equipamento'].astype(str).str.strip()
    
    df_merged = pd.merge(df_cliente, df_inv, on='Nº Equipamento', how='left')
    
    # Datas e Dias
    dias_no_mes = pd.Timestamp(year=report_year, month=report_month, day=1).days_in_month
    df_merged['Data Ativação'] = pd.to_datetime(df_merged['Data Ativação'], errors='coerce', dayfirst=True)
    df_merged['Data Desativação'] = pd.to_datetime(df_merged['Data Desativação'], errors='coerce', dayfirst=True)
    
    # Atribui preço baseado no tipo (GPRS/SATELITE)
    df_merged['Valor Unitario'] = df_merged['Tipo'].map(prices).fillna(0)
    
    # Lógica Proporcional Exata do financeiro-verdio
    # Mapeia colunas para evitar erros de acentuação na planilha
    suspenso_col = 'Suspenso Dias Mês' if 'Suspenso Dias Mês' in df_merged.columns else 'Suspenso Dias Mes'
    dias_ativos_col = 'Dias Ativos Mês' if 'Dias Ativos Mês' in df_merged.columns else 'Dias Ativos Mes'

    dias_a_faturar = np.where(
        df_merged['Data Desativação'].notna(), 
        df_merged['Data Desativação'].dt.day - df_merged[suspenso_col].fillna(0),
        np.where(
            (df_merged['Data Ativação'].dt.month == report_month) & (df_merged['Data Ativação'].dt.year == report_year), 
            (dias_no_mes - df_merged['Data Ativação'].dt.day + 1) - df_merged[suspenso_col].fillna(0),
            df_merged[dias_ativos_col].fillna(0) - df_merged[suspenso_col].fillna(0)
        )
    )
    
    df_merged['Valor Calculado'] = (df_merged['Valor Unitario'] / dias_no_mes) * np.clip(dias_a_faturar, 0, None)
    
    return df_merged['Valor Calculado'].sum()

# --- INTERFACE DE UPLOAD ---
uploaded_file = st.file_uploader("Suba a planilha global de terminais (.xlsx)", type=['xlsx'])

if uploaded_file:
    with st.spinner("Calculando faturamento global..."):
        file_bytes = uploaded_file.getvalue()
        tracker_inventory = umdb.get_tracker_inventory()
        pricing_config = umdb.get_pricing_config().get("TIPO_EQUIPAMENTO", {})
        
        # Preços padrão do sistema
        default_prices = {}
        for k, v in pricing_config.items():
            default_prices[k] = v.get("price1", 0) if isinstance(v, dict) else v

        periodo_texto, m, y = extrair_periodo(file_bytes)
        
        # Lê a planilha forçando 'Equipamento' como string e renomeando para o padrão interno
        df_geral = pd.read_excel(io.BytesIO(file_bytes), header=11, dtype={'Equipamento': str})
        df_geral = df_geral.rename(columns={'Equipamento': 'Nº Equipamento'})
        df_geral = df_geral.dropna(subset=['Cliente', 'Terminal'])

        resumo_dados = []
        clientes_unicos = df_geral['Cliente'].unique()

        for cliente in clientes_unicos:
            df_c = df_geral[df_geral['Cliente'] == cliente].copy()
            total_bruto = calcular_faturamento_cliente(df_c, m, y, tracker_inventory, default_prices)
            
            resumo_dados.append({
                "Cliente": cliente,
                "Bruto Total (R$)": total_bruto,
                "Mês de Referência": periodo_texto
            })

        # Exibição dos Resultados
        df_resumo = pd.DataFrame(resumo_dados).sort_values(by="Cliente")
        
        st.subheader(f"Resumo Processado: {periodo_texto}")
        
        c1, c2 = st.columns(2)
        c1.metric("Total de Clientes", len(df_resumo))
        c2.metric("Valor Total Global", f"R$ {df_resumo['Bruto Total (R$)'].sum():,.2f}")

        st.dataframe(
            df_resumo,
            column_config={
                "Bruto Total (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
            },
            use_container_width=True,
            hide_index=True
        )

        csv = df_resumo.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="📥 Baixar Tabela de Faturamento (CSV)",
            data=csv,
            file_name=f"Resumo_Geral_Verdio_{y}_{m}.csv",
            mime="text/csv",
        )
else:
    st.info("Suba o relatório de terminais para gerar a listagem de faturamento por cliente.")
