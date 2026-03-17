# pages/10_Faturamento_Parceiros.py
import sys
import os
import re
import io
from datetime import datetime
import pandas as pd
import numpy as np
from fpdf import FPDF
import streamlit as st

# Adiciona o diretório raiz ao path para importar módulos do projeto
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from firebase_config import db
import user_management_db as umdb

# --- CLASSE PARA GERAR PDF ---
class PDF(FPDF):
    def header(self):
        try:
            page_width = self.w - self.l_margin - self.r_margin
            self.image("imgs/header1.png", x=self.l_margin, y=8, w=page_width)
        except Exception:
            self.set_font("Arial", "B", 20)
            self.cell(0, 10, "Uzzipay Solucoes", 0, 1, "L")
            self.ln(15)

    def footer(self):
        try:
            self.set_y(-35)
            page_width = self.w - self.l_margin - self.r_margin
            self.image("imgs/footer1.png", x=self.l_margin, y=self.get_y(), w=page_width)
        except Exception:
            self.set_y(-15)
            self.set_font("Arial", "I", 8)
            self.cell(0, 10, f"Pagina {self.page_no()}", 0, 0, "C")

# --- CONFIGURAÇÃO E AUTENTICAÇÃO ---
st.set_page_config(layout="wide", page_title="Faturamento Filiais/Parceiros", page_icon="🏢")

if "user_info" not in st.session_state:
    st.error("🔒 Acesso Negado! Por favor, faça login para visualizar esta página.")
    st.stop()

st.sidebar.image("imgs/v-c.png", width=120)
st.sidebar.title(f"Olá, {st.session_state.get('name', 'N/A')}! 👋")
st.sidebar.markdown("---")
if st.sidebar.button("Logout"):
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.switch_page("1_Home.py")

# --- FUNÇÕES DE BANCO DE DADOS (FIREBASE) ---
def get_regras_parceiros():
    try:
        docs = db.collection("regras_parceiros").stream()
        return {doc.id: doc.to_dict() for doc in docs}
    except Exception as e:
        st.error(f"Erro ao buscar regras: {e}")
        return {}

def save_regra_parceiro(nome_parceiro, dados):
    try:
        db.collection("regras_parceiros").document(nome_parceiro).set(dados)
        return True
    except Exception as e:
        st.error(f"Erro ao salvar regra: {e}")
        return False

def get_terminais_parceiro(nome_parceiro):
    try:
        docs = db.collection("terminais_parceiros").where("parceiro", "==", nome_parceiro).stream()
        return {doc.id: doc.to_dict() for doc in docs}
    except Exception as e:
        st.error(f"Erro ao buscar terminais do parceiro: {e}")
        return {}

