# pages/3_Relatorio_SUGESP.py
import sys
import os
import re
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
from collections import defaultdict
import io

# --- 1. CONFIGURAÇÃO DA PÁGINA E AUTENTICAÇÃO ---
st.set_page_config(
    layout="wide",
    page_title="Gerador de Relatório SUGESP",
    page_icon="✍️"
)

# --- VERIFICAÇÃO DE LOGIN ---
if "user_info" not in st.session_state:
    st.error("🔒 Acesso Negado! Por favor, faça login para visualizar esta página.")
    st.stop()

# --- BARRA LATERAL PADRONIZA ---
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
        response = requests.get(url, headers=headers, timeout=120)
        response.raise_for_status()
        return response.json(), None
    except requests.exceptions.HTTPError as err:
        return None, f"Erro HTTP {response.status_code}: Token inválido ou API indisponível no endpoint '{endpoint}'."
    except requests.exceptions.RequestException as e:
        return None, f"Erro de conexão com o endpoint '{endpoint}': {e}"

def buscar_transacoes_em_partes(token, data_inicio, data_fim, chunk_days=8):
    """
    Busca transações em pedaços menores para evitar erro 500 em grandes volumes de dados.
    """
    todas_transacoes = []
    current_start = data_inicio
    progress_bar = st.progress(0.0, "Iniciando coleta de transações...")
    status_text = st.empty()
    
    total_days = (data_fim - data_inicio).days + 1
    days_processed = 0

    while current_start <= data_fim:
        current_end = current_start + timedelta(days=chunk_days - 1)
        if current_end > data_fim:
            current_end = data_fim

        progress_text = f"Buscando transações de {current_start.strftime('%d/%m/%Y')} a {current_end.strftime('%d/%m/%Y')}..."
        status_text.info(progress_text)
        
        endpoint = f"transacoes?TransacaoSearch[data_cadastro]={current_start.strftime('%d/%m/%Y')} - {current_end.strftime('%d/%m/%Y')}"
        dados, erro = buscar_dados_api(token, endpoint)

        if erro:
            status_text.empty()
            progress_bar.empty()
            return None, f"Erro ao buscar o lote de {current_start.strftime('%d/%m/%Y')} a {current_end.strftime('%d/%m/%Y')}: {erro}"
        
        if dados:
            todas_transacoes.extend(dados)

        days_in_chunk = (current_end - current_start).days + 1
        days_processed += days_in_chunk
        progress = min(1.0, days_processed / total_days)
        progress_bar.progress(progress, text=progress_text)
        
        current_start = current_end + timedelta(days=1)
    
    status_text.success("Coleta de transações concluída!")
    progress_bar.empty()
    return todas_transacoes, None


