# pages/6_Faturamento.py
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
def processar_planilha_faturamento(uploaded_file, valor_gprs, valor_satelital):
    """
    Lê a planilha, extrai informações, classifica, calcula e retorna os dataframes de faturamento.
    """
    # Lê as primeiras 11 linhas para extrair informações do cabeçalho
    header_info = pd.read_excel(uploaded_file, header=None, nrows=11, engine='openpyxl')
    
    periodo_relatorio = "Período não identificado"
    # Determina o mês e ano do relatório a partir dos próprios dados mais tarde
    
    # Lê a tabela de dados principal
    df = pd.read_excel(uploaded_file, header=11, engine='openpyxl', dtype={'Equipamento': str})
    df = df.rename(columns={'Suspenso Dias Mês': 'Suspenso Dias Mes', 'Equipamento': 'Nº Equipamento'})

    required_cols = ['Cliente', 'Terminal', 'Data Ativação', 'Data Desativação', 'Dias Ativos Mês', 'Suspenso Dias Mes', 'Nº Equipamento', 'Condição']
    if not all(col in df.columns for col in required_cols):
        return None, None, None, None, None, "Erro de Colunas: Verifique o cabeçalho na linha 12."

    nome_cliente = str(df['Cliente'].dropna().iloc[0]).strip() if not df.empty and 'Cliente' in df.columns else "Cliente não identificado"
            
    df.dropna(subset=['Terminal'], inplace=True)
    df['Terminal'] = df['Terminal'].astype(str).str.strip()
    df['Data Ativação'] = pd.to_datetime(df['Data Ativação'], errors='coerce', dayfirst=True)
    df['Data Desativação'] = pd.to_datetime(df['Data Desativação'], errors='coerce', dayfirst=True)
    df['Dias Ativos Mês'] = pd.to_numeric(df['Dias Ativos Mês'], errors='coerce').fillna(0)
    df['Suspenso Dias Mes'] = pd.to_numeric(df['Suspenso Dias Mes'], errors='coerce').fillna(0)

    # LÓGICA DE DETECÇÃO DE PERÍODO E FATURAMENTO CORRIGIDA
    # Determina o mês e ano do relatório a partir dos dados de data
    if not df[df['Data Desativação'].notna()].empty:
        report_date = df[df['Data Desativação'].notna()]['Data Desativação'].iloc[0]
    elif not df[df['Data Ativação'].notna()].empty:
        report_date = df[df['Data Ativação'].notna()]['Data Ativação'].iloc[0]
    else:
        report_date = datetime.now() # Fallback para o mês atual
    
    report_month = report_date.month
    report_year = report_date.year
    dias_no_mes = pd.Timestamp(year=report_year, month=report_month, day=1).days_in_month
    periodo_relatorio = report_date.strftime("%B de %Y") # Ex: Agosto de 2025

    df['Tipo'] = df['Nº Equipamento'].apply(lambda x: 'Satelital' if len(str(x).strip()) == 8 else 'GPRS')
    df['Valor Unitario'] = df['Tipo'].apply(lambda x: valor_satelital if x == 'Satelital' else valor_gprs)

    # Separa os desativados primeiro
    df_desativados = df[df['Data Desativação'].notna()].copy()
    if not df_desativados.empty:
        df_desativados['Dias a Faturar'] = (df_desativados['Data Desativação'].dt.day - df_desativados['Suspenso Dias Mes']).clip(lower=0)
        df_desativados['Valor a Faturar'] = (df_desativados['Valor Unitario'] / dias_no_mes) * df_desativados['Dias a Faturar']
    
    # Pega os restantes para analisar
    df_restantes = df[df['Data Desativação'].isna()].copy()
    
    # Separa os ativados no mês
    df_ativados = df_restantes[
        (df_restantes['Condição'].str.strip() == 'Ativado') &
        (df_restantes['Data Ativação'].dt.month == report_month) &
        (df_restantes['Data Ativação'].dt.year == report_year)
    ].copy()
    if not df_ativados.empty:
        df_ativados['Dias a Faturar'] = ((dias_no_mes - df_ativados['Data Ativação'].dt.day + 1) - df_ativados['Suspenso Dias Mes']).clip(lower=0)
        df_ativados['Valor a Faturar'] = (df_ativados['Valor Unitario'] / dias_no_mes) * df_ativados['Dias a Faturar']
    
    # O que sobrou é faturamento cheio
    df_cheio = df_restantes.drop(df_ativados.index).copy()
    if not df_cheio.empty:
        df_cheio['Dias a Faturar'] = (df_cheio['Dias Ativos Mês'] - df_cheio['Suspenso Dias Mes']).clip(lower=0)
        df_cheio['Valor a Faturar'] = (df_cheio['Valor Unitario'] / dias_no_mes) * df_cheio['Dias a Faturar']
    
    return nome_cliente, periodo_relatorio, df_cheio, df_ativados, df_desativados, None