def registrar_terminal_parceiro(terminal, parceiro, data_ativacao):
    try:
        db.collection("terminais_parceiros").document(terminal).set({
            "parceiro": parceiro,
            "data_ativacao": data_ativacao.strftime("%Y-%m-%d"),
            "data_registro": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
    except Exception as e:
        st.error(f"Erro ao registrar terminal no controle de cotas: {e}")

# --- FUNÇÕES DE LÓGICA DE FATURAMENTO ---
def calcular_meses_diferenca(data_inicio, data_fim):
    return (data_fim.year - data_inicio.year) * 12 + (data_fim.month - data_inicio.month)

@st.cache_data
def processar_planilha_parceiro(file_bytes, regra_parceiro, terminais_registrados):
    try:
        meses_pt = {"January": "Janeiro", "February": "Fevereiro", "March": "Março", "April": "Abril", "May": "Maio", "June": "Junho", "July": "Julho", "August": "Agosto", "September": "Setembro", "October": "Outubro", "November": "Novembro", "December": "Dezembro"}
        
        # Lê a data do relatório (Célula I9)
        try:
            periodo_df = pd.read_excel(io.BytesIO(file_bytes), header=None, sheet_name=0)
            periodo_str = periodo_df.iloc[8, 8]
            match = re.search(r'(\d{2}[-/]\d{2}[-/]\d{4})', str(periodo_str))
            if match:
                start_date_str = match.group(1).replace('-', '/')
                report_date = pd.to_datetime(start_date_str, dayfirst=True)
            else: 
                report_date = datetime.now()
        except Exception:
            report_date = datetime.now()

        # Lê os dados principais (Linha 12 em diante)
        df = pd.read_excel(io.BytesIO(file_bytes), header=11, engine='openpyxl', dtype={'Equipamento': str, 'Código do Terminal': str})
        df = df.rename(columns={'Suspenso Dias Mês': 'Suspenso Dias Mes', 'Código do Terminal': 'Nº Equipamento'})
        df.dropna(subset=['Terminal'], inplace=True)

        required_cols = ['Terminal', 'Data Ativação', 'Data Desativação', 'Dias Ativos Mês', 'Suspenso Dias Mes', 'Nº Equipamento', 'Condição']
        if not all(col in df.columns for col in required_cols):
            return None, "Erro de Colunas: Verifique o cabeçalho na linha 12 do arquivo enviado.", None, None

        for col in ['Data Ativação', 'Data Desativação']:
            df[col] = pd.to_datetime(df[col], errors='coerce', dayfirst=True)
        for col in ['Dias Ativos Mês', 'Suspenso Dias Mes']:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        report_month, report_year = report_date.month, report_date.year
        dias_no_mes = pd.Timestamp(year=report_year, month=report_month, day=1).days_in_month
        periodo_relatorio = f"{meses_pt.get(report_date.strftime('%B'), report_date.strftime('%B'))} de {report_year}"
        
        # Categorização proporcional
        conditions = [
            (df['Data Desativação'].notna()),
            (df['Data Ativação'].dt.month == report_month) & (df['Data Ativação'].dt.year == report_year),
            (df['Condição'].str.strip() == 'Suspenso')
        ]
        choices = ['Desativado', 'Ativado no Mês', 'Suspenso']
        df['Categoria'] = np.select(conditions, choices, default='Cheio')
        
        dias_a_faturar = 0
        dias_a_faturar = np.where(df['Categoria'] == 'Desativado', df['Data Desativação'].dt.day - df['Suspenso Dias Mes'], dias_a_faturar)
        dias_a_faturar = np.where(df['Categoria'] == 'Ativado no Mês', (dias_no_mes - df['Data Ativação'].dt.day + 1) - df['Suspenso Dias Mes'], dias_a_faturar)
        dias_a_faturar = np.where(df['Categoria'].isin(['Suspenso', 'Cheio']), df['Dias Ativos Mês'] - df['Suspenso Dias Mes'], dias_a_faturar)
        df['Dias a Faturar'] = np.clip(dias_a_faturar, 0, None)
        
        # --- APLICAÇÃO DA REGRA DE NEGÓCIO (COTA E PRAZO) ---
        valores_unitarios = []
        status_promocao = []
        terminais_novos_para_registrar = []
        
        cota_maxima = regra_parceiro.get("cota_maxima", 0)
        meses_duracao = regra_parceiro.get("meses_duracao", 0)
        preco_promo = regra_parceiro.get("preco_promocional", 0.0)
        preco_normal = regra_parceiro.get("preco_normal", 0.0)
        nome_parceiro = regra_parceiro.get("nome", "")
        
        cota_atual = len(terminais_registrados)

        for _, row in df.iterrows():
            terminal = str(row['Terminal']).strip()
            data_ativacao = row['Data Ativação']
            
            # Se for nulo, ignora a promoção e cobra normal
            if pd.isna(data_ativacao):
                valores_unitarios.append(preco_normal)
                status_promocao.append("Sem Data Ativação")
                continue

            # Verifica se já está registrado na base de promoções deste parceiro
            if terminal in terminais_registrados:
                data_reg_str = terminais_registrados[terminal].get("data_ativacao")
                data_ativacao_base = pd.to_datetime(data_reg_str) if data_reg_str else data_ativacao
                meses_uso = calcular_meses_diferenca(data_ativacao_base, report_date)
                
                if meses_uso < meses_duracao:
                    valores_unitarios.append(preco_promo)
                    status_promocao.append(f"Promoção Ativa (Mês {meses_uso+1}/{meses_duracao})")
                else:
                    valores_unitarios.append(preco_normal)
                    status_promocao.append("Prazo Promocional Expirado")
            else:
                # Terminal novo, verifica se ainda tem cota
                if cota_atual < cota_maxima:
                    valores_unitarios.append(preco_promo)
                    status_promocao.append("Nova Promoção Aplicada")
                    terminais_novos_para_registrar.append((terminal, data_ativacao))
                    cota_atual += 1
                else:
                    valores_unitarios.append(preco_normal)
                    status_promocao.append("Cota Promocional Esgotada")

        df['Valor Unitario'] = valores_unitarios
        df['Status Promoção'] = status_promocao
        df['Valor a Faturar'] = (df['Valor Unitario'] / dias_no_mes) * df['Dias a Faturar']
        
        return periodo_relatorio, df, terminais_novos_para_registrar, None

    except Exception as e:
        return None, None, None, f"Ocorreu um erro inesperado: {e}"

def export_excel(df_final):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_final.to_excel(writer, index=False, sheet_name='Faturamento Parceiro')
    return output.getvalue()

def create_pdf_parceiro(nome_parceiro, periodo, totais, df_final):
    pdf = PDF(orientation='P')
    pdf.set_top_margin(40)
    pdf.set_auto_page_break(auto=True, margin=45)
    pdf.add_page()
    
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, "Relatório de Faturamento - Parceiros", 0, 1, "C")
    pdf.ln(5)
    
    pdf.set_font("Arial", "", 12)
    pdf.cell(0, 8, f"Filial/Parceiro: {nome_parceiro}", 0, 1, "L")
    pdf.cell(0, 8, f"Período: {periodo}", 0, 1, "L")
    pdf.ln(5)
    
    pdf.set_font("Arial", "B", 10)
    pdf.cell(60, 8, "Total de Terminais Faturados:", 0, 0, "L")
    pdf.set_font("Arial", "", 10)
    pdf.cell(0, 8, str(len(df_final)), 0, 1, "L")
    
    pdf.set_font("Arial", "B", 10)
    pdf.cell(60, 8, "Terminais na Promoção:", 0, 0, "L")
    pdf.set_font("Arial", "", 10)
    qtd_promo = len(df_final[df_final['Valor Unitario'] < totais['preco_normal']])
    pdf.cell(0, 8, str(qtd_promo), 0, 1, "L")
    
    pdf.ln(5)
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 10, f"FATURAMENTO TOTAL: R$ {totais['total']:,.2f}", 1, 1, "C")
    pdf.ln(10)
    
    if not df_final.empty:
        pdf.set_font("Arial", "B", 7)
        cols = ['Terminal', 'Categoria', 'Dias a Faturar', 'Status Promoção', 'Valor Unitario', 'Valor a Faturar']
        widths = [30, 25, 25, 55, 25, 30]
        
        for i, col in enumerate(cols):
            pdf.cell(widths[i], 8, col, 1, 0, 'C')
        pdf.ln()
        
        pdf.set_font("Arial", "", 7)
        for _, row in df_final.iterrows():
            pdf.cell(widths[0], 6, str(row['Terminal']), 1, 0, 'C')
            pdf.cell(widths[1], 6, str(row['Categoria']), 1, 0, 'C')
            pdf.cell(widths[2], 6, str(row['Dias a Faturar']), 1, 0, 'C')
            pdf.cell(widths[3], 6, str(row['Status Promoção']), 1, 0, 'C')
            pdf.cell(widths[4], 6, f"R$ {row['Valor Unitario']:,.2f}", 1, 0, 'C')
            pdf.cell(widths[5], 6, f"R$ {row['Valor a Faturar']:,.2f}", 1, 1, 'C')

    return bytes(pdf.output(dest='S').encode('latin-1', errors='replace'))


