import sys
import os
import re
import io
import streamlit as st
import pandas as pd
from datetime import datetime
from fpdf import FPDF
import numpy as np

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import user_management_db as umdb
import auth_functions as af

# --- PDF CLASS ---
class PDF(FPDF):
    def header(self):
        try:
            self.image("imgs/header1.png", x=self.l_margin, y=8, w=self.w - self.l_margin - self.r_margin)
        except:
            self.set_font("Arial", "B", 20); self.cell(0, 10, "Uzzipay Soluções", 0, 1, "L"); self.ln(15)
    def footer(self):
        try:
            self.set_y(-35); self.image("imgs/footer1.png", x=self.l_margin, y=self.get_y(), w=self.w - self.l_margin - self.r_margin)
        except:
            self.set_y(-15); self.set_font("Arial", "I", 8); self.cell(0, 10, f"Pág {self.page_no()}", 0, 0, "C")

# --- LÓGICA DE NEGÓCIO ---
@st.cache_data
def processar_planilha_faturamento(file_bytes, tracker_inventory, prices):
    try:
        meses_pt = {"January": "Janeiro", "February": "Fevereiro", "March": "Março", "April": "Abril", "May": "Maio", "June": "Junho", "July": "Julho", "August": "Agosto", "September": "Setembro", "October": "Outubro", "November": "Novembro", "December": "Dezembro"}
        try:
            periodo_df = pd.read_excel(io.BytesIO(file_bytes), header=None, sheet_name=0)
            periodo_str = periodo_df.iloc[8, 8]
            match = re.search(r'(\d{2}[-/]\d{2}[-/]\d{4})', str(periodo_str))
            if match:
                start_date_str = match.group(1).replace('-', '/')
                report_date = pd.to_datetime(start_date_str, dayfirst=True)
            else: raise ValueError("Formato de data não encontrado")
        except:
            report_date = datetime.now()

        df = pd.read_excel(io.BytesIO(file_bytes), header=11, engine='openpyxl', dtype={'Equipamento': str})
        df = df.rename(columns={'Suspenso Dias Mês': 'Suspenso Dias Mes', 'Equipamento': 'Nº Equipamento'})
        df.dropna(subset=['Terminal'], inplace=True)

        nome_cliente = str(df['Cliente'].dropna().iloc[0]).strip() if not df['Cliente'].dropna().empty else "Cliente"
        
        for col in ['Data Ativação', 'Data Desativação']: df[col] = pd.to_datetime(df[col], errors='coerce', dayfirst=True)
        for col in ['Dias Ativos Mês', 'Suspenso Dias Mes']: df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

        report_month, report_year = report_date.month, report_date.year
        dias_no_mes = pd.Timestamp(year=report_year, month=report_month, day=1).days_in_month
        periodo_relatorio = f"{meses_pt.get(report_date.strftime('%B'), report_date.strftime('%B'))} de {report_year}"
        
        df_inv = pd.DataFrame(tracker_inventory)
        df_merged = pd.merge(df, df_inv, on='Nº Equipamento', how='left')
        not_found = df_merged[df_merged['Tipo'].isna()]['Nº Equipamento'].tolist()
        df_merged['Valor Unitario'] = df_merged['Tipo'].map(prices).fillna(0)

        conditions = [
            (df_merged['Data Desativação'].notna()),
            (df_merged['Data Ativação'].dt.month == report_month) & (df_merged['Data Ativação'].dt.year == report_year),
            (df_merged['Condição'].str.strip() == 'Suspenso')
        ]
        choices = ['Desativado', 'Ativado no Mês', 'Suspenso']
        df_merged['Categoria'] = np.select(conditions, choices, default='Cheio')
        
        dias = 0
        dias = np.where(df_merged['Categoria'] == 'Desativado', df_merged['Data Desativação'].dt.day - df_merged['Suspenso Dias Mes'], dias)
        dias = np.where(df_merged['Categoria'] == 'Ativado no Mês', (dias_no_mes - df_merged['Data Ativação'].dt.day + 1) - df_merged['Suspenso Dias Mes'], dias)
        dias = np.where(df_merged['Categoria'].isin(['Suspenso', 'Cheio']), df_merged['Dias Ativos Mês'] - df_merged['Suspenso Dias Mes'], dias)
        
        df_merged['Dias a Faturar'] = np.clip(dias, 0, None)
        df_merged['Valor a Faturar'] = (df_merged['Valor Unitario'] / dias_no_mes) * df_merged['Dias a Faturar']
        
        return nome_cliente, periodo_relatorio, df_merged, not_found, None
    except Exception as e:
        return None, None, None, None, str(e)

def to_excel(dfs):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as w:
        for name, df in dfs.items(): df.to_excel(w, index=False, sheet_name=name)
    return output.getvalue()