def processar_dados_completos(dados_faturas, dados_empenhos, dados_transacoes, dados_contratos):
    """
    Orquestra o processamento e cruzamento de todas as fontes de dados.
    """
    if not dados_faturas:
        return {}

    mapa_contratos = {c['id']: c.get('numero', 'N/A') for c in dados_contratos if 'id' in c}
    
    mapa_empenhos = defaultdict(list)
    for e in dados_empenhos:
        if e and isinstance(e, dict) and 'grupo_id' in e and e.get('numero_empenho'):
            mapa_empenhos[e['grupo_id']].append(e['numero_empenho'])

    df_transacoes = pd.json_normalize(dados_transacoes)
    if 'informacao.search.subgrupo.id' in df_transacoes.columns:
        df_transacoes['grupo_id'] = df_transacoes['informacao.search.subgrupo.id'].fillna(df_transacoes.get('informacao.search.grupo.id'))
    elif 'informacao.search.grupo.id' in df_transacoes.columns:
        df_transacoes['grupo_id'] = df_transacoes['informacao.search.grupo.id']
    else:
        df_transacoes['grupo_id'] = None
        
    df_transacoes.rename(columns={
        'informacao.produto.nome': 'Produto',
        'valor_total': 'Valor Bruto',
        'imposto_renda': 'IR Retido'
    }, inplace=True)
    
    for col in ['Valor Bruto', 'IR Retido', 'grupo_id']:
        if col in df_transacoes.columns:
            df_transacoes[col] = pd.to_numeric(df_transacoes[col], errors='coerce').fillna(0)

    relatorios_finais = {}
    
    for fatura in dados_faturas:
        grupo_obj = fatura.get('grupo')
        if not grupo_obj or not isinstance(grupo_obj, dict):
            continue

        grupo_id = grupo_obj.get('id')
        if not grupo_id:
            continue
            
        secretaria_nome = grupo_obj.get('nome', 'Secretaria Desconhecida')
        
        data_inicio_apuracao = pd.to_datetime(fatura['inicio_apuracao']).date()
        data_fim_apuracao = pd.to_datetime(fatura['fim_apuracao']).date()
        
        df_transacoes['data_cadastro_dt'] = pd.to_datetime(df_transacoes['data_cadastro'], errors='coerce').dt.date
        
        transacoes_secretaria = df_transacoes[
            (df_transacoes['grupo_id'] == grupo_id) &
            (df_transacoes['data_cadastro_dt'] >= data_inicio_apuracao) &
            (df_transacoes['data_cadastro_dt'] <= data_fim_apuracao)
        ]
        
        consumo_bruto = transacoes_secretaria.groupby('Produto')['Valor Bruto'].sum().round(2).to_dict()
        consumo_ir = transacoes_secretaria.groupby('Produto')['IR Retido'].sum().round(2).to_dict()

        contrato_id_fatura = fatura.get('configuracao', {}).get('contrato_id')
        numero_contrato = mapa_contratos.get(contrato_id_fatura, "NÃO ENCONTRADO")

        valor_bruto = float(fatura.get('valor_bruto', 0))
        valor_liquido = float(fatura.get('valor_liquido', 0))
        ir_retido = float(fatura.get('imposto_renda', 0))

        empenhos_str = ", ".join(sorted(list(set(mapa_empenhos.get(grupo_id, ["NÃO ENCONTRADO"])))))

        relatorios_finais[secretaria_nome] = {
            "Secretaria": secretaria_nome,
            "Valor Bruto": valor_bruto,
            "Taxa Negativa": round(valor_bruto - valor_liquido, 2),
            "Valor Liquido": valor_liquido,
            "IR Retido": ir_retido,
            "Período": f"{datetime.strptime(fatura['inicio_apuracao'], '%Y-%m-%d %H:%M:%S').strftime('%B/%Y').capitalize()}",
            "Vencimento": datetime.strptime(fatura['liquidacao_prevista'], '%Y-%m-%d %H:%M:%S').strftime('%d/%m/%Y'),
            "Empenho": empenhos_str,
            "Numero Contrato": numero_contrato,
            "Consumo Bruto": consumo_bruto,
            "Consumo IR": consumo_ir
        }
        
    return relatorios_finais

def gerar_texto_relatorio(dados_secretaria, inputs_manuais):
    """Monta a string final para uma secretaria específica no novo formato."""
    partes_principais = [
        f"({dados_secretaria['Secretaria']})",
        f"Valor Bruto: R$ {dados_secretaria['Valor Bruto']:,.2f}",
        f"Taxa Negativa: -R$ {dados_secretaria['Taxa Negativa']:,.2f}",
        f"Valor Líquido: R$ {dados_secretaria['Valor Liquido']:,.2f}",
        f"IR Retido: R$ {dados_secretaria['IR Retido']:,.2f}",
        f"Período: {dados_secretaria['Período']}",
        f"Empenho: {dados_secretaria['Empenho']}",
        f"Vencimento: {dados_secretaria['Vencimento']}",
        f"DADOS BANCÁRIOS: Banco {inputs_manuais['banco']} | Ag. {inputs_manuais['agencia']} | C/C {inputs_manuais['conta']}",
        f"CNPJ {inputs_manuais['cnpj']} – {inputs_manuais['nome_empresa']}",
        f"Objeto: Prestação contínua de serviços de gerenciamento de abastecimento de combustíveis e ARLA em postos credenciados via sistema informatizado (Termo Contrato nº {inputs_manuais['termo_contrato']}).",
        "VALOR DA CORRETAGEM OU COMISSÃO: ZERO - CONFORME LEI COMPLEMENTAR 878/2021, Art. 260"
    ]
    
    partes_consumo = []
    for produto, valor_bruto in dados_secretaria['Consumo Bruto'].items():
        valor_ir = dados_secretaria['Consumo IR'].get(produto, 0)
        partes_consumo.append(
            f"Combustível: {produto} | Valor Bruto: R$ {valor_bruto:,.2f} | Soma de VLR IRRF: R$ {valor_ir:,.2f}"
        )

    relatorio_completo = " | ".join(partes_principais)
    if partes_consumo:
        relatorio_completo += " | " + " | ".join(partes_consumo)
    
    return relatorio_completo


