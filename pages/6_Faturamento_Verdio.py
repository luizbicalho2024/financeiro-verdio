# pages/6_Faturamento_Verdio.py
import sys
import os
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
    """
    Classe customizada para gerar PDFs com cabeçalho e rodapé padrão da Uzzipay.
    """
    def header(self):
        """
        Adiciona o cabeçalho com o logo da Uzzipay Soluções em todas as páginas.
        """
        try:
            page_width = self.w - self.l_margin - self.r_margin
            self.image("imgs/header1.png", x=self.l_margin, y=8, w=page_width)
        except Exception:
            self.set_font("Arial", "B", 20)
            self.cell(0, 10, "Uzzipay Soluções", 0, 1, "L")
            self.ln(15)

    def footer(self):
        """
        Adiciona o rodapé com as informações da empresa em todas as páginas.
        """
        try:
            self.set_y(-35)
            page_width = self.w - self.l_margin - self.r_margin
            self.image("imgs/footer1.png", x=self.l_margin, y=self.get_y(), w=page_width)
        except Exception:
            self.set_y(-15)
            self.set_font("Arial", "I", 8)
            self.cell(0, 10, f"Página {self.page_no()}", 0, 0, "C")

# --- 1. CONFIGURAÇÃO E AUTENTICAÇÃO ---
st.set_page_config(
    layout="wide",
    page_title="Verdio Faturamento",
    page_icon="imgs/v-c.png"
)

# --- VERIFICAÇÃO DE LOGIN ---
if "user_info" not in st.session_state:
    st.error("🔒 Acesso Negado! Por favor, faça login para visualizar esta página.")
    st.stop()

# --- BARRA LATERAL PADRONIZADA ---
st.sidebar.image("imgs/v-c.png", width=120)
st.sidebar.title(f"Olá, {st.session_state.get('name', 'N/A')}! 👋")
st.sidebar.markdown("---")
if st.sidebar.button("Logout"):
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.switch_page("1_Home.py")


