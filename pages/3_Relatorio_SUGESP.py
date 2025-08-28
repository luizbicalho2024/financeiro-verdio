# pages/8_Relatorio_API.py (ou 3_Relatorio_SUGESP.py)
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
    page_title="SUGESP Relatório de Faturamento",
    page_icon=""
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

@st.cache_data(ttl=600)
def buscar_dados_api(token, endpoint):
    """Função genérica para buscar dados de um endpoint da API."""
    if not token:
        return None, "Por favor, insira o Token de Autenticação."
    
    headers = {"Authorization": f"Bearer {token}"}
    url = f"https://sigyo.uzzipay.com/api/{endpoint}"
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json(), None
    except requests.exceptions.HTTPError as err:
        return None, f"Erro HTTP {response.status_code}: Token inválido ou API indisponível no endpoint '{endpoint}'."
    except requests.exceptions.RequestException as e:
        return None, f"Erro de conexão com o endpoint '{endpoint}': {e}"

def mapear_empenhos(dados_empenhos):
    """Cria um dicionário mapeando o nome da secretaria ao seu número de empenho."""
    mapa = {}
    if not dados_empenhos:
        return mapa
    for empenho in dados_empenhos:
        # Verifica se 'grupo' e 'nome' existem para evitar erros
        if empenho.get('grupo') and empenho['grupo'].get('nome'):
            secretaria = empenho['grupo']['nome']
            numero_empenho = empenho.get('numero_empenho', 'Não encontrado')
            if secretaria not in mapa:
                mapa[secretaria] = []
            mapa[secretaria].append(numero_empenho)
    
    # Junta múltiplos empenhos em uma única string
    for secretaria, lista_empenhos in mapa.items():
        mapa[secretaria] = " / ".join(lista_empenhos)
        
    return mapa

def processar_dados_para_relatorio(dados_api, nome_cliente_principal, taxa_ir_geral):
    """Filtra e agrupa os dados por secretaria para gerar os valores do relatório."""
    if not dados_api:
        return None

    df = pd.json_normalize(dados_api)

    df.rename(columns={
        'informacao.cliente.nome': 'Cliente',
        'informacao.search.subgrupo.nome': 'Secretaria',
        'valor_total': 'Valor Bruto',
        'valor_liquido_cliente': 'Valor Liquido',
        'informacao.produto.nome': 'Produto'
    }, inplace=True)
    
    df_filtrado = df[df['Cliente'].str.contains(nome_cliente_principal, case=False, na=False)].copy()

    if df_filtrado.empty:
        return {}

    df_filtrado['Secretaria'] = df_filtrado['Secretaria'].fillna('Secretaria Não Informada')
    for col in ['Valor Bruto', 'Valor Liquido']:
        df_filtrado[col] = pd.to_numeric(df_filtrado[col], errors='coerce').fillna(0)

    dados_agrupados = {}
    for secretaria, group in df_filtrado.groupby('Secretaria'):
        valor_bruto_total = group['Valor Bruto'].sum()
        valor_liquido_total = group['Valor Liquido'].sum()
        ir_retido_total = valor_bruto_total * (taxa_ir_geral / 100)

        consumo_por_produto = group.groupby('Produto')['Valor Bruto'].sum()
        ir_por_produto = (consumo_por_produto * (taxa_ir_geral / 100)).to_dict()
        consumo_por_produto = consumo_por_produto.to_dict()

        dados_agrupados[secretaria] = {
            'Valor Bruto': valor_bruto_total,
            'Valor Liquido': valor_liquido_total,
            'Taxa Negativa': valor_bruto_total - valor_liquido_total,
            'IR Retido': ir_retido_total,
            'Consumo': consumo_por_produto,
            'IR por Item': ir_por_produto
        }
    return dados_agrupados

def gerar_texto_relatorio(dados_secretaria, inputs_manuais, empenho_automatico):
    """Monta a string final para uma secretaria específica."""
    consumo_str = ", ".join([f"{i+1}. {produto} R$ {valor:,.2f}" for i, (produto, valor) in enumerate(dados_secretaria['Consumo'].items())])
    ir_item_str = "; ".join([f"{i+1} - IR R$ {valor:,.2f}" for i, (produto, valor) in enumerate(dados_secretaria['IR por Item'].items())])

    relatorio = (
        f"(CONTRATO nº {inputs_manuais['contrato']}/PGE-SUGESP – {inputs_manuais['secretaria_nome']}) | "
        f"Valor Bruto: R$ {dados_secretaria['Valor Bruto']:,.2f} | "
        f"Taxa Negativa: -R$ {dados_secretaria['Taxa Negativa']:,.2f} | "
        f"Valor Líquido: R$ {dados_secretaria['Valor Liquido']:,.2f} | "
        f"IR Retido: R${dados_secretaria['IR Retido']:,.2f} | "
        f"Período: {inputs_manuais['periodo']} | "
        f"Empenho: {empenho_automatico} | "
        f"Vencimento: {inputs_manuais['vencimento']} | "
        f"DADOS BANCÁRIOS: Banco {inputs_manuais['banco']} | Ag. {inputs_manuais['agencia']} | C/C {inputs_manuais['conta']} | "
        f"CNPJ {inputs_manuais['cnpj']} – {inputs_manuais['nome_empresa']} | "
        f"Consumo: {consumo_str} | "
        f"(cada item: {ir_item_str}) | "
        f"Objeto: Prestação contínua de serviços de gerenciamento de abastecimento de combustíveis e ARLA em postos credenciados via sistema informatizado (Termo Contrato nº {inputs_manuais['termo_contrato']}). | "
        f"VALOR DA CORRETAGEM OU COMISSÃO: ZERO - CONFORME LEI COMPLEMENTAR 878/2021, Art. 260"
    )
    return relatorio


