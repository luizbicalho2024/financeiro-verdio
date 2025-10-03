# pages/6_Faturamento_Verdio.py
import sys
import os
import re
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import streamlit as st
import pandas as pd
from datetime import datetime
import io
import user_management_db as umdb
from fpdf import FPDF
import numpy as np

# --- CLASSE PARA GERAR PDF COM IDENTIDADE VISUAL (VERSÃO FINAL) ---
class PDF(FPDF):
    def header(self):
        try:
            page_width = self.w - self.l_margin - self.r_margin
            self.image("imgs/header1.png", x=self.l_margin, y=8, w=page_width)
        except Exception:
            self.set_font("Arial", "B", 20)
            self.cell(0, 10, "Uzzipay Soluções", 0, 1, "L")
            self.ln(15)

    def footer(self):
        try:
            self.set_y(-35)
            page_width = self.w - self.l_margin - self.r_margin
            self.image("imgs/footer1.png", x=self.l_margin, y=self.get_y(), w=page_width)
        except Exception:
            self.set_y(-15)
            self.set_font("Arial", "I", 8)
            self.cell(0, 10, f"Página {self.page_no()}", 0, 0, "C")

# --- 1. CONFIGURAÇÃO E AUTENTICAÇÃO ---
st.set_page_config(layout="wide", page_title="Verdio Faturamento", page_icon="imgs/v-c.png")
if "user_info" not in st.session_state:
    st.error("🔒 Acesso Negado! Por favor, faça login para visualizar esta página.")
    st.stop()

# --- BARRA LATERAL ---
st.sidebar.image("imgs/v-c.png", width=120)
st.sidebar.title(f"Olá, {st.session_state.get('name', 'N/A')}! 👋")
st.sidebar.markdown("---")
if st.sidebar.button("Logout"):
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.switch_page("1_Home.py")

# --- 2. FUNÇÕES AUXILIARES ---
@st.cache_data
def processar_planilha_faturamento(file_bytes, tracker_inventory, prices):
    try:
        meses_pt = {"January": "Janeiro", "February": "Fevereiro", "March": "Março", "April": "Abril", "May": "Maio", "June": "Junho", "July": "Julho", "August": "Agosto", "September": "Setembro", "October": "Outubro", "November": "Novembro", "December": "Dezembro"}
        
        # --- LÓGICA ATUALIZADA PARA LER PERÍODO DA CÉLULA I9 ---
        try:
            periodo_df = pd.read_excel(io.BytesIO(file_bytes), header=None, sheet_name=0)
            periodo_str = periodo_df.iloc[8, 8]  # Linha 9, Coluna I
            # Extrai a primeira data da string "Período Apuração: 01/09/2025 a 30/09/2025"
            start_date_str = re.search(r'(\d{2}/\d{2}/\d{4})', periodo_str).group(1)
            report_date = pd.to_datetime(start_date_str, dayfirst=True)
        except Exception:
            st.warning("Não foi possível ler o período da célula I9. Usando data atual como referência.")
            report_date = datetime.now()

        df = pd.read_excel(io.BytesIO(file_bytes), header=11, engine='openpyxl', dtype={'Equipamento': str})
        df = df.rename(columns={'Suspenso Dias Mês': 'Suspenso Dias Mes', 'Equipamento': 'Nº Equipamento'})
        df.dropna(subset=['Terminal'], inplace=True)

        required_cols = ['Cliente', 'Terminal', 'Data Ativação', 'Data Desativação', 'Dias Ativos Mês', 'Suspenso Dias Mes', 'Nº Equipamento', 'Condição']
        if not all(col in df.columns for col in required_cols):
            return None, "Erro de Colunas: Verifique o cabeçalho na linha 12.", None, None

        nome_cliente = str(df['Cliente'].dropna().iloc[0]).strip() if not df['Cliente'].dropna().empty else "Cliente não identificado"

        for col in ['Data Ativação', 'Data Desativação']:
            df[col] = pd.to_datetime(df[col], errors='coerce', dayfirst=True)
        for col in ['Dias Ativos Mês', 'Suspenso Dias Mes']:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

        report_month, report_year = report_date.month, report_date.year
        dias_no_mes = pd.Timestamp(year=report_year, month=report_month, day=1).days_in_month
        periodo_relatorio = f"{meses_pt.get(report_date.strftime('%B'), report_date.strftime('%B'))} de {report_year}"
        
        df_inventory = pd.DataFrame(tracker_inventory)
        df_merged = pd.merge(df, df_inventory, on='Nº Equipamento', how='left')

        not_found_equip = df_merged[df_merged['Tipo'].isna()]['Nº Equipamento'].tolist()
        
        df_merged['Valor Unitario'] = df_merged['Tipo'].map(prices).fillna(0)

        conditions = [
            (df_merged['Data Desativação'].notna()),
            (df_merged['Data Ativação'].dt.month == report_month) & (df_merged['Data Ativação'].dt.year == report_year),
            (df_merged['Condição'].str.strip() == 'Suspenso')
        ]
        choices = ['Desativado', 'Ativado no Mês', 'Suspenso']
        df_merged['Categoria'] = np.select(conditions, choices, default='Cheio')
        
        dias_a_faturar = 0
        dias_a_faturar = np.where(df_merged['Categoria'] == 'Desativado', df_merged['Data Desativação'].dt.day - df_merged['Suspenso Dias Mes'], dias_a_faturar)
        dias_a_faturar = np.where(df_merged['Categoria'] == 'Ativado no Mês', (dias_no_mes - df_merged['Data Ativação'].dt.day + 1) - df_merged['Suspenso Dias Mes'], dias_a_faturar)
        dias_a_faturar = np.where(df_merged['Categoria'].isin(['Suspenso', 'Cheio']), df_merged['Dias Ativos Mês'] - df_merged['Suspenso Dias Mes'], dias_a_faturar)
        
        df_merged['Dias a Faturar'] = np.clip(dias_a_faturar, 0, None)
        df_merged['Valor a Faturar'] = (df_merged['Valor Unitario'] / dias_no_mes) * df_merged['Dias a Faturar']
        
        return nome_cliente, periodo_relatorio, df_merged, not_found_equip, None

    except Exception as e:
        return None, None, None, None, f"Ocorreu um erro inesperado: {e}"


