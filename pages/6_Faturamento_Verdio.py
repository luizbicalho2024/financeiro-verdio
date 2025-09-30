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

        uploaded_file = io.BytesIO(file_bytes)
        df = pd.read_excel(uploaded_file, header=11, engine='openpyxl', dtype={'Equipamento': str})
        df = df.rename(columns={'Suspenso Dias Mês': 'Suspenso Dias Mes', 'Equipamento': 'Nº Equipamento'})

        required_cols = ['Cliente', 'Terminal', 'Data Ativação', 'Data Desativação', 'Dias Ativos Mês', 'Suspenso Dias Mes', 'Nº Equipamento', 'Condição']
        if not all(col in df.columns for col in required_cols):
            return None, None, None, None, None, None, "Erro de Colunas: Verifique o cabeçalho na linha 12."

        nome_cliente = str(df['Cliente'].dropna().iloc[0]).strip() if not df.empty and 'Cliente' in df.columns else "Cliente não identificado"

        df.dropna(subset=['Terminal'], inplace=True)
        df['Terminal'] = df['Terminal'].astype(str).str.strip()
        df['Data Ativação'] = pd.to_datetime(df['Data Ativação'], errors='coerce', dayfirst=True)
        df['Data Desativação'] = pd.to_datetime(df['Data Desativação'], errors='coerce', dayfirst=True)
        df['Dias Ativos Mês'] = pd.to_numeric(df['Dias Ativos Mês'], errors='coerce').fillna(0)
        df['Suspenso Dias Mes'] = pd.to_numeric(df['Suspenso Dias Mes'], errors='coerce').fillna(0)

        if not df[df['Data Desativação'].notna()].empty:
            report_date = df[df['Data Desativação'].notna()]['Data Desativação'].iloc[0]
        elif not df[df['Data Ativação'].notna()].empty:
            report_date = df[df['Data Ativação'].notna()]['Data Ativação'].iloc[0]
        else:
            report_date = datetime.now()
        
        mes_ingles = report_date.strftime("%B")
        mes_portugues = meses_pt.get(mes_ingles, mes_ingles)
        ano = report_date.strftime("%Y")
        periodo_relatorio = f"{mes_portugues} de {ano}"

        report_month = report_date.month
        report_year = report_date.year
        dias_no_mes = pd.Timestamp(year=report_year, month=report_month, day=1).days_in_month

        df['Tipo'] = df['Nº Equipamento'].apply(lambda x: 'Satelital' if len(str(x).strip()) == 8 else 'GPRS')
        df['Valor Unitario'] = df['Tipo'].apply(lambda x: valor_satelital if x == 'Satelital' else valor_gprs)

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
        
        df_suspensos = df_restantes[df_restantes['Condição'].str.strip() == 'Suspenso'].copy()
        if not df_suspensos.empty:
            df_suspensos['Dias a Faturar'] = (df_suspensos['Dias Ativos Mês'] - df_suspensos['Suspenso Dias Mes']).clip(lower=0)
            df_suspensos['Valor a Faturar'] = (df_suspensos['Valor Unitario'] / dias_no_mes) * df_suspensos['Dias a Faturar']

        indices_para_remover = df_ativados.index.union(df_suspensos.index)
        df_cheio = df_restantes.drop(indices_para_remover).copy()
        if not df_cheio.empty:
            df_cheio['Dias a Faturar'] = (df_cheio['Dias Ativos Mês'] - df_cheio['Suspenso Dias Mes']).clip(lower=0)
            df_cheio['Valor a Faturar'] = (df_cheio['Valor Unitario'] / dias_no_mes) * df_cheio['Dias a Faturar']

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

    header_map = {
        'Nº Equipamento': 'Nº\nEquipamento',
        'Valor a Faturar': 'Valor a\nFaturar',
        'Data Ativação': 'Data\nAtivação',
        'Data Desativação': 'Data\nDesativação',
        'Dias Ativos Mês': 'Dias\nAtivos',
        'Suspenso Dias Mes': 'Dias\nSuspensos',
        'Dias a Faturar': 'Dias a\nFaturar',
        'Valor Unitario': 'Valor\nUnitário'
    }

    widths_cheio = {'Terminal': 45, 'Nº Equipamento': 45, 'Placa': 40, 'Tipo': 25, 'Valor a Faturar': 35}
    cols_cheio = list(widths_cheio.keys())
    draw_table("Detalhamento do Faturamento Cheio", df_cheio, widths_cheio, cols_cheio, header_map)
    
    widths_proporcional = {
        'Terminal': 22, 'Nº Equipamento': 22, 'Placa': 22, 'Tipo': 15, 'Data Ativação': 18, 
        'Data Desativação': 18, 'Dias Ativos Mês': 15, 'Suspenso Dias Mes': 18, 
        'Dias a Faturar': 15, 'Valor Unitario': 20, 'Valor a Faturar': 20
    }
    cols_ativados = ['Terminal', 'Nº Equipamento', 'Placa', 'Tipo', 'Data Ativação', 'Dias Ativos Mês', 'Suspenso Dias Mes', 'Dias a Faturar', 'Valor Unitario', 'Valor a Faturar']
    draw_table("Detalhamento Proporcional (Ativações no Mês)", df_ativados, widths_proporcional, cols_ativados, header_map)
    
    cols_desativados = ['Terminal', 'Nº Equipamento', 'Placa', 'Tipo', 'Data Desativação', 'Dias Ativos Mês', 'Suspenso Dias Mes', 'Dias a Faturar', 'Valor Unitario', 'Valor a Faturar']
    draw_table("Detalhamento Proporcional (Desativações no Mês)", df_desativados, widths_proporcional, cols_desativados, header_map)

    # CORREÇÃO: Usa as larguras da tabela proporcional para a tabela de suspensos
    cols_suspensos = ['Terminal', 'Nº Equipamento', 'Placa', 'Tipo', 'Data Ativação', 'Dias Ativos Mês', 'Suspenso Dias Mes', 'Dias a Faturar', 'Valor Unitario', 'Valor a Faturar']
    draw_table("Detalhamento dos Terminais Suspensos (Faturamento Prop.)", df_suspensos, widths_proporcional, cols_suspensos, header_map)
    
    return bytes(pdf.output(dest='S').encode('latin-1'))

