# pages/8_Relatorio_API.py (ou 3_Relatorio_SUGESP.py)
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
import unicodedata

# --- 1. CONFIGURAÇÃO DA PÁGINA E AUTENTICAÇÃO ---
st.set_page_config(
    layout="wide",
    page_title="Gerador de Relatório de Faturamento",
    page_icon="✍️"
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


# --- DICIONÁRIO DE MAPEAMENTO MANUAL ---
# Se uma secretaria da API de transações não encontra um empenho,
# adicione o nome dela aqui e, ao lado, o nome correspondente da API de empenhos.
MAPEAMENTO_SECRETARIAS = {
    "POLICIA CIVIL": "POLÍCIA CIVIL",
    "CORPO DE BOMBEIROS MILITAR DE RONDONIA": "CORPO DE BOMBEIROS MILITAR",
    "EMATER": "EMATER-RO",
    # Adicione outras correspondências aqui conforme necessário. Exemplo:
    # "NOME_NA_API_TRANSACOES": "NOME_NA_API_EMPENHOS",
}


# --- 2. FUNÇÕES DE LÓGICA ---

def normalizar_texto(texto):
    """Remove acentos e converte para maiúsculas para uma comparação robusta."""
    if not isinstance(texto, str):
        return ""
    return "".join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn').upper()

@st.cache_data(ttl=600)
def buscar_dados_api(token, endpoint):
    """Função genérica para buscar dados de um endpoint da API."""
    if not token:
        return None, "Por favor, insira o Token de Autenticação."
    headers = {"Authorization": f"Bearer {token}"}
    url = f"https://sigyo.uzzipay.com/api/{endpoint}"
    try:
        response = requests.get(url, headers=headers, timeout=45)
        response.raise_for_status()
        return response.json(), None
    except requests.exceptions.HTTPError as err:
        return None, f"Erro HTTP {response.status_code}: Token inválido ou API indisponível no endpoint '{endpoint}'."
    except requests.exceptions.RequestException as e:
        return None, f"Erro de conexão com o endpoint '{endpoint}': {e}"

def mapear_empenhos(dados_empenhos):
    """Cria um dicionário mapeando o nome NORMALIZADO da secretaria ao seu número de empenho."""
    mapa = {}
    if not dados_empenhos:
        return mapa, []
    
    nomes_originais_empenhos = []
    for empenho in dados_empenhos:
        if empenho.get('grupo') and empenho['grupo'].get('nome'):
            secretaria_original = empenho['grupo']['nome']
            nomes_originais_empenhos.append(secretaria_original) # Guarda o nome original para debug
            secretaria_normalizada = normalizar_texto(secretaria_original)
            numero_empenho = empenho.get('numero_empenho', 'Não encontrado')
            
            if secretaria_normalizada not in mapa:
                mapa[secretaria_normalizada] = []
            mapa[secretaria_normalizada].append(numero_empenho)
    
    for secretaria, lista_empenhos in mapa.items():
        mapa[secretaria] = " / ".join(filter(None, lista_empenhos))
        
    return mapa, list(set(nomes_originais_empenhos))

def processar_dados_para_relatorio(dados_transacoes, nome_cliente_principal):
    """Filtra e agrupa os dados por secretaria, usando os valores diretamente da API de transações."""
    if not dados_transacoes:
        return None
    df = pd.json_normalize(dados_transacoes)
    df.rename(columns={
        'informacao.cliente.nome': 'Cliente',
        'informacao.search.subgrupo.nome': 'Secretaria',
        'valor_total': 'Valor Bruto',
        'valor_liquido_cliente': 'Valor Liquido',
        'informacao.produto.nome': 'Produto',
        'imposto_renda': 'IR Retido',
        'valor_taxa_cliente': 'Taxa Negativa'
    }, inplace=True)
    df_filtrado = df[df['Cliente'].str.contains(nome_cliente_principal, case=False, na=False)].copy()
    if df_filtrado.empty:
        return {}
    df_filtrado['Secretaria'] = df_filtrado['Secretaria'].fillna('Secretaria Não Informada')
    for col in ['Valor Bruto', 'Valor Liquido', 'IR Retido', 'Taxa Negativa']:
        df_filtrado[col] = pd.to_numeric(df_filtrado[col], errors='coerce').fillna(0)
    dados_agrupados = {}
    for secretaria, group in df_filtrado.groupby('Secretaria'):
        dados_agrupados[secretaria] = {
            'Valor Bruto': group['Valor Bruto'].sum(),
            'Valor Liquido': group['Valor Liquido'].sum(),
            'Taxa Negativa': group['Taxa Negativa'].sum(),
            'IR Retido': group['IR Retido'].sum(),
            'Consumo': group.groupby('Produto')['Valor Bruto'].sum().to_dict(),
            'IR por Item': group.groupby('Produto')['IR Retido'].sum().to_dict()
        }
    return dados_agrupados

def gerar_texto_relatorio(dados_secretaria, inputs_manuais, empenho_automatico):
    """Monta a string final para uma secretaria específica."""
    consumo_str = ", ".join([f"{i+1}. {produto} R$ {valor:,.2f}" for i, (produto, valor) in enumerate(dados_secretaria['Consumo'].items())])
    ir_item_str = "; ".join([f"{i+1} - IR R$ {valor:,.2f}" for i, (produto, valor) in enumerate(dados_secretaria['IR por Item'].items()) if produto in dados_secretaria['Consumo']])
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
st.title("✍️ Gerador de Relatório de Faturamento")
st.markdown("Gere o texto final para faturamento a partir dos dados da API e informações manuais.")
st.markdown("---")

# ... (O resto da interface permanece igual) ...
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
st.subheader("2. Informações Manuais para o Relatório")

meses_em_portugues = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
    5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
    9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
}
nome_mes = meses_em_portugues.get(data_inicio.month, "")
periodo_formatado = f"{nome_mes.capitalize()}/{data_inicio.year}"

