# pages/6_Faturamento.py
import sys
import os

# Adiciona o diretório raiz do projeto ao sys.path para resolver o ImportError
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import streamlit as st
import pandas as pd
from datetime import datetime
import io
import user_management_db as umdb
from fpdf import FPDF

# --- 1. CONFIGURAÇÃO E AUTENTICAÇÃO ---
st.set_page_config(
    layout="wide",
    page_title="Assistente de Faturamento",
    page_icon="💲"
)

if not st.session_state.get("authentication_status"):
    st.error("🔒 Acesso Negado! Por favor, faça login para visualizar esta página.")
    st.stop()

# --- 2. FUNÇÕES AUXILIARES ---
@st.cache_data
def processar_planilha_faturamento(file_bytes, valor_gprs, valor_satelital):
    """
    Lê a planilha, extrai informações, classifica, calcula e retorna os dataframes de faturamento.
    Recebe os bytes do arquivo para funcionar com o cache do Streamlit.
    """
    try:
        uploaded_file = io.BytesIO(file_bytes)
        
        # Lê a tabela de dados principal
        df = pd.read_excel(uploaded_file, header=11, engine='openpyxl', dtype={'Equipamento': str})
        df = df.rename(columns={'Suspenso Dias Mês': 'Suspenso Dias Mes', 'Equipamento': 'Nº Equipamento'})

        required_cols = ['Cliente', 'Terminal', 'Data Ativação', 'Data Desativação', 'Dias Ativos Mês', 'Suspenso Dias Mes', 'Nº Equipamento', 'Condição']
        if not all(col in df.columns for col in required_cols):
            return None, None, None, None, None, "Erro de Colunas: Verifique se o cabeçalho está na linha 12 do arquivo Excel e se todas as colunas necessárias existem."

        nome_cliente = str(df['Cliente'].dropna().iloc[0]).strip() if not df['Cliente'].dropna().empty else "Cliente não identificado"
                
        df.dropna(subset=['Terminal'], inplace=True)
        df['Terminal'] = df['Terminal'].astype(str).str.strip()
        df['Data Ativação'] = pd.to_datetime(df['Data Ativação'], errors='coerce', dayfirst=True)
        df['Data Desativação'] = pd.to_datetime(df['Data Desativação'], errors='coerce', dayfirst=True)
        df['Dias Ativos Mês'] = pd.to_numeric(df['Dias Ativos Mês'], errors='coerce').fillna(0)
        df['Suspenso Dias Mes'] = pd.to_numeric(df['Suspenso Dias Mes'], errors='coerce').fillna(0)

        # Lógica para determinar o mês/ano do relatório
        if not df['Data Ativação'].dropna().empty:
            report_date = df['Data Ativação'].dropna().iloc[0]
        else:
            report_date = datetime.now()
        
        report_month = report_date.month
        report_year = report_date.year
        dias_no_mes = pd.Timestamp(year=report_year, month=report_month, day=1).days_in_month
        periodo_relatorio = report_date.strftime("%B de %Y")

        df['Tipo'] = df['Nº Equipamento'].apply(lambda x: 'Satelital' if len(str(x).strip()) == 8 else 'GPRS')
        df['Valor Unitario'] = df['Tipo'].apply(lambda x: valor_satelital if x == 'Satelital' else valor_gprs)

        # Classificação e cálculo
        df_desativados = df[df['Data Desativação'].notna()].copy()
        if not df_desativados.empty:
            df_desativados['Dias a Faturar'] = (df_desativados['Data Desativação'].dt.day - df_desativados['Suspenso Dias Mes']).clip(lower=0)
            df_desativados['Valor a Faturar'] = (df_desativados['Valor Unitario'] / dias_no_mes) * df_desativados['Dias a Faturar']
        
        df_restantes = df[df['Data Desativação'].isna()].copy()
        
        df_ativados = df_restantes[
            (df_restantes['Condição'].str.strip() == 'Ativado') &
            (df_restantes['Data Ativação'].dt.month == report_month) &
            (df_restantes['Data Ativação'].dt.year == report_year)
        ].copy()
        if not df_ativados.empty:
            df_ativados['Dias a Faturar'] = ((dias_no_mes - df_ativados['Data Ativação'].dt.day + 1) - df_ativados['Suspenso Dias Mes']).clip(lower=0)
            df_ativados['Valor a Faturar'] = (df_ativados['Valor Unitario'] / dias_no_mes) * df_ativados['Dias a Faturar']
        
        df_cheio = df_restantes.drop(df_ativados.index).copy()
        if not df_cheio.empty:
            df_cheio['Dias a Faturar'] = (df_cheio['Dias Ativos Mês'] - df_cheio['Suspenso Dias Mes']).clip(lower=0)
            df_cheio['Valor a Faturar'] = (df_cheio['Valor Unitario'] / dias_no_mes) * df_cheio['Dias a Faturar']
        
        return nome_cliente, periodo_relatorio, df_cheio, df_ativados, df_desativados, None
    except Exception as e:
        return None, None, None, None, None, f"Ocorreu um erro inesperado ao processar o arquivo: {e}"