# --- 3. INTERFACE DA PÁGINA ---
st.title("✍️ Gerador de Relatório de Faturamento - SUGESP")
st.markdown("Gere o texto final para faturamento a partir das faturas do sistema.")
st.markdown("---")

st.subheader("1. Parâmetros da Consulta")
col1, col2 = st.columns(2)
with col1:
    token = st.text_input("🔑 Token de Autenticação", type="password")
    cliente_cnpj = st.text_input("👤 CNPJ do Cliente (filtro inicial)", value="03693136000112")
with col2:
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
    
    st.info("Buscando dados de faturas, empenhos e contratos...")
    dados_faturas, erro_faturas = buscar_dados_api(token, "fatura-recebimentos?expand=cliente,configuracao.faturamentoTipo,grupo")
    dados_empenhos, erro_empenhos = buscar_dados_api(token, "empenhos?expand=contrato.empresa,grupo")
    dados_contratos, erro_contratos = buscar_dados_api(token, "contratos")
    
    dados_transacoes, erro_transacoes = buscar_transacoes_em_partes(token, data_inicio, data_fim)

    erros = [e for e in [erro_faturas, erro_empenhos, erro_transacoes, erro_contratos] if e]
    if erros:
        for erro in erros:
            st.error(erro)
    else:
        with st.spinner("Processando e cruzando todos os dados..."):
            clean_cnpj_input = re.sub(r'[^\d]', '', cliente_cnpj)
            faturas_filtradas = [
                f for f in dados_faturas 
                if f and isinstance(f, dict) and re.sub(r'[^\d]', '', f.get('cliente', {}).get('cnpj', '')) == clean_cnpj_input
            ]
            
            dados_finais = processar_dados_completos(faturas_filtradas, dados_empenhos, dados_transacoes, dados_contratos)
        
        if not dados_finais:
            st.warning(f"Nenhuma fatura encontrada para o cliente com CNPJ '{cliente_cnpj}'.")
        else:
            st.success(f"Dados processados! {len(dados_finais)} relatórios gerados.")
            st.markdown("---")
            st.subheader("3. Resultado Final")

            texto_completo_para_download = ""

            for secretaria_original, dados in sorted(dados_finais.items()):
                inputs_manuais = {
                    "banco": banco, "agencia": agencia, "conta": conta, 
                    "cnpj": cnpj, "nome_empresa": nome_empresa, 
                    "termo_contrato": termo_contrato,
                }
                texto_gerado = gerar_texto_relatorio(dados, inputs_manuais)
                texto_completo_para_download += texto_gerado + "\n\n"
                
                st.markdown(f"#### {secretaria_original}")
                st.code(texto_gerado, language=None)
            
            st.download_button(
                label="📥 Baixar Relatório Completo (.txt)",
                data=texto_completo_para_download.encode('utf-8'),
                file_name=f"Relatorio_{cliente_cnpj}_{hoje.strftime('%Y-%m-%d')}.txt",
                mime='text/plain'
            )
