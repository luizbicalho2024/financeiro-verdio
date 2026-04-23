# pages/10_Faturamento_Lote.py
import sys
import os
import re
import zipfile
import io
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import streamlit as st
import pandas as pd
from datetime import datetime
import user_management_db as umdb
from fpdf import FPDF
import numpy as np

# --- CLASSE PARA GERAR PDF COM IDENTIDADE VISUAL ---
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
st.set_page_config(layout="wide", page_title="Faturamento em Lote", page_icon="imgs/v-c.png")
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
def create_pdf_report(nome_cliente, periodo, totais, df_cheio, df_ativados, df_desativados, df_suspensos):
    pdf = PDF(orientation='P')
    pdf.set_top_margin(40)
    pdf.set_auto_page_break(auto=True, margin=45)
    pdf.add_page()
    
    pdf.set_font("Arial", "B", 16); pdf.cell(0, 10, "Resumo do Faturamento", 0, 1, "C"); pdf.ln(5)
    pdf.set_font("Arial", "", 12); pdf.cell(0, 8, f"Cliente: {nome_cliente}", 0, 1, "L"); pdf.cell(0, 8, f"Período: {periodo}", 0, 1, "L"); pdf.ln(5)
    
    pdf.set_font("Arial", "B", 9)
    table_width = pdf.w - pdf.l_margin - pdf.r_margin
    col_width = table_width / 5
    pdf.cell(col_width, 8, "Nº Fat. Cheio", 1, 0, "C"); pdf.cell(col_width, 8, "Nº Fat. Proporcional", 1, 0, "C"); pdf.cell(col_width, 8, "Nº Suspensos", 1, 0, "C")
    pdf.cell(col_width, 8, "Total GPRS", 1, 0, "C"); pdf.cell(col_width, 8, "Total Satelitais", 1, 1, "C")
    
    pdf.set_font("Arial", "", 9)
    pdf.cell(col_width, 8, str(totais['terminais_cheio']), 1, 0, "C"); pdf.cell(col_width, 8, str(totais['terminais_proporcional']), 1, 0, "C"); pdf.cell(col_width, 8, str(totais['terminais_suspensos']), 1, 0, "C")
    pdf.cell(col_width, 8, str(totais['terminais_gprs']), 1, 0, "C"); pdf.cell(col_width, 8, str(totais['terminais_satelitais']), 1, 1, "C"); pdf.ln(5)
    
    pdf.set_font("Arial", "B", 11); pdf.cell(table_width / 2, 8, "Faturamento (Cheio)", 1, 0, "C"); pdf.cell(table_width / 2, 8, "Faturamento (Proporcional)", 1, 1, "C")
    pdf.set_font("Arial", "", 11); pdf.cell(table_width / 2, 8, f"R$ {totais['cheio']:,.2f}", 1, 0, "C"); pdf.cell(table_width / 2, 8, f"R$ {totais['proporcional']:,.2f}", 1, 1, "C")
    pdf.set_font("Arial", "B", 11); pdf.cell(0, 10, f"FATURAMENTO TOTAL: R$ {totais['geral']:,.2f}", 1, 1, "C"); pdf.ln(10)
    
    def draw_table(title, df, col_widths, available_cols, header_map):
        if not df.empty:
            pdf.set_font("Arial", "B", 12)
            if pdf.get_y() > pdf.h - 60: pdf.add_page()
            
            pdf.cell(0, 10, title, 0, 1, "L"); pdf.set_font("Arial", "B", 7)
            header = [h for h in available_cols if h in df.columns]
            header_row_height = 8; y_start = pdf.get_y(); x_start = pdf.get_x()
            
            for h in header: pdf.cell(col_widths.get(h, 20), header_row_height, '', border=1, ln=0, align='C')
            
            pdf.set_xy(x_start, y_start); current_x = x_start
            for h in header:
                width = col_widths.get(h, 20); header_text = header_map.get(h, h)
                pdf.set_x(current_x); pdf.multi_cell(width, 4, header_text, border=0, align='C'); current_x += width; pdf.set_y(y_start)
            
            pdf.set_y(y_start + header_row_height); pdf.set_font("Arial", "", 6)
            for _, row in df.iterrows():
                for h in header:
                    cell_text = str(row[h])
                    if isinstance(row[h], datetime) and pd.notna(row[h]): cell_text = row[h].strftime('%d/%m/%Y')
                    elif isinstance(row[h], (float, int)): cell_text = f"R$ {row[h]:,.2f}" if 'Valor' in h else str(row[h])
                    elif pd.isna(row[h]): cell_text = ""
                    pdf.cell(col_widths.get(h, 20), 6, cell_text, 1, 0, 'C')
                pdf.ln()
            if pdf.get_y() < pdf.h - 55: pdf.ln(5)
            
    header_map = {'Nº Equipamento': 'Nº\nEquipamento', 'Valor a Faturar': 'Valor a\nFaturar', 'Data Ativação': 'Data\nAtivação', 'Data Desativação': 'Data\nDesativação', 'Dias Ativos Mês': 'Dias\nAtivos', 'Suspenso Dias Mes': 'Dias\nSuspensos', 'Dias a Faturar': 'Dias a\nFaturar', 'Valor Unitario': 'Valor\nUnitário'}
    widths_cheio = {'Terminal': 38, 'Nº Equipamento': 38, 'Placa': 25, 'Modelo': 34, 'Tipo': 20, 'Valor a Faturar': 35}
    draw_table("Detalhamento do Faturamento Cheio", df_cheio, widths_cheio, list(widths_cheio.keys()), header_map)
    widths_proporcional = {'Terminal': 19, 'Nº Equipamento': 20, 'Modelo': 18, 'Tipo': 14, 'Data Ativação': 17, 'Data Desativação': 17, 'Dias Ativos Mês': 13, 'Suspenso Dias Mes': 16, 'Dias a Faturar': 13, 'Valor Unitario': 19, 'Valor a Faturar': 19}
    cols_proporcionais = ['Terminal', 'Nº Equipamento', 'Modelo', 'Tipo', 'Data Ativação', 'Data Desativação', 'Dias Ativos Mês', 'Suspenso Dias Mes', 'Dias a Faturar', 'Valor Unitario', 'Valor a Faturar']
    draw_table("Detalhamento Proporcional (Ativações no Mês)", df_ativados, widths_proporcional, cols_proporcionais, header_map)
    draw_table("Detalhamento Proporcional (Desativações no Mês)", df_desativados, widths_proporcional, cols_proporcionais, header_map)
    draw_table("Detalhamento dos Terminais Suspensos (Faturamento Prop.)", df_suspensos, widths_proporcional, cols_proporcionais, header_map)
    
    return bytes(pdf.output(dest='S').encode('latin-1', errors='replace'))