def to_excel(df_cheio, df_ativados, df_desativados):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_cheio.to_excel(writer, index=False, sheet_name='Faturamento Cheio')
        df_ativados.to_excel(writer, index=False, sheet_name='Proporcional - Ativados')
        df_desativados.to_excel(writer, index=False, sheet_name='Proporcional - Desativados')
    return output.getvalue()

def create_pdf_report(nome_cliente, periodo, totais, df_cheio, df_ativados, df_desativados):
    pdf = FPDF(orientation='L', unit='mm', format='A4')
    pdf.add_page()
    try:
        pdf.image("imgs/logo.png", x=10, y=8, w=50)
    except Exception:
        pdf.set_font("Arial", "B", 20)
        pdf.cell(0, 10, "Verdio", 0, 1, "L")
    
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, "Resumo do Faturamento", 0, 1, "C")
    pdf.ln(15)

    pdf.set_font("Arial", "", 12)
    pdf.cell(0, 8, f"Cliente: {nome_cliente}", 0, 1, "L")
    pdf.cell(0, 8, f"Periodo: {periodo}", 0, 1, "L")
    pdf.ln(5)

    pdf.set_font("Arial", "B", 10)
    pdf.cell(69, 8, "Nº Fat. Cheio", 1, 0, "C")
    pdf.cell(69, 8, "Nº Fat. Proporcional", 1, 0, "C")
    pdf.cell(69, 8, "Total Terminais GPRS", 1, 0, "C")
    pdf.cell(69, 8, "Total Terminais Satelitais", 1, 1, "C")
    pdf.set_font("Arial", "", 10)
    pdf.cell(69, 8, str(totais['terminais_cheio']), 1, 0, "C")
    pdf.cell(69, 8, str(totais['terminais_proporcional']), 1, 0, "C")
    pdf.cell(69, 8, str(totais['terminais_gprs']), 1, 0, "C")
    pdf.cell(69, 8, str(totais['terminais_satelitais']), 1, 1, "C")
    pdf.ln(5)

    pdf.set_font("Arial", "B", 11)
    pdf.cell(138, 8, "Faturamento (Cheio)", 1, 0, "C")
    pdf.cell(138, 8, "Faturamento (Proporcional)", 1, 1, "C")
    pdf.set_font("Arial", "", 11)
    pdf.cell(138, 8, f"R$ {totais['cheio']:,.2f}", 1, 0, "C")
    pdf.cell(138, 8, f"R$ {totais['proporcional']:,.2f}", 1, 1, "C")
    pdf.set_font("Arial", "B", 11)
    pdf.cell(0, 10, f"FATURAMENTO TOTAL: R$ {totais['geral']:,.2f}", 1, 1, "C")
    pdf.ln(10)
    return bytes(pdf.output(dest='S').encode('latin-1'))


# --- 3. INTERFACE DA PÁGINA ---
st.sidebar.image("imgs/v-c.png", width=120)
st.sidebar.title(f"Olá, {st.session_state.get('name', 'N/A')}! 👋")
st.sidebar.markdown("---")
if st.sidebar.button("Logout"):
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