# --- 3. INTERFACE DA PÁGINA ---
try:
    st.image("imgs/logo.png", width=250)
except: pass

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
                last_gprs = last_billing.get("valor_unitario_gprs", valor_gprs)
                last_satelital = last_billing.get("valor_unitario_satelital", valor_satelital)

                if last_gprs != valor_gprs or last_satelital != valor_satelital:
                    st.info(f"💡 Encontramos os valores utilizados no último faturamento para **{nome_cliente}**.")
                    col1, col2, col3 = st.columns([2,2,3])
                    col1.metric("Último Valor GPRS", f"R$ {last_gprs:.2f}")
                    col2.metric("Último Valor Satelital", f"R$ {last_satelital:.2f}")
                    with col3:
                        st.write("") 
                        if st.button("Aplicar valores e recalcular"):
                            st.session_state['gprs_to_apply'] = last_gprs
                            st.session_state['satelital_to_apply'] = last_satelital
                            st.rerun()

            total_faturamento_cheio = df_cheio['Valor a Faturar'].sum() if not df_cheio.empty else 0
            total_faturamento_ativados = df_ativados['Valor a Faturar'].sum() if not df_ativados.empty else 0
            total_faturamento_desativados = df_desativados['Valor a Faturar'].sum() if not df_desativados.empty else 0
            total_faturamento_suspensos = df_suspensos['Valor a Faturar'].sum() if not df_suspensos.empty else 0
            
            faturamento_proporcional_total = total_faturamento_ativados + total_faturamento_desativados + total_faturamento_suspensos
            faturamento_total_geral = total_faturamento_cheio + faturamento_proporcional_total

            st.header("Resumo do Faturamento")
            st.subheader(f"Cliente: {nome_cliente}")
            st.caption(f"Período: {periodo_relatorio}")

            df_total = pd.concat([df_cheio, df_ativados, df_desativados, df_suspensos])
            total_gprs = len(df_total[df_total['Tipo'] == 'GPRS'])
            total_satelital = len(df_total[df_total['Tipo'] == 'Satelital'])

            col1, col2, col3, col4, col5 = st.columns(5)
            col1.metric("Nº Fat. Cheio", value=len(df_cheio))
            col2.metric("Nº Fat. Proporcional", value=len(df_ativados) + len(df_desativados))
            col3.metric("Nº Suspensos", value=len(df_suspensos))
            col4.metric("Total GPRS", value=total_gprs)
            col5.metric("Total Satelitais", value=total_satelital)

            col_a, col_b, col_c = st.columns(3)
            col_a.success(f"**Faturamento (Cheio):** R$ {total_faturamento_cheio:,.2f}")
            col_b.warning(f"**Faturamento (Proporcional):** R$ {faturamento_proporcional_total:,.2f}")
            col_c.info(f"**FATURAMENTO TOTAL:** R$ {faturamento_total_geral:,.2f}")

            st.markdown("---")

            st.subheader("Ações Finais")
            excel_data = to_excel(df_cheio, df_ativados, df_desativados, df_suspensos)
            totais_pdf = {
                "cheio": total_faturamento_cheio, "proporcional": faturamento_proporcional_total, "geral": faturamento_total_geral,
                "terminais_cheio": len(df_cheio), "terminais_proporcional": len(df_ativados) + len(df_desativados) + len(df_suspensos),
                "terminais_suspensos": len(df_suspensos), "terminais_gprs": total_gprs, "terminais_satelitais": total_satelital
            }
            pdf_data = create_pdf_report(nome_cliente, periodo_relatorio, totais_pdf, df_cheio, df_ativados, df_desativados, df_suspensos)
            faturamento_data_log = {
                "cliente": nome_cliente, "periodo_relatorio": periodo_relatorio,
                "valor_total": faturamento_total_geral, "terminais_cheio": len(df_cheio),
                "terminais_proporcional": len(df_ativados) + len(df_desativados) + len(df_suspensos),
                "terminais_suspensos": len(df_suspensos),
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
            
            with st.expander("Detalhamento dos Terminais Suspensos (Faturamento Proporcional)"):
                if not df_suspensos.empty:
                    st.dataframe(df_suspensos[['Terminal', 'Nº Equipamento', 'Placa', 'Tipo', 'Data Ativação', 'Dias Ativos Mês', 'Suspenso Dias Mes', 'Dias a Faturar', 'Valor Unitario', 'Valor a Faturar']], use_container_width=True, hide_index=True)
                else:
                    st.info("Nenhum terminal suspenso neste período.")

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

else:
    st.info("Aguardando o carregamento do relatório para iniciar a análise.")