@st.cache_data
def processar_planilha_lote(file_bytes, file_name, tracker_inventory, global_prices):
    try:
        meses_pt = {"January": "Janeiro", "February": "Fevereiro", "March": "Março", "April": "Abril", "May": "Maio", "June": "Junho", "July": "Julho", "August": "Agosto", "September": "Setembro", "October": "Outubro", "November": "Novembro", "December": "Dezembro"}
        
        # Leitura inicial para encontrar cabeçalho e período
        if file_name.endswith('.csv'):
            df_raw = pd.read_csv(io.BytesIO(file_bytes), header=None, encoding='utf-8', on_bad_lines='skip')
        else:
            df_raw = pd.read_excel(io.BytesIO(file_bytes), header=None, engine='openpyxl')

        # Buscar data do relatório no cabeçalho bruto (agora à prova de floats/NaNs)
        report_date = None
        for i in range(min(20, len(df_raw))):
            row_str = " ".join([str(val) for val in df_raw.iloc[i].tolist()])
            match = re.search(r'Data Final:\s*(\d{2}[-/]\d{2}[-/]\d{4})', row_str)
            if match:
                start_date_str = match.group(1).replace('-', '/')
                report_date = pd.to_datetime(start_date_str, dayfirst=True)
                break
        
        # Encontrar a linha real do cabeçalho da tabela
        header_row_idx = None
        for i in range(min(30, len(df_raw))):
            row_vals = [str(val) for val in df_raw.iloc[i].tolist()]
            if any('Cliente' in val for val in row_vals) and any('Terminal' in val for val in row_vals):
                header_row_idx = i
                break
                
        if header_row_idx is None:
            return None, None, None, "Erro: Não foi possível encontrar o cabeçalho com as colunas 'Cliente' e 'Terminal'."

        # Construir o dataframe definitivo
        df = df_raw.iloc[header_row_idx+1:].copy()
        df.columns = [str(c).strip() for c in df_raw.iloc[header_row_idx].tolist()]
        
        df = df.rename(columns={'Suspenso Dias Mês': 'Suspenso Dias Mes', 'Equipamento': 'Nº Equipamento'})
        df.dropna(subset=['Terminal'], inplace=True)
        df = df[df['Terminal'].astype(str).str.strip() != '']
        df = df[df['Cliente'] != 'Cliente'] # Remove repetições de cabeçalho na quebra de página
        
        # Limpar nomes dos clientes
        df['Cliente'] = df['Cliente'].astype(str).str.strip()

        for col in ['Data Ativação', 'Data Desativação']:
            df[col] = pd.to_datetime(df[col], errors='coerce', dayfirst=True)
        for col in ['Dias Ativos Mês', 'Suspenso Dias Mes']:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            
        if not report_date:
            report_date = datetime.now()

        report_month, report_year = report_date.month, report_date.year
        dias_no_mes = pd.Timestamp(year=report_year, month=report_month, day=1).days_in_month
        periodo_relatorio = f"{meses_pt.get(report_date.strftime('%B'), report_date.strftime('%B'))} de {report_year}"
        
        # Cruzamento com Estoque
        df_inventory = pd.DataFrame(tracker_inventory)
        # Garantir que as chaves de cruzamento sejam strings limpas
        df['Nº Equipamento'] = df['Nº Equipamento'].astype(str).str.strip()
        df_inventory['Nº Equipamento'] = df_inventory['Nº Equipamento'].astype(str).str.strip()
        
        df_merged = pd.merge(df, df_inventory, on='Nº Equipamento', how='left')
        not_found_equip = df_merged[df_merged['Tipo'].isna()]['Nº Equipamento'].unique().tolist()
        
        # --- PRECIFICAÇÃO INTELIGENTE POR CLIENTE ---
        # Busca o último faturamento de cada cliente para aplicar preços personalizados automaticamente
        client_prices = {}
        for cliente in df_merged['Cliente'].unique():
            last_billing = umdb.get_last_billing_for_client(cliente)
            if last_billing:
                client_prices[cliente] = {
                    "GPRS": last_billing.get("valor_unitario_gprs", global_prices.get("GPRS", 0)),
                    "SATELITE": last_billing.get("valor_unitario_satelital", global_prices.get("SATELITE", 0))
                }
            else:
                client_prices[cliente] = global_prices.copy()
                
        def get_price(row):
            c = row['Cliente']
            t = row['Tipo']
            return client_prices.get(c, {}).get(t, 0.0)

        df_merged['Valor Unitario'] = df_merged.apply(get_price, axis=1)

        # Regras de Categoria
        conditions = [
            (df_merged['Data Desativação'].notna()),
            (df_merged['Data Ativação'].dt.month == report_month) & (df_merged['Data Ativação'].dt.year == report_year),
            (df_merged['Condição'].astype(str).str.strip().str.lower() == 'suspenso')
        ]
        choices = ['Desativado', 'Ativado no Mês', 'Suspenso']
        df_merged['Categoria'] = np.select(conditions, choices, default='Cheio')
        
        dias_a_faturar = 0
        dias_a_faturar = np.where(df_merged['Categoria'] == 'Desativado', df_merged['Data Desativação'].dt.day - df_merged['Suspenso Dias Mes'], dias_a_faturar)
        dias_a_faturar = np.where(df_merged['Categoria'] == 'Ativado no Mês', (dias_no_mes - df_merged['Data Ativação'].dt.day + 1) - df_merged['Suspenso Dias Mes'], dias_a_faturar)
        dias_a_faturar = np.where(df_merged['Categoria'].isin(['Suspenso', 'Cheio']), df_merged['Dias Ativos Mês'] - df_merged['Suspenso Dias Mes'], dias_a_faturar)
        
        df_merged['Dias a Faturar'] = np.clip(dias_a_faturar, 0, None)
        df_merged['Valor a Faturar'] = (df_merged['Valor Unitario'] / dias_no_mes) * df_merged['Dias a Faturar']
        
        return periodo_relatorio, df_merged, not_found_equip, None

    except Exception as e:
        return None, None, None, f"Ocorreu um erro inesperado: {e}"

