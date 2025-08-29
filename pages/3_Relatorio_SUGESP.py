# pages/8_Relatorio_API.py
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import streamlit as st
import pandas as pd
import requests
from datetime import datetime
import unicodedata
import io

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

# --- 2. FUNÇÕES DE LÓGICA ---

@st.cache_data(ttl=300)
def buscar_dados_api(token, endpoint):
    """Função genérica para buscar dados de um endpoint da API."""
    if not token:
        return None, "Por favor, insira o Token de Autenticação."
    headers = {"Authorization": f"Bearer {token}"}
    url = f"https://sigyo.uzzipay.com/api/{endpoint}"
    try:
        response = requests.get(url, headers=headers, timeout=60)
        response.raise_for_status()
        return response.json(), None
    except requests.exceptions.HTTPError as err:
        return None, f"Erro HTTP {response.status_code}: Token inválido ou API indisponível no endpoint '{endpoint}'."
    except requests.exceptions.RequestException as e:
        return None, f"Erro de conexão com o endpoint '{endpoint}': {e}"

def processar_dados_completos(dados_faturas, dados_empenhos, dados_transacoes, dados_contratos):
    """
    Orquestra o processamento e cruzamento de todas as fontes de dados.
    A fonte da verdade são as faturas de recebimento.
    """
    if not dados_faturas:
        return {}

    # Mapeia contratos e empenhos para busca rápida
    mapa_contratos = {c['id']: c.get('numero', 'N/A') for c in dados_contratos}
    mapa_empenhos = {e['grupo_id']: e.get('numero_empenho', 'NÃO ENCONTRADO') for e in dados_empenhos if 'grupo_id' in e}
    
    # Processa transações para detalhamento de consumo
    df_transacoes = pd.json_normalize(dados_transacoes)
    df_transacoes.rename(columns={
        'informacao.search.subgrupo.id': 'grupo_id',
        'informacao.produto.nome': 'Produto',
        'valor_total': 'Valor Bruto',
        'imposto_renda': 'IR Retido'
    }, inplace=True)
    
    for col in ['Valor Bruto', 'IR Retido']:
        df_transacoes[col] = pd.to_numeric(df_transacoes[col], errors='coerce').fillna(0)

    relatorios_finais = {}
    
    for fatura in dados_faturas:
        grupo_id = fatura.get('grupo_id')
        if not grupo_id:
            continue
            
        secretaria_nome = fatura.get('grupo', {}).get('grupo', {}).get('nome', 'Secretaria Desconhecida')
        
        # Filtra transações para o grupo_id e período da fatura
        data_inicio_apuracao = pd.to_datetime(fatura['inicio_apuracao']).date()
        data_fim_apuracao = pd.to_datetime(fatura['fim_apuracao']).date()
        
        df_transacoes['data_cadastro_dt'] = pd.to_datetime(df_transacoes['data_cadastro']).dt.date
        
        transacoes_secretaria = df_transacoes[
            (df_transacoes['grupo_id'] == grupo_id) &
            (df_transacoes['data_cadastro_dt'] >= data_inicio_apuracao) &
            (df_transacoes['data_cadastro_dt'] <= data_fim_apuracao)
        ]
        
        consumo = transacoes_secretaria.groupby('Produto')['Valor Bruto'].sum().round(2).to_dict()
        ir_por_item = transacoes_secretaria.groupby('Produto')['IR Retido'].sum().round(2).to_dict()

        # Encontra o contrato associado (lógica pode precisar de refinamento se a ligação não for direta)
        # Assumindo que o contrato pode ser encontrado pelo cliente_id na fatura
        contrato_id_encontrado = None
        for c in dados_contratos:
            if c.get('empresa_id') == fatura.get('cliente_id'):
                contrato_id_encontrado = c.get('id')
                break
        
        relatorios_finais[secretaria_nome] = {
            "Valor Bruto": fatura.get('valor_bruto', 0),
            "Taxa Negativa": fatura.get('valor_bruto', 0) - fatura.get('valor_liquido', 0),
            "Valor Liquido": fatura.get('valor_liquido', 0),
            "IR Retido": fatura.get('imposto_renda', 0),
            "Período": f"{datetime.strptime(fatura['inicio_apuracao'], '%Y-%m-%d %H:%M:%S').strftime('%B/%Y').capitalize()}",
            "Vencimento": datetime.strptime(fatura['liquidacao_prevista'], '%Y-%m-%d %H:%M:%S').strftime('%d/%m/%Y'),
            "Empenho": mapa_empenhos.get(grupo_id, "NÃO ENCONTRADO"),
            "Numero Contrato": mapa_contratos.get(contrato_id_encontrado, "NÃO ENCONTRADO"),
            "Consumo": consumo,
            "IR por Item": ir_por_item
        }
        
    return relatorios_finais