def create_pdf_report(nome_cliente, periodo, totais, dfs):
    pdf = PDF('P'); pdf.set_top_margin(40); pdf.set_auto_page_break(True, 45); pdf.add_page()
    pdf.set_font("Arial", "B", 16); pdf.cell(0, 10, "Resumo do Faturamento", 0, 1, "C"); pdf.ln(5)
    pdf.set_font("Arial", "", 12); pdf.cell(0, 8, f"Cliente: {nome_cliente}", 0, 1, "L"); pdf.cell(0, 8, f"Período: {periodo}", 0, 1, "L"); pdf.ln(5)
    
    # Totais
    w = pdf.w - pdf.l_margin - pdf.r_margin; col = w / 5
    pdf.set_font("Arial", "B", 9); headers = ["Nº Fat. Cheio", "Nº Proporcional", "Nº Suspensos", "Total GPRS", "Total Satelitais"]
    for h in headers: pdf.cell(col, 8, h, 1, 0, "C")
    pdf.ln(); pdf.set_font("Arial", "", 9)
    vals = [totais['terminais_cheio'], totais['terminais_proporcional'], totais['terminais_suspensos'], totais['terminais_gprs'], totais['terminais_satelitais']]
    for v in vals: pdf.cell(col, 8, str(v), 1, 0, "C")
    pdf.ln(); pdf.ln(5)

    pdf.set_font("Arial", "B", 11); pdf.cell(w/2, 8, "Faturamento (Cheio)", 1, 0, "C"); pdf.cell(w/2, 8, "Faturamento (Proporcional)", 1, 1, "C")
    pdf.set_font("Arial", "", 11); pdf.cell(w/2, 8, f"R$ {totais['cheio']:,.2f}", 1, 0, "C"); pdf.cell(w/2, 8, f"R$ {totais['proporcional']:,.2f}", 1, 1, "C")
    pdf.ln(5); pdf.set_font("Arial", "B", 11); pdf.cell(0, 10, f"FATURAMENTO TOTAL: R$ {totais['geral']:,.2f}", 1, 1, "C"); pdf.ln(10)

    def draw_table(title, df, widths):
        if df.empty: return
        pdf.set_font("Arial", "B", 12); pdf.cell(0, 10, title, 0, 1, "L")
        if pdf.get_y() > pdf.h - 60: pdf.add_page()
        
        pdf.set_font("Arial", "B", 7); cols = list(widths.keys()); h_map = {'Nº Equipamento': 'Nº\nEquipamento', 'Valor a Faturar': 'Valor a\nFaturar', 'Data Ativação': 'Data\nAtivação', 'Data Desativação': 'Data\nDesativação', 'Dias Ativos Mês': 'Dias\nAtivos', 'Suspenso Dias Mes': 'Dias\nSuspensos', 'Dias a Faturar': 'Dias a\nFaturar', 'Valor Unitario': 'Valor\nUnitário'}
        y = pdf.get_y(); x = pdf.get_x()
        
        for c in cols: pdf.cell(widths[c], 8, '', 1, 0, 'C')
        pdf.set_xy(x, y); curr_x = x
        for c in cols:
            pdf.set_x(curr_x); pdf.multi_cell(widths[c], 4, h_map.get(c, c), 0, 'C'); curr_x += widths[c]; pdf.set_y(y)
        pdf.set_y(y + 8); pdf.set_font("Arial", "", 6)
        
        for _, row in df.iterrows():
            for c in cols:
                txt = str(row.get(c, ''))
                if 'Valor' in c and isinstance(row.get(c), (int, float)): txt = f"R$ {row[c]:,.2f}"
                elif isinstance(row.get(c), datetime): txt = row[c].strftime('%d/%m/%Y')
                pdf.cell(widths[c], 6, txt, 1, 0, 'C')
            pdf.ln()
        pdf.ln(5)

    # Tabelas
    w_cheio = {'Terminal': 38, 'Nº Equipamento': 38, 'Placa': 25, 'Modelo': 34, 'Tipo': 20, 'Valor a Faturar': 35}
    draw_table("Detalhamento Cheio", dfs['cheio'], w_cheio)
    w_prop = {'Terminal': 19, 'Nº Equipamento': 20, 'Modelo': 18, 'Tipo': 14, 'Data Ativação': 17, 'Data Desativação': 17, 'Dias Ativos Mês': 13, 'Suspenso Dias Mes': 16, 'Dias a Faturar': 13, 'Valor Unitario': 19, 'Valor a Faturar': 19}
    draw_table("Ativações no Mês", dfs['ativados'], w_prop)
    draw_table("Desativações no Mês", dfs['desativados'], w_prop)
    draw_table("Suspensos", dfs['suspensos'], w_prop)
    
    return bytes(pdf.output(dest='S').encode('latin-1', errors='replace'))