@st.cache_data
def to_excel(df_cheio, df_ativados, df_desativados):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_cheio.to_excel(writer, index=False, sheet_name='Faturamento Cheio')
        df_ativados.to_excel(writer, index=False, sheet_name='Proporcional - Ativados')
        df_desativados.to_excel(writer, index=False, sheet_name='Proporcional - Desativados')
    return output.getvalue()

def create_pdf_report(nome_cliente, periodo, totais, df_cheio, df_ativados, df_desativados):
    pdf = FPDF(orientation='L')
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

    def draw_table(title, df, col_widths, available_cols):
        if not df.empty:
            pdf.set_font("Arial", "B", 12)
            pdf.cell(0, 10, title, 0, 1, "L")
            pdf.set_font("Arial", "B", 8)
            
            header = [h for h in available_cols if h in df.columns]
            
            for h in header:
                pdf.cell(col_widths.get(h, 20), 7, h, 1, 0, 'C')
            pdf.ln()

            pdf.set_font("Arial", "", 7)
            for _, row in df.iterrows():
                for h in header:
                    cell_text = str(row[h])
                    if isinstance(row[h], datetime) and pd.notna(row[h]):
                        cell_text = row[h].strftime('%d/%m/%Y')
                    elif isinstance(row[h], (float, int)):
                        cell_text = f"R$ {row[h]:,.2f}" if 'Valor' in h else str(int(row[h]))
                    elif pd.isna(row[h]):
                        cell_text = ""
                    pdf.cell(col_widths.get(h, 20), 6, cell_text, 1, 0, 'C')
                pdf.ln()
            pdf.ln(5)

    cols_cheio = ['Terminal', 'Nº Equipamento', 'Placa', 'Tipo', 'Valor a Faturar']
    widths_cheio = {'Terminal': 60, 'Nº Equipamento': 60, 'Placa': 60, 'Tipo': 47, 'Valor a Faturar': 50}
    draw_table("Detalhamento do Faturamento Cheio", df_cheio, widths_cheio, cols_cheio)
    
    cols_ativados = ['Terminal', 'Nº Equipamento', 'Placa', 'Tipo', 'Data Ativação', 'Dias Ativos Mês', 'Suspenso Dias Mes', 'Dias a Faturar', 'Valor Unitario', 'Valor a Faturar']
    widths_ativados = {
        'Terminal': 25, 'Nº Equipamento': 30, 'Placa': 25, 'Tipo': 20, 'Data Ativação': 25,
        'Dias Ativos Mês': 20, 'Suspenso Dias Mes': 25, 'Dias a Faturar': 20, 
        'Valor Unitario': 30, 'Valor a Faturar': 30
    }
    draw_table("Detalhamento Proporcional (Ativações no Mês)", df_ativados, widths_ativados, cols_ativados)

    cols_desativados = ['Terminal', 'Nº Equipamento', 'Placa', 'Tipo', 'Data Desativação', 'Dias Ativos Mês', 'Suspenso Dias Mes', 'Dias a Faturar', 'Valor Unitario', 'Valor a Faturar']
    widths_desativados = {
        'Terminal': 25, 'Nº Equipamento': 30, 'Placa': 25, 'Tipo': 20,
        'Data Desativação': 25, 'Dias Ativos Mês': 20, 'Suspenso Dias Mes': 25, 
        'Dias a Faturar': 20, 'Valor Unitario': 30, 'Valor a Faturar': 30
    }
    draw_table("Detalhamento Proporcional (Desativações no Mês)", df_desativados, widths_desativados, cols_desativados)
    
    return bytes(pdf.output())