# --- 2. FUNÇÕES AUXILIARES ---
@st.cache_data
def processar_planilha_faturamento(file_bytes, valor_gprs, valor_satelital):
    """
    Lê a planilha, extrai informações, classifica, calcula e retorna os dataframes de faturamento.
    """
    try:
        meses_pt = {
            "January": "Janeiro", "February": "Fevereiro", "March": "Março",
            "April": "Abril", "May": "Maio", "June": "Junho",
            "July": "Julho", "August": "Agosto", "September": "Setembro",
            "October": "Outubro", "November": "Novembro", "December": "Dezembro"
        }

        df = pd.read_excel(io.BytesIO(file_bytes), header=11, engine='openpyxl', dtype={'Equipamento': str})
        df = df.rename(columns={'Suspenso Dias Mês': 'Suspenso Dias Mes', 'Equipamento': 'Nº Equipamento'})
        df.dropna(subset=['Terminal'], inplace=True)

        required_cols = ['Cliente', 'Terminal', 'Data Ativação', 'Data Desativação', 'Dias Ativos Mês', 'Suspenso Dias Mes', 'Nº Equipamento', 'Condição']
        if not all(col in df.columns for col in required_cols):
            return None, None, None, None, None, None, "Erro de Colunas: Verifique o cabeçalho na linha 12."

        nome_cliente = str(df['Cliente'].dropna().iloc[0]).strip() if not df.empty else "Cliente não identificado"

        for col in ['Data Ativação', 'Data Desativação']:
            df[col] = pd.to_datetime(df[col], errors='coerce', dayfirst=True)
        for col in ['Dias Ativos Mês', 'Suspenso Dias Mes']:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

        # Determina o Mês/Ano de referência do relatório
        report_date = df[df['Data Desativação'].notna()]['Data Desativação'].iloc[0] if not df[df['Data Desativação'].notna()].empty else \
                      df[df['Data Ativação'].notna()]['Data Ativação'].iloc[0] if not df[df['Data Ativação'].notna()].empty else datetime.now()
        report_month, report_year = report_date.month, report_date.year
        dias_no_mes = pd.Timestamp(year=report_year, month=report_month, day=1).days_in_month
        periodo_relatorio = f"{meses_pt.get(report_date.strftime('%B'), report_date.strftime('%B'))} de {report_year}"

        df['Tipo'] = np.where(df['Nº Equipamento'].str.len() == 8, 'Satelital', 'GPRS')
        df['Valor Unitario'] = np.where(df['Tipo'] == 'Satelital', valor_satelital, valor_gprs)

        # --- LÓGICA DE CLASSIFICAÇÃO REFEITA ---
        conditions = [
            (df['Data Desativação'].notna()),
            (df['Data Ativação'].dt.month == report_month) & (df['Data Ativação'].dt.year == report_year),
            (df['Condição'].str.strip() == 'Suspenso')
        ]
        choices = ['Desativado', 'Ativado no Mês', 'Suspenso']
        df['Categoria'] = np.select(conditions, choices, default='Cheio')

        # --- LÓGICA DE CÁLCULO REFEITA ---
        dias_a_faturar = 0
        # Desativados: Fatura até o dia da desativação
        dias_a_faturar = np.where(df['Categoria'] == 'Desativado', (df['Data Desativação'].dt.day - df['Suspenso Dias Mes']), dias_a_faturar)
        # Ativados no Mês: Fatura do dia da ativação até o fim do mês
        dias_a_faturar = np.where(df['Categoria'] == 'Ativado no Mês', (dias_no_mes - df['Data Ativação'].dt.day + 1) - df['Suspenso Dias Mes'], dias_a_faturar)
        # Suspensos e Cheios: Fatura os dias ativos menos os dias suspensos
        dias_a_faturar = np.where(df['Categoria'].isin(['Suspenso', 'Cheio']), (df['Dias Ativos Mês'] - df['Suspenso Dias Mes']), dias_a_faturar)
        
        df['Dias a Faturar'] = dias_a_faturar.clip(lower=0)
        df['Valor a Faturar'] = (df['Valor Unitario'] / dias_no_mes) * df['Dias a Faturar']
        
        # Separa os DataFrames finais
        df_cheio = df[df['Categoria'] == 'Cheio'].copy()
        df_ativados = df[df['Categoria'] == 'Ativado no Mês'].copy()
        df_desativados = df[df['Categoria'] == 'Desativado'].copy()
        df_suspensos = df[df['Categoria'] == 'Suspenso'].copy()

        return nome_cliente, periodo_relatorio, df_cheio, df_ativados, df_desativados, df_suspensos, None

    except Exception as e:
        return None, None, None, None, None, None, f"Ocorreu um erro inesperado ao processar o arquivo: {e}"

@st.cache_data
def to_excel(df_cheio, df_ativados, df_desativados, df_suspensos):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_cheio.to_excel(writer, index=False, sheet_name='Faturamento Cheio')
        df_ativados.to_excel(writer, index=False, sheet_name='Proporcional - Ativados')
        df_desativados.to_excel(writer, index=False, sheet_name='Proporcional - Desativados')
        df_suspensos.to_excel(writer, index=False, sheet_name='Suspensos (Faturamento Prop.)')
    return output.getvalue()