# --- APP UX ---
st.set_page_config(layout="wide", page_title="Faturamento", page_icon="📑")
if "user_info" not in st.session_state: st.stop()

af.render_sidebar()
st.title("📑 Gerador de Faturamento")

st.info("Passo 1: Carregar Planilha do Sistema")
file = st.file_uploader("", type=['xlsx'], label_visibility="collapsed")
if not file: st.stop()

st.info("Passo 2: Configurar Preços Aplicados")
pricing_config = umdb.get_pricing_config().get("TIPO_EQUIPAMENTO", {})
defaults = st.session_state.get('prices_to_apply', pricing_config)
prices = {}
cols = st.columns(4)
i = 0
for k in sorted(pricing_config.keys()):
    val = defaults.get(k, 0.0)
    if isinstance(val, dict): val = val.get("price1", 0.0)
    with cols[i % 4]: prices[k] = st.number_input(f"Preço {k}", value=float(val), format="%.2f")
    i += 1

st.divider()
st.subheader("Processamento")

inv = umdb.get_tracker_inventory()
if not inv: st.error("Estoque vazio!"); st.stop()

nome, periodo, df_final, not_found, err = processar_planilha_faturamento(file.getvalue(), inv, prices)

if err: st.error(err); st.stop()
if not_found: st.warning(f"⚠️ {len(not_found)} Equipamentos não encontrados no estoque."); st.json(not_found)

# Separação
df_cheio = df_final[df_final['Categoria'] == 'Cheio'].copy()
df_ativ = df_final[df_final['Categoria'] == 'Ativado no Mês'].copy()
df_desat = df_final[df_final['Categoria'] == 'Desativado'].copy()
df_susp = df_final[df_final['Categoria'] == 'Suspenso'].copy()

# Totais
total_cheio = df_cheio['Valor a Faturar'].sum()
total_prop = df_ativ['Valor a Faturar'].sum() + df_desat['Valor a Faturar'].sum() + df_susp['Valor a Faturar'].sum()
total_geral = total_cheio + total_prop

# Exibição
st.success(f"Faturamento Processado: {nome} | {periodo}")
k1, k2, k3 = st.columns(3)
k1.metric("Cheio", f"R$ {total_cheio:,.2f}")
k2.metric("Proporcional", f"R$ {total_prop:,.2f}")
k3.metric("TOTAL GERAL", f"R$ {total_geral:,.2f}")

# Detalhes e Exportação
details_list = df_final[['Terminal', 'Nº Equipamento', 'Modelo', 'Tipo', 'Categoria', 'Valor Unitario', 'Valor a Faturar']].to_dict(orient='records')
log_data = {
    "cliente": nome, "periodo_relatorio": periodo, "valor_total": total_geral,
    "terminais_cheio": len(df_cheio), "terminais_proporcional": len(df_ativ)+len(df_desat), 
    "terminais_suspensos": len(df_susp), "terminais_gprs": len(df_final[df_final['Tipo']=='GPRS']), 
    "terminais_satelitais": len(df_final[df_final['Tipo']=='SATELITE']),
    "valor_unitario_gprs": prices.get("GPRS", 0), "valor_unitario_satelital": prices.get("SATELITE", 0)
}

dfs_dict = {'Faturamento Cheio': df_cheio, 'Ativados': df_ativ, 'Desativados': df_desat, 'Suspensos': df_susp}
xls = to_excel(dfs_dict)
pdf = create_pdf_report(nome, periodo, {"cheio": total_cheio, "proporcional": total_prop, "geral": total_geral, "terminais_cheio": len(df_cheio), "terminais_proporcional": len(df_ativ)+len(df_desat), "terminais_suspensos": len(df_susp), "terminais_gprs": len(df_final[df_final['Tipo']=='GPRS']), "terminais_satelitais": len(df_final[df_final['Tipo']=='SATELITE'])}, {'cheio': df_cheio, 'ativados': df_ativ, 'desativados': df_desat, 'suspensos': df_susp})

c1, c2 = st.columns(2)
c1.download_button("📥 Excel + Salvar Histórico", xls, f"Faturamento_{nome}.xlsx", on_click=umdb.log_faturamento, args=(log_data, details_list))
c2.download_button("📄 PDF + Salvar Histórico", pdf, f"Faturamento_{nome}.pdf", on_click=umdb.log_faturamento, args=(log_data, details_list))

with st.expander("Visualizar Tabelas"):
    st.write("Cheio"); st.dataframe(df_cheio, use_container_width=True)
    st.write("Proporcional"); st.dataframe(df_ativ, use_container_width=True)