# --- 3. INTERFACE DA PÁGINA ---
st.title("SUGESP Relatório de Faturamento")
st.markdown("Gerar o texto final para faturamento a partir das informações do SIGYO.")
st.markdown("---")

st.subheader("1. Consulta à API")
col1, col2 = st.columns(2)
with col1:
    token = st.text_input("🔑 Token de Autenticação", type="password")
    nome_cliente = st.text_input("👤 Cliente Principal", value="SUGESP")
with col2:
    hoje = datetime.now()
    inicio_mes = hoje.replace(day=1)
    data_inicio = st.date_input("🗓️ Data de Início", value=inicio_mes)
    data_fim = st.date_input("🗓️ Data de Fim", value=hoje)

st.markdown("---")
st.subheader("2. Informações para o Relatório")
col_a, col_b = st.columns(2)
with col_a:
    contrato = st.text_input("Nº do Contrato", "1551/2024")
    periodo = st.text_input("Período", f"{data_inicio.strftime('%B/%Y')}")
    vencimento = st.date_input("Vencimento", hoje + timedelta(days=30))
    taxa_ir_geral = st.number_input("Taxa de IR Retido Geral (%)", min_value=0.0, value=2.4, step=0.1, format="%.2f")

with col_b:
    termo_contrato = st.text_input("Nº do Termo de Contrato (Objeto)", "1551 – 0055472251")
    nome_empresa = st.text_input("Nome da Empresa", "Uzzipay Administradora de Convênios Ltda.")
    cnpj = st.text_input("CNPJ", "05.884.660/0001-04")

st.markdown("Dados Bancários")
col_c, col_d, col_e = st.columns(3)
with col_c:
    banco = st.text_input("Banco", "552")
with col_d:
    agencia = st.text_input("Agência", "0001")
with col_e:
    conta = st.text_input("C/C", "20-5")

if st.button("Gerar Relatório", type="primary"):
    with st.spinner("Buscando e processando os dados... (Isso pode levar um momento)"):
        # Busca dados das duas APIs
        endpoint_transacoes = f"transacoes?TransacaoSearch[data_cadastro]={data_inicio.strftime('%d/%m/%Y')} - {data_fim.strftime('%d/%m/%Y')}"
        dados_transacoes, erro_transacoes = buscar_dados_api(token, endpoint_transacoes)
        dados_empenhos, erro_empenhos = buscar_dados_api(token, "empenhos?expand=contrato.empresa,grupo")

        # Verifica erros
        if erro_transacoes:
            st.error(erro_transacoes)
        elif erro_empenhos:
            st.error(erro_empenhos)
        else:
            # Processa os dados
            mapa_empenhos = mapear_empenhos(dados_empenhos)
            dados_agrupados = processar_dados_para_relatorio(dados_transacoes, nome_cliente, taxa_ir_geral)
            
            if not dados_agrupados:
                st.warning(f"Nenhuma transação encontrada para o cliente '{nome_cliente}' no período selecionado.")
            else:
                st.success(f"Dados processados! {len(dados_agrupados)} secretarias encontradas.")
                st.markdown("---")
                st.subheader("3. Resultado Final")

                texto_final_completo = ""
                
                for secretaria, dados in dados_agrupados.items():
                    # Pega o empenho do mapa, ou usa um valor padrão se não encontrar
                    empenho_automatico = mapa_empenhos.get(secretaria, "EMPENHO NÃO ENCONTRADO")
                    
                    inputs_manuais = {
                        "contrato": contrato,
                        "secretaria_nome": secretaria,
                        "periodo": periodo,
                        "vencimento": vencimento.strftime('%d/%m/%Y'),
                        "banco": banco,
                        "agencia": agencia,
                        "conta": conta,
                        "cnpj": cnpj,
                        "nome_empresa": nome_empresa,
                        "termo_contrato": termo_contrato,
                    }
                    
                    texto_gerado = gerar_texto_relatorio(dados, inputs_manuais, empenho_automatico)
                    texto_final_completo += texto_gerado + "\n\n"

                if texto_final_completo:
                    st.text_area(
                        "Texto Consolidado (pronto para copiar)", 
                        value=texto_final_completo.strip(), 
                        height=500
                    )