def generate_master_excel(df_aprovado):
    output = io.BytesIO()
    
    # Criar DataFrame de Resumo
    resumo_data = []
    for cliente in df_aprovado['Cliente'].unique():
        df_cliente = df_aprovado[df_aprovado['Cliente'] == cliente]
        total_geral = df_cliente['Valor a Faturar'].sum()
        total_terminais = len(df_cliente)
        terminais_suspensos = len(df_cliente[df_cliente['Categoria'] == 'Suspenso'])
        
        resumo_data.append({
            'Cliente': cliente,
            'Total Faturar': total_geral,
            'Qtd Terminais Faturados': total_terminais,
            'Qtd Terminais Suspensos': terminais_suspensos
        })
        
    df_resumo = pd.DataFrame(resumo_data)
    
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_resumo.to_excel(writer, index=False, sheet_name='Resumo Faturamento Lote')
        df_aprovado.to_excel(writer, index=False, sheet_name='Todos os Terminais')
        
    return output.getvalue()

def create_zip_of_pdfs(df_aprovado, periodo_relatorio):
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
        clientes = df_aprovado['Cliente'].unique()
        for cliente in clientes:
            df_cliente = df_aprovado[df_aprovado['Cliente'] == cliente].copy()
            
            df_cheio = df_cliente[df_cliente['Categoria'] == 'Cheio']
            df_ativados = df_cliente[df_cliente['Categoria'] == 'Ativado no Mês']
            df_desativados = df_cliente[df_cliente['Categoria'] == 'Desativado']
            df_suspensos = df_cliente[df_cliente['Categoria'] == 'Suspenso']
            
            total_cheio = df_cheio['Valor a Faturar'].sum()
            total_proporcional = df_ativados['Valor a Faturar'].sum() + df_desativados['Valor a Faturar'].sum() + df_suspensos['Valor a Faturar'].sum()
            total_geral = total_cheio + total_proporcional
            
            totais = {
                "cheio": total_cheio,
                "proporcional": total_proporcional,
                "geral": total_geral,
                "terminais_cheio": len(df_cheio),
                "terminais_proporcional": len(df_ativados) + len(df_desativados),
                "terminais_suspensos": len(df_suspensos),
                "terminais_gprs": len(df_cliente[df_cliente['Tipo'] == 'GPRS']),
                "terminais_satelitais": len(df_cliente[df_cliente['Tipo'] == 'SATELITE'])
            }
            
            pdf_bytes = create_pdf_report(cliente, periodo_relatorio, totais, df_cheio, df_ativados, df_desativados, df_suspensos)
            safe_cliente = re.sub(r'[^A-Za-z0-9]+', '_', cliente).strip('_')
            file_name = f"Faturamento_{safe_cliente}.pdf"
            zip_file.writestr(file_name, pdf_bytes)
            
    return zip_buffer.getvalue()