# (As funções to_excel e create_pdf_report permanecem inalteradas)

# --- 3. INTERFACE DA PÁGINA ---
st.image("imgs/logo.png", width=250)
st.markdown("<h1 style='text-align: center; color: #006494;'>Verdio Assistente de Faturamento</h1>", unsafe_allow_html=True)
st.markdown("---")

# --- 4. INPUTS DE CONFIGURAÇÃO ---
st.sidebar.header("Valores de Faturamento")
pricing_config = umdb.get_pricing_config().get("TIPO_EQUIPAMENTO", {})

# Lógica para aplicar valores do mês anterior, se solicitado
if 'prices_to_apply' in st.session_state:
    default_prices = st.session_state.pop('prices_to_apply')
else:
    default_prices = pricing_config

# Inputs editáveis na sidebar
prices = {}
for equip_type in ["GPRS", "SATELITE", "CAMERA", "RADIO"]:
    prices[equip_type] = st.sidebar.number_input(
        f"Preço {equip_type}",
        min_value=0.0,
        value=float(default_prices.get(equip_type, 0.0)),
        format="%.2f"
    )

# --- 5. UPLOAD DO FICHEIRO ---
st.subheader("Carregamento do Relatório de Terminais")
st.info("Por favor, carregue o ficheiro `relatorio_terminal_xx-xx-xxxx_xx-xx-xxxx.xlsx` exportado do sistema.")
uploaded_file = st.file_uploader("Selecione o relatório", type=['xlsx'])
st.markdown("---")