# --- INTERFACE DO USUÁRIO ---
st.title("🏢 Gestão e Faturamento de Filiais")

tab1, tab2 = st.tabs(["📊 Processar Faturamento", "⚙️ Regras e Campanhas (Configuração)"])

regras_cadastradas = get_regras_parceiros()

with tab2:
    st.header("Configuração de Campanhas e Regras de Preço")
    st.markdown("Crie ou atualize as regras de faturamento para filiais (Ex: Autovema).")
    
    with st.form("form_regra_parceiro"):
        c1, c2 = st.columns(2)
        nome_parceiro = c1.text_input("Nome da Filial/Parceiro (Ex: Autovema)")
        cota_maxima = c2.number_input("Cota Máxima de Veículos na Promoção", min_value=0, value=100, step=1)
        
        c3, c4, c5 = st.columns(3)
        preco_normal = c3.number_input("Preço Normal (R$)", min_value=0.0, value=60.0, format="%.2f")
        preco_promocional = c4.number_input("Preço Promocional (R$)", min_value=0.0, value=20.0, format="%.2f")
        meses_duracao = c5.number_input("Duração da Promoção (Meses)", min_value=1, value=12, step=1)
        
        submit_regra = st.form_submit_button("Salvar Regra da Filial")
        
        if submit_regra:
            if not nome_parceiro:
                st.warning("O nome da filial é obrigatório.")
            else:
                dados = {
                    "nome": nome_parceiro.strip(),
                    "cota_maxima": cota_maxima,
                    "preco_normal": preco_normal,
                    "preco_promocional": preco_promocional,
                    "meses_duracao": meses_duracao,
                    "ultima_atualizacao": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                if save_regra_parceiro(nome_parceiro.strip(), dados):
                    st.success(f"Regra para '{nome_parceiro}' salva com sucesso!")
                    st.rerun()

    if regras_cadastradas:
        st.markdown("---")
        st.subheader("Filiais Cadastradas")
        df_regras = pd.DataFrame(list(regras_cadastradas.values()))
        st.dataframe(df_regras, use_container_width=True, hide_index=True)


with tab1:
    if not regras_cadastradas:
        st.info("Nenhuma filial cadastrada. Vá na aba 'Regras e Campanhas' para criar a primeira regra (ex: Autovema).")
    else:
        st.subheader("Faturamento Mensal do Parceiro")
        
        filial_selecionada = st.selectbox("Selecione a Filial para Faturamento", options=list(regras_cadastradas.keys()))
        regra_atual = regras_cadastradas[filial_selecionada]
        
        st.info(f"**Regra Ativa:** Cota de {regra_atual['cota_maxima']} veículos a R$ {regra_atual['preco_promocional']:,.2f} durante {regra_atual['meses_duracao']} meses. Valor normal: R$ {regra_atual['preco_normal']:,.2f}.")
        
        uploaded_file = st.file_uploader(f"Selecione o relatório (.xlsx) exportado para a {filial_selecionada}", type=['xlsx'])
        
        if uploaded_file:
            terminais_bd = get_terminais_parceiro(filial_selecionada)
            
            with st.spinner("Processando regras e verificando cotas..."):
                file_bytes = uploaded_file.getvalue()
                periodo_relatorio, df_final, terminais_novos, erro = processar_planilha_parceiro(file_bytes, regra_atual, terminais_bd)
            
            if erro:
                st.error(erro)
            elif df_final is not None:
                total_geral = df_final['Valor a Faturar'].sum()
                qtd_total = len(df_final)
                qtd_promocao = len(df_final[df_final['Valor Unitario'] == regra_atual['preco_promocional']])
                qtd_normal = len(df_final[df_final['Valor Unitario'] == regra_atual['preco_normal']])
                
                # Exibição dos Totais
                st.markdown("---")
                st.header("Resumo do Faturamento")
                st.caption(f"Período: {periodo_relatorio}")
                
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Total de Veículos", qtd_total)
                col2.metric("Veículos na Promoção", qtd_promocao)
                col3.metric("Veículos Preço Normal", qtd_normal)
                col4.metric("Valor Total a Faturar", f"R$ {total_geral:,.2f}")
                
                # Se houver novos terminais que entraram na cota, avisa e permite salvar no banco
                if terminais_novos:
                    st.warning(f"Foram identificados **{len(terminais_novos)} novos terminais** que se qualificam para a promoção. Eles ocuparão a cota da filial.")
                    
                    if st.button("Gravar Novos Terminais na Cota e Exportar", type="primary"):
                        with st.spinner("Registrando terminais na cota..."):
                            for terminal, data_ativacao in terminais_novos:
                                registrar_terminal_parceiro(terminal, filial_selecionada, data_ativacao)
                        st.success("Terminais registrados no banco com sucesso! Gerando arquivos...")
                        st.rerun()
                
                st.markdown("---")
                st.subheader("Ações Finais e Exportação")
                
                excel_data = export_excel(df_final)
                totais = {"total": total_geral, "preco_normal": regra_atual['preco_normal']}
                pdf_data = create_pdf_parceiro(filial_selecionada, periodo_relatorio, totais, df_final)
                
                c1, c2 = st.columns(2)
                c1.download_button(
                    label="📥 Baixar Excel Analítico",
                    data=excel_data,
                    file_name=f"Faturamento_{filial_selecionada}_{datetime.now().strftime('%Y-%m')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                c2.download_button(
                    label="📄 Baixar Resumo em PDF",
                    data=pdf_data,
                    file_name=f"Resumo_{filial_selecionada}_{datetime.now().strftime('%Y-%m')}.pdf",
                    mime="application/pdf"
                )
                
                st.markdown("---")
                with st.expander("Ver Tabela Detalhada de Faturamento e Status das Promoções", expanded=True):
                    cols_to_show = ['Terminal', 'Data Ativação', 'Categoria', 'Dias a Faturar', 'Status Promoção', 'Valor Unitario', 'Valor a Faturar']
                    st.dataframe(df_final[cols_to_show], use_container_width=True, hide_index=True)
