# pages/8_Relatorio_API.py
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
import io

# --- 1. CONFIGURAÇÃO DA PÁGINA E AUTENTICAÇÃO ---
st.set_page_config(
    layout="wide",
    page_title="Relatório de Transações por API",
    page_icon="📊"
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


# --- 2. FUNÇÕES DE LÓGICA ---

@st.cache_data(ttl=600) # Cache por 10 minutos
def buscar_dados_api(token, data_inicio, data_fim):
    """
    Busca os dados da API com o token e período fornecidos.
    """
    if not token:
        return None, "Por favor, insira o Token de Autenticação."

    headers = {
        "Authorization": f"Bearer {token}"
    }
    
    # Formata as datas no padrão esperado pela API (dd/mm/aaaa)
    data_formatada = f"{data_inicio.strftime('%d/%m/%Y')} - {data_fim.strftime('%d/%m/%Y')}"
    
    url = f"https://sigyo.uzzipay.com/api/transacoes?TransacaoSearch[data_cadastro]={data_formatada}"
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()  # Lança um erro para status HTTP 4xx/5xx
        return response.json(), None
    except requests.exceptions.HTTPError as err:
        if response.status_code == 401:
            return None, "Erro de Autenticação: Token inválido ou expirado."
        return None, f"Erro HTTP: {err}"
    except requests.exceptions.RequestException as e:
        return None, f"Erro de conexão com a API: {e}"

def processar_transacoes(dados_api, nome_cliente, taxa_ir, taxa_admin, outras_taxas):
    """
    Filtra e processa os dados JSON para o cliente e secretarias especificados.
    """
    if not dados_api:
        return None, {}

    # Normaliza o JSON para um DataFrame do Pandas
    df = pd.json_normalize(dados_api)

    # Renomeia colunas para facilitar o acesso
    df.rename(columns={
        'informacao.cliente.nome': 'Cliente',
        'informacao.search.subgrupo.nome': 'Secretaria',
        'data_cadastro': 'Data',
        'valor_total': 'Valor Bruto',
        'quantidade': 'Quantidade',
        'valor_unitario': 'Vlr. Unitário',
        'informacao.produto.nome': 'Produto',
        'informacao.credenciado.nome': 'Posto Credenciado',
        'informacao.veiculo.placa': 'Placa',
        'informacao.motorista.nome': 'Motorista'
    }, inplace=True)
    
    # Filtra pelo nome do cliente
    df_cliente = df[df['Cliente'].str.contains(nome_cliente, case=False, na=False)].copy()

    if df_cliente.empty:
        return None, {}
        
    # Converte colunas para os tipos corretos
    df_cliente['Data'] = pd.to_datetime(df_cliente['Data']).dt.strftime('%d/%m/%Y %H:%M')
    df_cliente['Valor Bruto'] = pd.to_numeric(df_cliente['Valor Bruto'], errors='coerce').fillna(0)
    df_cliente['Secretaria'] = df_cliente['Secretaria'].fillna('Secretaria Não Informada')

    # Calcula os valores com base nas taxas inseridas pelo usuário
    df_cliente['Taxa Adm (R$)'] = df_cliente['Valor Bruto'] * (taxa_admin / 100)
    df_cliente['IR Retido (R$)'] = df_cliente['Valor Bruto'] * (taxa_ir / 100)
    df_cliente['Outras Taxas (R$)'] = outras_taxas
    df_cliente['Valor Líquido'] = df_cliente['Valor Bruto'] - df_cliente['Taxa Adm (R$)'] - df_cliente['IR Retido (R$)'] - df_cliente['Outras Taxas (R$)']

    # Agrupa os dados por secretaria
    secretarias = df_cliente['Secretaria'].unique()
    dados_por_secretaria = {}

    for secretaria in secretarias:
        df_secretaria = df_cliente[df_cliente['Secretaria'] == secretaria].copy()
        dados_por_secretaria[secretaria] = df_secretaria
        
    return df_cliente, dados_por_secretaria

@st.cache_data
def to_excel(dados_por_secretaria):
    """
    Cria um arquivo Excel em memória com uma aba para cada secretaria.
    """
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        for secretaria, df_secretaria in dados_por_secretaria.items():
            # Remove caracteres inválidos do nome da aba
            safe_sheet_name = "".join([c for c in secretaria if c.isalnum() or c in (' ', '_')]).rstrip()[:31]
            df_secretaria.to_excel(writer, index=False, sheet_name=safe_sheet_name)
    return output.getvalue()


# --- 3. INTERFACE DA PÁGINA ---
st.title("📊 Relatório de Transações por API")
st.markdown("Consulte as transações de um cliente e suas secretarias, aplique taxas e exporte o resultado.")
st.markdown("---")

# --- Inputs do Usuário ---
st.subheader("1. Parâmetros da Consulta")
col1, col2 = st.columns(2)

with col1:
    token = st.text_input("🔑 Token de Autenticação da API", type="password")
    nome_cliente = st.text_input("👤 Nome do Cliente", value="SUGESP")

with col2:
    hoje = datetime.now()
    inicio_mes = hoje.replace(day=1)
    data_inicio = st.date_input("🗓️ Data de Início", value=inicio_mes)
    data_fim = st.date_input("🗓️ Data de Fim", value=hoje)

st.subheader("2. Taxas e Deduções")
col3, col4, col5 = st.columns(3)
with col3:
    taxa_admin_percent = st.number_input("Taxa de Administração (%)", min_value=0.0, value=5.0, step=0.1, format="%.2f")
with col4:
    taxa_ir_percent = st.number_input("Taxa de IR Retido (%)", min_value=0.0, value=1.5, step=0.1, format="%.2f")
with col5:
    outras_taxas_valor = st.number_input("Outras Taxas (R$)", min_value=0.0, value=0.0, step=0.01, format="%.2f")

if st.button("🚀 Gerar Relatório", type="primary"):
    if not token or not nome_cliente:
        st.warning("Por favor, preencha o Token e o Nome do Cliente.")
    else:
        with st.spinner("Buscando e processando dados da API..."):
            # Para demonstração, vamos carregar os dados locais se a API falhar
            # Em produção, você pode remover este bloco de 'try/except'
            try:
                dados_json, erro = buscar_dados_api(token, data_inicio, data_fim)
                if erro:
                    st.error(erro)
                    st.stop()
            except Exception:
                st.warning("Falha ao buscar dados da API. Usando dados de exemplo 'response.json'.")
                import json
                try:
                    with open('response.json', 'r') as f:
                        dados_json = json.load(f)
                except FileNotFoundError:
                    st.error("Arquivo 'response.json' de exemplo não encontrado.")
                    st.stop()
            
            df_completo, dados_por_secretaria = processar_transacoes(dados_json, nome_cliente, taxa_ir_percent, taxa_admin_percent, outras_taxas_valor)

            if df_completo is None or df_completo.empty:
                st.error(f"Nenhum dado encontrado para o cliente '{nome_cliente}' no período selecionado.")
            else:
                st.success("Relatório gerado com sucesso!")
                
                # --- Exibição dos Totais ---
                st.markdown("---")
                st.subheader("Resumo Geral")
                
                total_bruto = df_completo['Valor Bruto'].sum()
                total_taxa_adm = df_completo['Taxa Adm (R$)'].sum()
                total_ir = df_completo['IR Retido (R$)'].sum()
                total_outras_taxas = df_completo['Outras Taxas (R$)'].sum()
                total_liquido = df_completo['Valor Líquido'].sum()
                
                col_resumo1, col_resumo2, col_resumo3 = st.columns(3)
                col_resumo1.metric("Valor Bruto Total", f"R$ {total_bruto:,.2f}")
                col_resumo2.metric("Total de Deduções", f"R$ {(total_taxa_adm + total_ir + total_outras_taxas):,.2f}")
                col_resumo3.metric("Valor Líquido Total", f"R$ {total_liquido:,.2f}")
                
                # --- Botão de Download ---
                excel_file = to_excel(dados_por_secretaria)
                st.download_button(
                    label="📥 Baixar Relatório Completo em Excel",
                    data=excel_file,
                    file_name=f"Relatorio_{nome_cliente.replace(' ', '_')}_{hoje.strftime('%Y-%m-%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

                # --- Detalhamento por Secretaria ---
                st.markdown("---")
                st.subheader("Detalhamento por Secretaria")
                
                for secretaria, df_secretaria in dados_por_secretaria.items():
                    with st.expander(f"**{secretaria}** (Total: R$ {df_secretaria['Valor Líquido'].sum():,.2f})"):
                        st.dataframe(df_secretaria[[
                            'Data', 'Posto Credenciado', 'Placa', 'Motorista', 
                            'Produto', 'Quantidade', 'Vlr. Unitário', 'Valor Bruto',
                            'Taxa Adm (R$)', 'IR Retido (R$)', 'Valor Líquido'
                        ]], use_container_width=True, hide_index=True)