# --- 6. ANÁLISE E EXIBIÇÃO ---
if uploaded_file:
    tracker_inventory = umdb.get_tracker_inventory()
    if not tracker_inventory:
        st.warning("⚠️ Nenhum dado de estoque de rastreadores encontrado. Atualize o estoque na página de 'Gestão de Estoque'.")
        st.stop()
    
    file_bytes = uploaded_file.getvalue()
    nome_cliente, periodo_relatorio, df_final, not_found, error = processar_planilha_faturamento(file_bytes, tracker_inventory, prices)

    if error:
        st.error(error)
    elif df_final is not None:
        # --- LÓGICA PARA SUGERIR PREÇOS DO ÚLTIMO FATURAMENTO ---
        last_billing = umdb.get_last_billing_for_client(nome_cliente)
        if last_billing:
            last_prices = {
                "GPRS": last_billing.get("valor_unitario_gprs", prices["GPRS"]),
                "SATELITE": last_billing.get("valor_unitario_satelital", prices["SATELITE"]),
                # Adicione outros tipos se eles forem salvos no histórico
            }
            # Compara se os preços atuais são diferentes dos últimos encontrados
            if any(prices.get(k, 0) != v for k, v in last_prices.items()):
                st.info(f"💡 Encontramos os valores utilizados no último faturamento para **{nome_cliente}**.")
                cols = st.columns(len(last_prices) + 1)
                i = 0
                for p_type, p_val in last_prices.items():
                    cols[i].metric(f"Último Preço {p_type}", f"R$ {p_val:.2f}")
                    i += 1
                
                if cols[i].button("Aplicar valores e recalcular"):
                    st.session_state['prices_to_apply'] = last_prices
                    st.rerun()

        if not_found:
            with st.expander("⚠️ Equipamentos Não Encontrados no Estoque", expanded=True):
                st.warning("Os seguintes equipamentos não foram encontrados no estoque e não serão faturados.")
                st.json(not_found)

        df_cheio = df_final[df_final['Categoria'] == 'Cheio'].copy()
        df_ativados = df_final[df_final['Categoria'] == 'Ativado no Mês'].copy()
        df_desativados = df_final[df_final['Categoria'] == 'Desativado'].copy()
        df_suspensos = df_final[df_final['Categoria'] == 'Suspenso'].copy()
        
        total_cheio = df_cheio['Valor a Faturar'].sum()
        total_proporcional = df_ativados['Valor a Faturar'].sum() + df_desativados['Valor a Faturar'].sum() + df_suspensos['Valor a Faturar'].sum()
        total_geral = total_cheio + total_proporcional

        st.header("Resumo do Faturamento")
        st.subheader(f"Cliente: {nome_cliente}"); st.caption(f"Período: {periodo_relatorio}")

        num_prop = len(df_ativados) + len(df_desativados)
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Nº Fat. Cheio", len(df_cheio)); c2.metric("Nº Fat. Proporcional", num_prop); c3.metric("Nº Suspensos", len(df_suspensos))
        c4.metric("Total GPRS", len(df_final[df_final['Tipo'] == 'GPRS'])); c5.metric("Total Satelitais", len(df_final[df_final['Tipo'] == 'SATELITE']))
        
        c1, c2, c3 = st.columns(3)
        c1.success(f"**Faturamento (Cheio):** R$ {total_cheio:,.2f}"); c2.warning(f"**Faturamento (Proporcional):** R$ {total_proporcional:,.2f}"); c3.info(f"**FATURAMENTO TOTAL:** R$ {total_geral:,.2f}")
        
        st.markdown("---"); st.subheader("Ações Finais")
        
        excel_data = to_excel(df_cheio, df_ativados, df_desativados, df_suspensos)
        log_data = {
            "cliente": nome_cliente, "periodo_relatorio": periodo_relatorio, "valor_total": total_geral,
            "terminais_cheio": len(df_cheio), "terminais_proporcional": num_prop, "terminais_suspensos": len(df_suspensos),
            "terminais_gprs": len(df_final[df_final['Tipo'] == 'GPRS']), "terminais_satelitais": len(df_final[df_final['Tipo'] == 'SATELITE']),
            "valor_unitario_gprs": prices.get("GPRS", 0), "valor_unitario_satelital": prices.get("SATELITE", 0)
        }
        pdf_data = create_pdf_report(nome_cliente, periodo_relatorio, {"cheio": total_cheio, "proporcional": total_proporcional, "geral": total_geral, "terminais_cheio": len(df_cheio), "terminais_proporcional": num_prop, "terminais_suspensos": len(df_suspensos), "terminais_gprs": len(df_final[df_final['Tipo'] == 'GPRS']), "terminais_satelitais": len(df_final[df_final['Tipo'] == 'SATELITE'])}, df_cheio, df_ativados, df_desativados, df_suspensos)
        
        c1, c2 = st.columns(2)
        c1.download_button("📥 Exportar Excel e Salvar Histórico", excel_data, f"Faturamento_{nome_cliente.replace(' ', '_')}_{datetime.now().strftime('%Y-%m')}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", on_click=umdb.log_faturamento, args=(log_data,))
        c2.download_button("📄 Exportar Resumo em PDF", pdf_data, f"Resumo_Faturamento_{nome_cliente.replace(' ', '_')}_{datetime.now().strftime('%Y-%m')}.pdf", "application/pdf", on_click=umdb.log_faturamento, args=(log_data,))

        st.markdown("---")
        cols_to_show = ['Terminal', 'Nº Equipamento', 'Modelo', 'Tipo', 'Data Ativação', 'Dias Ativos Mês', 'Suspenso Dias Mes', 'Dias a Faturar', 'Valor Unitario', 'Valor a Faturar']
        
        with st.expander("Detalhamento do Faturamento Cheio"):
            st.dataframe(df_cheio[['Terminal', 'Nº Equipamento', 'Modelo', 'Tipo', 'Dias a Faturar', 'Valor a Faturar']], use_container_width=True, hide_index=True)
        with st.expander("Detalhamento Proporcional (Ativações no Mês)"):
            st.dataframe(df_ativados[cols_to_show], use_container_width=True, hide_index=True)
        with st.expander("Detalhamento Proporcional (Desativações no Mês)"):
            st.dataframe(df_desativados[cols_to_show], use_container_width=True, hide_index=True)
        with st.expander("Detalhamento dos Terminais Suspensos (Faturamento Proporcional)"):
            st.dataframe(df_suspensos[cols_to_show], use_container_width=True, hide_index=True)
else:
    st.info("Aguardando o carregamento do relatório para iniciar a análise.")