def gerar_texto_relatorio(dados_secretaria, inputs_manuais):
    """Monta a string final para uma secretaria específica de forma robusta."""
    consumo_str = ", ".join([f"{i+1}. {produto} R$ {valor:,.2f}" for i, (produto, valor) in enumerate(dados_secretaria['Consumo'].items())])
    ir_item_str = "; ".join([f"{i+1} - IR R$ {valor:,.2f}" for i, (produto, valor) in enumerate(dados_secretaria['IR por Item'].items())])
    
    partes = [
        f"(CONTRATO nº {dados_secretaria['Numero Contrato']}/PGE-SUGESP – {inputs_manuais['secretaria_nome']})",
        f"Valor Bruto: R$ {dados_secretaria['Valor Bruto']:,.2f}",
        f"Taxa Negativa: -R$ {dados_secretaria['Taxa Negativa']:,.2f}",
        f"Valor Líquido: R$ {dados_secretaria['Valor Liquido']:,.2f}",
        f"IR Retido: R$ {dados_secretaria['IR Retido']:,.2f}",
        f"Período: {dados_secretaria['Período']}",
        f"Empenho: {dados_secretaria['Empenho']}",
        f"Vencimento: {dados_secretaria['Vencimento']}",
        f"DADOS BANCÁRIOS: Banco {inputs_manuais['banco']} | Ag. {inputs_manuais['agencia']} | C/C {inputs_manuais['conta']}",
        f"CNPJ {inputs_manuais['cnpj']} – {inputs_manuais['nome_empresa']}",
        f"Consumo: {consumo_str}",
        f"(cada item: {ir_item_str})",
        f"Objeto: Prestação contínua de serviços de gerenciamento de abastecimento de combustíveis e ARLA em postos credenciados via sistema informatizado (Termo Contrato nº {inputs_manuais['termo_contrato']}).",
        "VALOR DA CORRETAGEM OU COMISSÃO: ZERO - CONFORME LEI COMPLEMENTAR 878/2021, Art. 260"
    ]
    return " | ".join(partes)

# --- 3. INTERFACE DA PÁGINA ---
st.title("✍️ Gerador de Relatório de Faturamento")
st.markdown("Gere o texto final para faturamento a partir das faturas do sistema.")
st.markdown("---")

st.subheader("1. Parâmetros da Consulta")
col1, col2 = st.columns(2)
with col1:
    token = st.text_input("🔑 Token de Autenticação", type="password")
    cliente_principal = st.text_input("👤 Cliente Principal (filtro inicial)", value="SUGESP")
with col2:
    # A data agora é apenas para o endpoint de transações
    hoje = datetime.now()
    inicio_mes_passado = (hoje.replace(day=1) - timedelta(days=1)).replace(day=1)
    data_inicio = st.date_input("🗓️ Data de Início (para filtro de consumo)", value=inicio_mes_passado)
    data_fim = st.date_input("🗓️ Data de Fim (para filtro de consumo)", value=hoje)

st.markdown("---")
st.subheader("2. Informações Manuais (Padrão para todos os relatórios)")
col_a, col_b = st.columns(2)
with col_a:
    termo_contrato = st.text_input("Nº Padrão do Termo de Contrato (Objeto)", "1551 – 0055472251")
    nome_empresa = st.text_input("Nome da Empresa", "Uzzipay Administradora de Convênios Ltda.")
    cnpj = st.text_input("CNPJ", "05.884.660/0001-04")
with col_b:
    banco = st.text_input("Banco", "552")
    agencia = st.text_input("Agência", "0001")
    conta = st.text_input("C/C", "20-5")

if st.button("🚀 Gerar Relatório", type="primary"):
    with st.spinner("Buscando e processando dados de todas as APIs... Este é o momento da verdade!"):
        # Busca em todas as APIs necessárias
        endpoint_transacoes = f"transacoes?TransacaoSearch[data_cadastro]={data_inicio.strftime('%d/%m/%Y')} - {data_fim.strftime('%d/%m/%Y')}"
        dados_faturas, erro_faturas = buscar_dados_api(token, "fatura-recebimentos?expand=cliente,configuracao.faturamentoTipo,grupo.grupo,status")
        dados_empenhos, erro_empenhos = buscar_dados_api(token, "empenhos?expand=contrato.empresa,grupo")
        dados_transacoes, erro_transacoes = buscar_dados_api(token, endpoint_transacoes)
        dados_contratos, erro_contratos = buscar_dados_api(token, "contratos")

        # Verifica todos os erros antes de prosseguir
        erros = [e for e in [erro_faturas, erro_empenhos, erro_transacoes, erro_contratos] if e]
        if erros:
            for erro in erros:
                st.error(erro)
        else:
            # Filtra faturas pelo cliente principal
            faturas_filtradas = [f for f in dados_faturas if cliente_principal.upper() in f.get('cliente',{}).get('nome','').upper()]
            
            dados_finais = processar_dados_completos(faturas_filtradas, dados_empenhos, dados_transacoes, dados_contratos)
            
            if not dados_finais:
                st.warning(f"Nenhuma fatura encontrada para o cliente '{cliente_principal}'.")
            else:
                st.success(f"Dados processados! {len(dados_finais)} relatórios gerados.")
                st.markdown("---")
                st.subheader("3. Resultado Final")

                texto_completo_para_download = ""

                for secretaria_original, dados in sorted(dados_finais.items()):
                    inputs_manuais = {
                        "secretaria_nome": secretaria_original, "banco": banco, 
                        "agencia": agencia, "conta": conta, "cnpj": cnpj, 
                        "nome_empresa": nome_empresa, "termo_contrato": termo_contrato,
                    }
                    texto_gerado = gerar_texto_relatorio(dados, inputs_manuais)
                    texto_completo_para_download += texto_gerado + "\n\n"
                    
                    st.markdown(f"#### {secretaria_original}")
                    if "NÃO ENCONTRADO" in texto_gerado:
                        st.warning(texto_gerado)
                    else:
                        st.code(texto_gerado, language=None)
                
                st.download_button(
                    label="📥 Baixar Relatório Completo (.txt)",
                    data=texto_completo_para_download.encode('utf-8'),
                    file_name=f"Relatorio_{cliente_principal}_{hoje.strftime('%Y-%m-%d')}.txt",
                    mime='text/plain'
                )