# --- 3. INTERFACE DA PÁGINA ---
st.sidebar.image("imgs/v-c.png", width=120)
st.sidebar.title(f"Olá, {st.session_state.get('name', 'N/A')}! 👋")
st.sidebar.markdown("---")

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
        try:
            nome_cliente, periodo_relatorio, df_cheio, df_ativados, df_desativados, error_message = processar_planilha_faturamento(uploaded_file, valor_gprs, valor_satelital)
            
            if error_message:
                st.error(error_message)
            elif df_cheio is not None:
                total_faturamento_cheio = df_cheio['Valor a Faturar'].sum() if not df_cheio.empty else 0
                total_faturamento_ativados = df_ativados['Valor a Faturar'].sum() if not df_ativados.empty else 0
                total_faturamento_desativados = df_desativados['Valor a Faturar'].sum() if not df_desativados.empty else 0
                faturamento_proporcional_total = total_faturamento_ativados + total_faturamento_desativados
                faturamento_total_geral = total_faturamento_cheio + faturamento_proporcional_total

                st.header("Resumo do Faturamento")
                st.subheader(f"Cliente: {nome_cliente}")
                st.caption(f"Período: {periodo_relatorio}")
                
                df_total = pd.concat([df_cheio, df_ativados, df_desativados])
                total_gprs = len(df_total[df_total['Tipo'] == 'GPRS'])
                total_satelital = len(df_total[df_total['Tipo'] == 'Satelital'])
                
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Nº Fat. Cheio", value=len(df_cheio))
                col2.metric("Nº Fat. Proporcional", value=len(df_ativados) + len(df_desativados))
                col3.metric("Total GPRS", value=total_gprs)
                col4.metric("Total Satelitais", value=total_satelital)
                
                col_a, col_b, col_c = st.columns(3)
                col_a.success(f"**Faturamento (Cheio):** R$ {total_faturamento_cheio:,.2f}")
                col_b.warning(f"**Faturamento (Proporcional):** R$ {faturamento_proporcional_total:,.2f}")
                col_c.info(f"**FATURAMENTO TOTAL:** R$ {faturamento_total_geral:,.2f}")

                st.markdown("---")
                
                st.subheader("Ações Finais")
                excel_data = to_excel(df_cheio, df_ativados, df_desativados)
                totais_pdf = {
                    "cheio": total_faturamento_cheio, "proporcional": faturamento_proporcional_total, "geral": faturamento_total_geral,
                    "terminais_cheio": len(df_cheio), "terminais_proporcional": len(df_ativados) + len(df_desativados),
                    "terminais_gprs": total_gprs, "terminais_satelitais": total_satelital
                }
                pdf_data = create_pdf_report(nome_cliente, periodo_relatorio, totais_pdf, df_cheio, df_ativados, df_desativados)
                faturamento_data_log = {
                    "cliente": nome_cliente, "periodo_relatorio": periodo_relatorio,
                    "valor_total": faturamento_total_geral, "terminais_cheio": len(df_cheio),
                    "terminais_proporcional": len(df_ativados) + len(df_desativados),
                    "terminais_gprs": total_gprs, "terminais_satelitais": total_satelital,
                    "valor_unitario_gprs": valor_gprs, "valor_unitario_satelital": valor_satelital
                }

                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    st.download_button(
                       label="📥 Exportar Excel e Salvar Histórico",
                       data=excel_data,
                       file_name=f"Faturamento_{nome_cliente.replace(' ', '_')}_{datetime.now().strftime('%Y-%m')}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       on_click=umdb.log_faturamento, args=(faturamento_data_log,)
                    )
                with col_btn2:
                    st.download_button(
                       label="📄 Exportar Resumo em PDF",
                       data=pdf_data,
                       file_name=f"Resumo_Faturamento_{nome_cliente.replace(' ', '_')}_{datetime.now().strftime('%Y-%m')}.pdf",
                       mime="application/pdf",
                       on_click=umdb.log_faturamento, args=(faturamento_data_log,)
                    )

                st.markdown("---")

                with st.expander("Detalhamento do Faturamento Proporcional (Ativações no Mês)"):
                    if not df_ativados.empty:
                        st.dataframe(df_ativados[['Terminal', 'Nº Equipamento', 'Placa', 'Tipo', 'Data Ativação', 'Dias Ativos Mês', 'Suspenso Dias Mes', 'Dias a Faturar', 'Valor Unitario', 'Valor a Faturar']], use_container_width=True, hide_index=True)
                    else:
                        st.info("Nenhum terminal ativado com faturamento proporcional neste período.")
                
                with st.expander("Detalhamento do Faturamento Proporcional (Desativações no Mês)"):
                    if not df_desativados.empty:
                        st.dataframe(df_desativados[['Terminal', 'Nº Equipamento', 'Placa', 'Tipo', 'Data Desativação', 'Dias Ativos Mês', 'Suspenso Dias Mes', 'Dias a Faturar', 'Valor Unitario', 'Valor a Faturar']], use_container_width=True, hide_index=True)
                    else:
                        st.info("Nenhum terminal desativado neste período.")
                
                with st.expander("Detalhamento do Faturamento Cheio"):
                    if not df_cheio.empty:
                        st.dataframe(df_cheio[['Terminal', 'Nº Equipamento', 'Placa', 'Tipo', 'Valor a Faturar']], use_container_width=True, hide_index=True)
                    else:
                        st.info("Nenhum terminal com faturamento cheio neste período.")

        except Exception as e:
            st.error(f"Ocorreu um erro ao processar o ficheiro: {e}")
            st.info("Por favor, verifique se o ficheiro tem o formato e as colunas esperadas.")
else:
    st.info("Aguardando o carregamento do relatório para iniciar a análise.")