col_a, col_b = st.columns(2)
with col_a:
    contrato = st.text_input("Nº do Contrato", "1551/2024")
    periodo = st.text_input("Período", value=periodo_formatado)
    vencimento = st.date_input("Vencimento", hoje + timedelta(days=30))

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


if st.button("🚀 Gerar Texto do Relatório", type="primary"):
    with st.spinner("Buscando e processando os dados... (Isso pode levar um momento)"):
        endpoint_transacoes = f"transacoes?TransacaoSearch[data_cadastro]={data_inicio.strftime('%d/%m/%Y')} - {data_fim.strftime('%d/%m/%Y')}"
        dados_transacoes, erro_transacoes = buscar_dados_api(token, endpoint_transacoes)
        dados_empenhos, erro_empenhos = buscar_dados_api(token, "empenhos?expand=contrato.empresa,grupo")

        if erro_transacoes:
            st.error(erro_transacoes)
        elif erro_empenhos:
            st.error(erro_empenhos)
        else:
            mapa_empenhos, nomes_empenhos_api = mapear_empenhos(dados_empenhos)
            dados_agrupados = processar_dados_para_relatorio(dados_transacoes, nome_cliente)
            
            if not dados_agrupados:
                st.warning(f"Nenhuma transação encontrada para o cliente '{nome_cliente}' no período selecionado.")
            else:
                st.success(f"Dados processados! {len(dados_agrupados)} secretarias encontradas.")
                st.markdown("---")
                st.subheader("3. Resultado Final")

                secretarias_sem_empenho = []

                for secretaria_original, dados in sorted(dados_agrupados.items()):
                    secretaria_normalizada = normalizar_texto(secretaria_original)
                    empenho_automatico = mapa_empenhos.get(secretaria_normalizada)

                    # Lógica de fallback usando o mapeamento manual
                    if not empenho_automatico:
                        nome_mapeado = MAPEAMENTO_SECRETARIAS.get(secretaria_normalizada)
                        if nome_mapeado:
                            empenho_automatico = mapa_empenhos.get(normalizar_texto(nome_mapeado))
                    
                    if not empenho_automatico:
                        empenho_automatico = "EMPENHO NÃO ENCONTRADO"
                        secretarias_sem_empenho.append(secretaria_original)

                    inputs_manuais = {
                        "contrato": contrato, "secretaria_nome": secretaria_original,
                        "periodo": periodo, "vencimento": vencimento.strftime('%d/%m/%Y'),
                        "banco": banco, "agencia": agencia, "conta": conta,
                        "cnpj": cnpj, "nome_empresa": nome_empresa,
                        "termo_contrato": termo_contrato,
                    }
                    
                    texto_gerado = gerar_texto_relatorio(dados, inputs_manuais, empenho_automatico)
                    
                    st.markdown(f"#### {secretaria_original}")
                    if empenho_automatico == "EMPENHO NÃO ENCONTRADO":
                        st.warning(texto_gerado)
                    else:
                        st.code(texto_gerado, language=None)
                
                # Exibe um resumo das secretarias sem empenho para facilitar o mapeamento
                if secretarias_sem_empenho:
                    st.markdown("---")
                    st.error("As seguintes secretarias não encontraram um empenho correspondente:")
                    col_debug1, col_debug2 = st.columns(2)
                    with col_debug1:
                        st.write("**Nomes na API de Transações (copie daqui):**")
                        st.json(secretarias_sem_empenho)
                    with col_debug2:
                        st.write("**Nomes disponíveis na API de Empenhos (cole aqui):**")
                        st.json(sorted(nomes_empenhos_api))