def create_pdf_report(nome_cliente, periodo, totais, df_cheio, df_ativados, df_desativados, df_suspensos):
    # (O código desta função permanece o mesmo da versão anterior e não precisa ser alterado)
    pdf = PDF(orientation='P')
    pdf.set_top_margin(40)
    pdf.set_auto_page_break(auto=True, margin=40)
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, "Resumo do Faturamento", 0, 1, "C")
    pdf.ln(5)
    pdf.set_font("Arial", "", 12)
    pdf.cell(0, 8, f"Cliente: {nome_cliente}", 0, 1, "L")
    pdf.cell(0, 8, f"Período: {periodo}", 0, 1, "L")
    pdf.ln(5)
    pdf.set_font("Arial", "B", 9)
    table_width = pdf.w - pdf.l_margin - pdf.r_margin
    col_width = table_width / 5
    pdf.cell(col_width, 8, "Nº Fat. Cheio", 1, 0, "C")
    pdf.cell(col_width, 8, "Nº Fat. Proporcional", 1, 0, "C")
    pdf.cell(col_width, 8, "Nº Suspensos", 1, 0, "C")
    pdf.cell(col_width, 8, "Total GPRS", 1, 0, "C")
    pdf.cell(col_width, 8, "Total Satelitais", 1, 1, "C")
    pdf.set_font("Arial", "", 9)
    pdf.cell(col_width, 8, str(totais['terminais_cheio']), 1, 0, "C")
    pdf.cell(col_width, 8, str(totais['terminais_proporcional']), 1, 0, "C")
    pdf.cell(col_width, 8, str(totais['terminais_suspensos']), 1, 0, "C")
    pdf.cell(col_width, 8, str(totais['terminais_gprs']), 1, 0, "C")
    pdf.cell(col_width, 8, str(totais['terminais_satelitais']), 1, 1, "C")
    pdf.ln(5)
    pdf.set_font("Arial", "B", 11)
    pdf.cell(table_width / 2, 8, "Faturamento (Cheio)", 1, 0, "C")
    pdf.cell(table_width / 2, 8, "Faturamento (Proporcional)", 1, 1, "C")
    pdf.set_font("Arial", "", 11)
    pdf.cell(table_width / 2, 8, f"R$ {totais['cheio']:,.2f}", 1, 0, "C")
    pdf.cell(table_width / 2, 8, f"R$ {totais['proporcional']:,.2f}", 1, 1, "C")
    pdf.set_font("Arial", "B", 11)
    pdf.cell(0, 10, f"FATURAMENTO TOTAL: R$ {totais['geral']:,.2f}", 1, 1, "C")
    pdf.ln(10)
    def draw_table(title, df, col_widths, available_cols, header_map):
        if not df.empty:
            pdf.set_font("Arial", "B", 12)
            pdf.cell(0, 10, title, 0, 1, "L")
            pdf.set_font("Arial", "B", 7)
            header = [h for h in available_cols if h in df.columns]
            header_row_height = 8
            y_start = pdf.get_y()
            x_start = pdf.get_x()
            for h in header:
                width = col_widths.get(h, 20)
                pdf.cell(width, header_row_height, '', border=1, ln=0, align='C')
            pdf.set_xy(x_start, y_start) 
            current_x = x_start
            for h in header:
                width = col_widths.get(h, 20)
                header_text = header_map.get(h, h)
                pdf.set_x(current_x)
                pdf.multi_cell(width, 4, header_text, border=0, align='C')
                current_x += width
                pdf.set_y(y_start)
            pdf.set_y(y_start + header_row_height)
            pdf.set_font("Arial", "", 6)
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
    header_map = {'Nº Equipamento': 'Nº\nEquipamento', 'Valor a Faturar': 'Valor a\nFaturar', 'Data Ativação': 'Data\nAtivação', 'Data Desativação': 'Data\nDesativação', 'Dias Ativos Mês': 'Dias\nAtivos', 'Suspenso Dias Mes': 'Dias\nSuspensos', 'Dias a Faturar': 'Dias a\nFaturar', 'Valor Unitario': 'Valor\nUnitário'}
    widths_cheio = {'Terminal': 45, 'Nº Equipamento': 45, 'Placa': 40, 'Tipo': 25, 'Valor a Faturar': 35}
    cols_cheio = list(widths_cheio.keys())
    draw_table("Detalhamento do Faturamento Cheio", df_cheio, widths_cheio, cols_cheio, header_map)
    widths_proporcional = {'Terminal': 22, 'Nº Equipamento': 22, 'Placa': 22, 'Tipo': 15, 'Data Ativação': 18, 'Data Desativação': 18, 'Dias Ativos Mês': 15, 'Suspenso Dias Mes': 18, 'Dias a Faturar': 15, 'Valor Unitario': 20, 'Valor a Faturar': 20}
    cols_ativados = ['Terminal', 'Nº Equipamento', 'Placa', 'Tipo', 'Data Ativação', 'Dias Ativos Mês', 'Suspenso Dias Mes', 'Dias a Faturar', 'Valor Unitario', 'Valor a Faturar']
    draw_table("Detalhamento Proporcional (Ativações no Mês)", df_ativados, widths_proporcional, cols_ativados, header_map)
    cols_desativados = ['Terminal', 'Nº Equipamento', 'Placa', 'Tipo', 'Data Desativação', 'Dias Ativos Mês', 'Suspenso Dias Mes', 'Dias a Faturar', 'Valor Unitario', 'Valor a Faturar']
    draw_table("Detalhamento Proporcional (Desativações no Mês)", df_desativados, widths_proporcional, cols_desativados, header_map)
    cols_suspensos = ['Terminal', 'Nº Equipamento', 'Placa', 'Tipo', 'Data Ativação', 'Dias Ativos Mês', 'Suspenso Dias Mes', 'Dias a Faturar', 'Valor Unitario', 'Valor a Faturar']
    draw_table("Detalhamento dos Terminais Suspensos (Faturamento Prop.)", df_suspensos, widths_proporcional, cols_suspensos, header_map)
    return bytes(pdf.output(dest='S').encode('latin-1'))