def salvar_historico_lote(df_aprovado, periodo_relatorio, global_prices):
    for cliente in df_aprovado['Cliente'].unique():
        df_cliente = df_aprovado[df_aprovado['Cliente'] == cliente]
        
        total_geral = df_cliente['Valor a Faturar'].sum()
        terminais_cheio = len(df_cliente[df_cliente['Categoria'] == 'Cheio'])
        terminais_suspensos = len(df_cliente[df_cliente['Categoria'] == 'Suspenso'])
        terminais_prop = len(df_cliente) - terminais_cheio - terminais_suspensos
        
        # Recupera preço para log (tenta pegar do dataframe se existir, senão global)
        preco_gprs = df_cliente[df_cliente['Tipo'] == 'GPRS']['Valor Unitario'].max()
        preco_sat = df_cliente[df_cliente['Tipo'] == 'SATELITE']['Valor Unitario'].max()
        
        log_data = {
            "cliente": cliente, 
            "periodo_relatorio": periodo_relatorio, 
            "valor_total": total_geral, 
            "terminais_cheio": terminais_cheio, 
            "terminais_proporcional": terminais_prop, 
            "terminais_suspensos": terminais_suspensos, 
            "terminais_gprs": len(df_cliente[df_cliente['Tipo'] == 'GPRS']), 
            "terminais_satelitais": len(df_cliente[df_cliente['Tipo'] == 'SATELITE']), 
            "valor_unitario_gprs": preco_gprs if pd.notna(preco_gprs) else global_prices.get("GPRS", 0), 
            "valor_unitario_satelital": preco_sat if pd.notna(preco_sat) else global_prices.get("SATELITE", 0)
        }
        
        cols_to_save = ['Terminal', 'Nº Equipamento', 'Modelo', 'Tipo', 'Categoria', 'Valor Unitario', 'Valor a Faturar', 'Dias a Faturar']
        detalhes_itens = df_cliente[cols_to_save].to_dict(orient='records')
        
        umdb.log_faturamento(log_data, detalhes_itens)
        
    st.session_state['lote_salvo'] = True