try:
    st.image("imgs/logo.png", width=250)
except: pass

st.markdown("<h1 style='text-align: center; color: #006494;'>💲 Assistente de Faturamento</h1>", unsafe_allow_html=True)
st.markdown("---")

# --- 4. INPUTS DE CONFIGURAÇÃO ---
st.sidebar.header("Valores de Faturamento")
pricing_config = umdb.get_pricing_config()
default_gprs = float(pricing_config.get("PRECOS_PF", {}).get("GPRS / Gsm", 0.0))
default_satelital = float(pricing_config.get("PLANOS_PJ", {}).get("36 Meses", {}).get("Satélite", 0.0))
valor_gprs = st.sidebar.number_input("Valor Unitário Mensal (GPRS)", min_value=0.0, value=default_gprs, step=1.0, format="%.2f")
valor_satelital = st.sidebar.number_input("Valor Unitário Mensal (Satelital)", min_value=0.0, value=default_satelital, step=1.0, format="%.2f")

# --- 5. UPLOAD DO FICHEIRO ---
st.subheader("Carregamento do Relatório de Terminais")
st.info("Por favor, carregue o ficheiro `relatorio_terminal_xx-xx-xxxx_xx-xx-xxxx.xlsx` exportado do sistema.")
uploaded_file = st.file_uploader("Selecione o relatório", type=['xlsx'])
st.markdown("---")

# --- 6. ANÁLISE E EXIBIÇÃO ---
if uploaded_file:
    if valor_gprs == 0.0 or valor_satelital == 0.0:
        st.warning("Por favor, insira os valores unitários de GPRS e Satelital na barra lateral para continuar.")
    else:
        file_bytes = uploaded_file.getvalue()
        nome_cliente, periodo_relatorio, df_cheio, df_ativados, df_desativados, error_message = processar_planilha_faturamento(file_bytes, valor_gprs, valor_satelital)
        
        if error_message:
            st.error(f"❌ {error_message}")
        elif df_cheio is not None:
            total_faturamento_cheio = df_cheio['Valor a Faturar'].sum()
            faturamento_proporcional_total = df_ativados['Valor a Faturar'].sum() + df_desativados['Valor a Faturar'].sum()
            faturamento_total_geral = total_faturamento_cheio + faturamento_proporcional_total
            df_total = pd.concat([df_cheio, df_ativados, df_desativados])
            total_gprs = len(df_total[df_total['Tipo'] == 'GPRS'])
            total_satelital = len(df_total[df_total['Tipo'] == 'Satelital'])
            
            st.header("Resumo do Faturamento")
            st.subheader(f"Cliente: {nome_cliente}")
            st.caption(f"Período: {periodo_relatorio}")
            
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Nº Fat. Cheio", len(df_cheio))
            col2.metric("Nº Fat. Proporcional", len(df_ativados) + len(df_desativados))
            col3.metric("Total GPRS", total_gprs)
            col4.metric("Total Satelitais", total_satelital)
            
            faturamento_data_log = {
                "cliente": nome_cliente, "periodo_relatorio": periodo_relatorio,
                "valor_total": faturamento_total_geral, "terminais_cheio": len(df_cheio),
                "terminais_proporcional": len(df_ativados) + len(df_desativados),
                "gerado_por": st.session_state.get("email", "N/A")
            }
            
            st.subheader("Ações Finais")
            col_btn1, col_btn2 = st.columns(2)

            with col_btn1:
                excel_data = to_excel(df_cheio, df_ativados, df_desativados)
                st.download_button(
                    label="📥 Exportar Excel e Salvar Histórico",
                    data=excel_data,
                    file_name=f"Faturamento_{nome_cliente.replace(' ', '_')}_{datetime.now().strftime('%Y-%m')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    on_click=umdb.log_faturamento, args=(faturamento_data_log,)
                )
else:
    st.info("Aguardando o carregamento do relatório para iniciar a análise.")