# --- 3. INTERFACE DA PÁGINA ---
st.image("imgs/logo.png", width=250, use_column_width='auto')
st.markdown("<h1 style='text-align: center; color: #006494;'>Verdio Assistente de Faturamento</h1>", unsafe_allow_html=True)
st.markdown("---")

# --- 4. INPUTS DE CONFIGURAÇÃO ---
st.sidebar.header("Valores de Faturamento")
pricing_config = umdb.get_pricing_config()
if 'gprs_to_apply' in st.session_state:
    default_gprs = st.session_state.pop('gprs_to_apply')
    default_satelital = st.session_state.pop('satelital_to_apply')
else:
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
        nome_cliente, periodo_relatorio, df_cheio, df_ativados, df_desativados, df_suspensos, error_message = processar_planilha_faturamento(file_bytes, valor_gprs, valor_satelital)

        if error_message:
            st.error(error_message)
        elif df_cheio is not None:
            last_billing = umdb.get_last_billing_for_client(nome_cliente)
            if last_billing:
                last_gprs, last_satelital = last_billing.get("valor_unitario_gprs", valor_gprs), last_billing.get("valor_unitario_satelital", valor_satelital)
                if last_gprs != valor_gprs or last_satelital != valor_satelital:
                    st.info(f"💡 Encontramos os valores utilizados no último faturamento para **{nome_cliente}**.")
                    c1, c2, c3 = st.columns([2,2,3])
                    c1.metric("Último Valor GPRS", f"R$ {last_gprs:.2f}"); c2.metric("Último Valor Satelital", f"R$ {last_satelital:.2f}")
                    if c3.button("Aplicar valores e recalcular"):
                        st.session_state.update({'gprs_to_apply': last_gprs, 'satelital_to_apply': last_satelital}); st.rerun()

            total_cheio = df_cheio['Valor a Faturar'].sum()
            total_ativados = df_ativados['Valor a Faturar'].sum()
            total_desativados = df_desativados['Valor a Faturar'].sum()
            total_suspensos = df_suspensos['Valor a Faturar'].sum()
            total_proporcional = total_ativados + total_desativados + total_suspensos
            total_geral = total_cheio + total_proporcional

            st.header("Resumo do Faturamento")
            st.subheader(f"Cliente: {nome_cliente}"); st.caption(f"Período: {periodo_relatorio}")

            df_total = pd.concat([df_cheio, df_ativados, df_desativados, df_suspensos])
            num_prop = len(df_ativados) + len(df_desativados)

            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Nº Fat. Cheio", len(df_cheio)); c2.metric("Nº Fat. Proporcional", num_prop); c3.metric("Nº Suspensos", len(df_suspensos))
            c4.metric("Total GPRS", len(df_total[df_total['Tipo'] == 'GPRS'])); c5.metric("Total Satelitais", len(df_total[df_total['Tipo'] == 'Satelital']))
            
            c1, c2, c3 = st.columns(3)
            c1.success(f"**Faturamento (Cheio):** R$ {total_cheio:,.2f}"); c2.warning(f"**Faturamento (Proporcional):** R$ {total_proporcional:,.2f}"); c3.info(f"**FATURAMENTO TOTAL:** R$ {total_geral:,.2f}")
            
            st.markdown("---"); st.subheader("Ações Finais")
            
            excel_data = to_excel(df_cheio, df_ativados, df_desativados, df_suspensos)
            log_data = {"cliente": nome_cliente, "periodo_relatorio": periodo_relatorio, "valor_total": total_geral, "terminais_cheio": len(df_cheio), "terminais_proporcional": num_prop, "terminais_suspensos": len(df_suspensos), "terminais_gprs": len(df_total[df_total['Tipo'] == 'GPRS']), "terminais_satelitais": len(df_total[df_total['Tipo'] == 'Satelital']), "valor_unitario_gprs": valor_gprs, "valor_unitario_satelital": valor_satelital}
            pdf_data = create_pdf_report(nome_cliente, periodo_relatorio, {"cheio": total_cheio, "proporcional": total_proporcional, "geral": total_geral, "terminais_cheio": len(df_cheio), "terminais_proporcional": num_prop, "terminais_suspensos": len(df_suspensos), "terminais_gprs": len(df_total[df_total['Tipo'] == 'GPRS']), "terminais_satelitais": len(df_total[df_total['Tipo'] == 'Satelital'])}, df_cheio, df_ativados, df_desativados, df_suspensos)
            
            c1, c2 = st.columns(2)
            c1.download_button("📥 Exportar Excel e Salvar Histórico", excel_data, f"Faturamento_{nome_cliente.replace(' ', '_')}_{datetime.now().strftime('%Y-%m')}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", on_click=umdb.log_faturamento, args=(log_data,))
            c2.download_button("📄 Exportar Resumo em PDF", pdf_data, f"Resumo_Faturamento_{nome_cliente.replace(' ', '_')}_{datetime.now().strftime('%Y-%m')}.pdf", "application/pdf", on_click=umdb.log_faturamento, args=(log_data,))

            st.markdown("---")
            cols_to_show = ['Terminal', 'Nº Equipamento', 'Placa', 'Tipo', 'Data Ativação', 'Dias Ativos Mês', 'Suspenso Dias Mes', 'Dias a Faturar', 'Valor Unitario', 'Valor a Faturar']
            
            with st.expander("Detalhamento do Faturamento Cheio"):
                st.dataframe(df_cheio[['Terminal', 'Nº Equipamento', 'Placa', 'Tipo', 'Dias a Faturar', 'Valor a Faturar']], use_container_width=True, hide_index=True)
            with st.expander("Detalhamento Proporcional (Ativações no Mês)"):
                st.dataframe(df_ativados[cols_to_show], use_container_width=True, hide_index=True)
            with st.expander("Detalhamento Proporcional (Desativações no Mês)"):
                st.dataframe(df_desativados[cols_to_show], use_container_width=True, hide_index=True)
            with st.expander("Detalhamento dos Terminais Suspensos (Faturamento Proporcional)"):
                st.dataframe(df_suspensos[cols_to_show], use_container_width=True, hide_index=True)
else:
    st.info("Aguardando o carregamento do relatório para iniciar a análise.")