# --- 4. INPUTS DE CONFIGURAÇÃO GLOBAIS ---
st.sidebar.header("Valores Padrão Globais")
st.sidebar.info("Estes valores serão usados caso o cliente não tenha um histórico de preços salvo.")
pricing_config = umdb.get_pricing_config().get("TIPO_EQUIPAMENTO", {})
prices = {}
for equip_type in sorted(pricing_config.keys()):
    val = pricing_config.get(equip_type, 0.0)
    if isinstance(val, dict): val = val.get("price1", 0.0)
    prices[equip_type] = st.sidebar.number_input(f"Preço {equip_type}", min_value=0.0, value=float(val), format="%.2f")

# --- 5. UPLOAD DO FICHEIRO ---
st.subheader("Processamento de Faturamento em Lote (Múltiplos Clientes)")
st.info("Carregue o arquivo consolidado de terminais. O sistema processará todos os clientes de uma vez, aplicando os preços adequados baseados no histórico.")
uploaded_file = st.file_uploader("Selecione o relatório consolidado", type=['xlsx', 'csv'])
st.markdown("---")

# --- 6. ANÁLISE E EXIBIÇÃO ---
if uploaded_file:
    tracker_inventory = umdb.get_tracker_inventory()
    if not tracker_inventory:
        st.warning("⚠️ Nenhum dado de estoque de rastreadores encontrado."); st.stop()
    
    file_bytes = uploaded_file.getvalue()
    file_name = uploaded_file.name
    
    with st.spinner('Processando dados de todos os clientes...'):
        periodo_relatorio, df_final, not_found, error = processar_planilha_lote(file_bytes, file_name, tracker_inventory, prices)

    if error:
        st.error(error)
    elif df_final is not None:
        
        if not_found:
            with st.expander("⚠️ Equipamentos Não Encontrados no Estoque", expanded=False):
                st.warning("Os seguintes equipamentos não foram encontrados no estoque.")
                st.json(not_found)

        # --- SEÇÃO DE REVISÃO INTERATIVA ---
        st.subheader(f"Revisão Global de Terminais - {periodo_relatorio}")
        st.caption("Desmarque a caixa 'Faturar?' para ignorar equipamentos específicos de qualquer cliente.")
        
        if 'Faturar' not in df_final.columns:
            df_final.insert(0, 'Faturar', True)
            
        edited_df = st.data_editor(
            df_final,
            column_config={
                "Faturar": st.column_config.CheckboxColumn("Faturar?", default=True),
                "Cliente": st.column_config.TextColumn(disabled=True),
                "Terminal": st.column_config.TextColumn(disabled=True),
                "Nº Equipamento": st.column_config.TextColumn(disabled=True),
                "Tipo": st.column_config.TextColumn(disabled=True),
                "Categoria": st.column_config.TextColumn(disabled=True),
                "Valor Unitario": st.column_config.NumberColumn(format="R$ %.2f", disabled=True),
                "Valor a Faturar": st.column_config.NumberColumn(format="R$ %.2f", disabled=True),
            },
            hide_index=True,
            use_container_width=True,
            height=400,
            key="editor_revisao_lote"
        )
        
        df_aprovado = edited_df[edited_df['Faturar'] == True].copy()
        
        total_geral_lote = df_aprovado['Valor a Faturar'].sum()
        total_clientes = df_aprovado['Cliente'].nunique()
        total_terminais = len(df_aprovado)
        
        st.markdown("---")
        st.header("Resumo Consolidado do Lote")
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Total de Clientes", total_clientes)
        c2.metric("Total de Terminais Faturados", total_terminais)
        c3.info(f"**FATURAMENTO TOTAL PREVISTO:** R$ {total_geral_lote:,.2f}")
        
        # Resumo por cliente na tela
        resumo_tela = df_aprovado.groupby('Cliente').agg(
            Qtd_Terminais=('Terminal', 'count'),
            Valor_Faturar=('Valor a Faturar', 'sum')
        ).reset_index()
        
        with st.expander("Ver Resumo por Cliente"):
            st.dataframe(
                resumo_tela, 
                use_container_width=True, 
                hide_index=True,
                column_config={"Valor_Faturar": st.column_config.NumberColumn(format="R$ %.2f")}
            )
            
        st.markdown("---")
        st.subheader("Exportação e Salvamento")
        
        # Gerar arquivos
        excel_master_data = generate_master_excel(df_aprovado)
        zip_pdfs_data = create_zip_of_pdfs(df_aprovado, periodo_relatorio)
        
        col1, col2, col3 = st.columns(3)
        
        col1.download_button(
            "📊 Baixar Excel Consolidado", 
            excel_master_data, 
            f"Faturamento_Lote_{periodo_relatorio.replace(' ', '_')}.xlsx", 
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
        col2.download_button(
            "📁 Baixar PDFs Individuais (ZIP)", 
            zip_pdfs_data, 
            f"PDFs_Faturamento_{periodo_relatorio.replace(' ', '_')}.zip", 
            "application/zip"
        )
        
        if col3.button("💾 Salvar Histórico de Todos no Banco", type="primary"):
            with st.spinner("Salvando históricos..."):
                salvar_historico_lote(df_aprovado, periodo_relatorio, prices)
            
        if st.session_state.get('lote_salvo'):
            st.success("✅ O faturamento de todos os clientes foi registrado no banco de dados com sucesso!")

else:
    st.info("Aguardando o carregamento da planilha consolidada (Excel ou CSV) para iniciar a análise em lote.")
