# pages/4_Relatorio_SUGESP_Detalhado.py
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
    page_title="Relatório Detalhado SUGESP",
    page_icon="📑"
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

def formatar_moeda_br(valor):
    """Formata um valor float para o padrão monetário brasileiro (ex: 1.234,56)"""
    if valor is None:
        return "0,00"
    valor_formatado = f"{float(valor):,.2f}"
    # Substitui vírgulas temporárias por X, pontos por vírgulas, e X por pontos
    return valor_formatado.replace(",", "X").replace(".", ",").replace("X", ".")

@st.cache_data(ttl=300)
def buscar_dados_api(token, endpoint):
    """Função genérica para buscar dados de um endpoint da API."""
    if not token:
        st.warning("Por favor, insira o Token de Autenticação.")
        return None
    headers = {"Authorization": f"Bearer {token}"}
    url = f"https://sigyo.uzzipay.com/api/{endpoint}"
    try:
        response = requests.get(url, headers=headers, timeout=180)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as err:
        st.error(f"Erro HTTP {response.status_code}: Token inválido ou API indisponível no endpoint '{endpoint}'.")
        return None
    except requests.exceptions.RequestException as e:
        st.error(f"Erro de conexão com o endpoint '{endpoint}': {e}")
        return None

def buscar_transacoes_em_partes(token, data_inicio, data_fim, chunk_days=7):
    """Busca transações em partes para evitar timeouts em grandes volumes."""
    todas_transacoes = []
    current_start = data_inicio
    total_dias = (data_fim - data_inicio).days + 1
    
    progress_bar = st.progress(0.0, "Iniciando coleta de transações...")
    
    dias_processados = 0
    while current_start <= data_fim:
        current_end = min(current_start + timedelta(days=chunk_days - 1), data_fim)
        
        endpoint = f"transacoes?TransacaoSearch[data_cadastro]={current_start.strftime('%d/%m/%Y')} - {current_end.strftime('%d/%m/%Y')}"
        dados = buscar_dados_api(token, endpoint)

        if dados is None:
            progress_bar.empty()
            st.error(f"Falha ao buscar transações entre {current_start.strftime('%d/%m/%Y')} e {current_end.strftime('%d/%m/%Y')}.")
            return None
        
        todas_transacoes.extend(dados)

        dias_no_chunk = (current_end - current_start).days + 1
        dias_processados += dias_no_chunk
        progresso = min(1.0, dias_processados / total_dias)
        progress_bar.progress(progresso, f"Buscando transações: {current_start.strftime('%d/%m/%Y')} a {current_end.strftime('%d/%m/%Y')}")
        
        current_start = current_end + timedelta(days=1)
    
    progress_bar.success("Coleta de transações concluída!")
    return todas_transacoes

def processar_relatorio_com_base_nas_transacoes(faturas, transacoes, empenhos, contratos, produtos, dados_bancarios, info_empresa, data_inicio, taxa_adicional, vencimento_manual, status_selecionados):
    """
    LÓGICA APRIMORADA: Gera relatórios filtrando pelo status da transação com formatação ABNT e tratamentos de None.
    """
    mapa_produtos = {p['id']: p['nome'] for p in produtos}
    mapa_contratos = {c['id']: c for c in contratos}
    mapa_empenhos = {e['id']: e['numero_empenho'] for e in empenhos}
    relatorios_finais = []
    
    meses_pt = {
        "January": "Janeiro", "February": "Fevereiro", "March": "Março", "April": "Abril", "May": "Maio", "June": "Junho",
        "July": "Julho", "August": "Agosto", "September": "Setembro", "October": "Outubro", "November": "Novembro", "December": "Dezembro"
    }

    CNPJ_PRINCIPAL = "03693136000112"

    # Filtra transações pelo status de forma segura evitando AttributeError
    transacoes_sugesp = []
    for t in transacoes:
        if not isinstance(t, dict):
            continue
            
        informacao = t.get('informacao') or {}
        if not isinstance(informacao, dict): informacao = {}
        
        cliente = informacao.get('cliente') or {}
        if not isinstance(cliente, dict): cliente = {}
        
        if cliente.get('cnpj') == CNPJ_PRINCIPAL and t.get('status') in status_selecionados:
            transacoes_sugesp.append(t)

    if not transacoes_sugesp:
        st.warning(f"Nenhuma transação com os status selecionados ({', '.join(status_selecionados)}) foi encontrada para o cliente SUGESP no período.")
        return []

    secretarias = defaultdict(list)
    for t in transacoes_sugesp:
        informacao = t.get('informacao') or {}
        if not isinstance(informacao, dict): informacao = {}
        
        search = informacao.get('search') or {}
        if not isinstance(search, dict): search = {}
        
        grupo_info = search.get('grupo') or {}
        if not isinstance(grupo_info, dict): grupo_info = {}
        
        if grupo_info and 'nome' in grupo_info:
            nome_secretaria = grupo_info['nome']
            secretarias[nome_secretaria].append(t)

    if vencimento_manual:
        vencimento = vencimento_manual.strftime('%d/%m/%Y')
    else:
        mes_referencia = data_inicio.month
        ano_referencia = data_inicio.year
        fatura_geral = next((
            f for f in faturas 
            if isinstance(f, dict) and isinstance(f.get('cliente'), dict) and f['cliente'].get('cnpj') == CNPJ_PRINCIPAL and f.get('mes_referencia') == mes_referencia and f.get('ano_referencia') == ano_referencia
        ), None)

        if not fatura_geral:
            st.warning(f"Nenhuma fatura geral da SUGESP encontrada para o período. A data de vencimento não pôde ser definida automaticamente.")
            return []
        vencimento = datetime.strptime(fatura_geral['liquidacao_prevista'], '%Y-%m-%d %H:%M:%S').strftime('%d/%m/%Y')
        
    mes_en = data_inicio.strftime('%B')
    ano = data_inicio.strftime('%Y')
    mes_pt_nome = meses_pt.get(mes_en, mes_en)
    periodo = f"{mes_pt_nome.capitalize()}/{ano}"

    for nome_secretaria, transacoes_da_secretaria in secretarias.items():
        valor_bruto = sum(float(t.get('valor_total', 0)) for t in transacoes_da_secretaria)
        ir_retido = sum(float(t.get('imposto_renda', 0)) for t in transacoes_da_secretaria)
        
        valor_taxa_adicional = valor_bruto * (taxa_adicional / 100.0)
        
        valor_liquido_original = sum(float(t.get('valor_liquido_cliente', 0)) for t in transacoes_da_secretaria)
        valor_liquido_final = valor_liquido_original - valor_taxa_adicional
        taxa_negativa = valor_bruto - valor_liquido_final
        
        consumo_por_produto = defaultdict(lambda: {'valor_bruto': 0.0, 'irrf': 0.0})
        empenhos_usados_ids = set()
        
        for t in transacoes_da_secretaria:
            produto_nome = mapa_produtos.get(t['produto_id'], "Desconhecido")
            consumo_por_produto[produto_nome]['valor_bruto'] += float(t.get('valor_total', 0))
            consumo_por_produto[produto_nome]['irrf'] += float(t.get('imposto_renda', 0))
            if t.get('empenho_id'):
                empenhos_usados_ids.add(t['empenho_id'])
        
        partes_consumo = [
            f"Combustível: {produto} | Valor Bruto: R$ {formatar_moeda_br(valores['valor_bruto'])} | Soma de VLR IRRF: R$ {formatar_moeda_br(valores['irrf'])}"
            for produto, valores in sorted(consumo_por_produto.items())
        ]
        consumo_str = " | ".join(partes_consumo)

        empenhos_str = ", ".join(sorted([mapa_empenhos[eid] for eid in empenhos_usados_ids if eid in mapa_empenhos])) or "N/A"
        
        primeira_transacao = transacoes_da_secretaria[0]
        contrato_id_transacao = primeira_transacao.get('contrato_id')
        
        if not contrato_id_transacao and primeira_transacao.get('faturamento_id_cliente'):
            fatura_da_transacao = next((f for f in faturas if f.get('id') == primeira_transacao['faturamento_id_cliente']), None)
            if fatura_da_transacao:
                configuracao = fatura_da_transacao.get('configuracao')
                if configuracao:
                    contrato_id_transacao = configuracao.get('contrato_id')

        numero_contrato = "N/A"
        if contrato_id_transacao and contrato_id_transacao in mapa_contratos:
            numero_contrato = mapa_contratos[contrato_id_transacao].get('numero', 'N/A')
        objeto_contrato = f"(Termo Contrato nº {numero_contrato})."

        texto_relatorio = (
            f"({nome_secretaria}) | "
            f"Valor Bruto: R$ {formatar_moeda_br(valor_bruto)} | "
            f"Taxa Negativa: -R$ {formatar_moeda_br(taxa_negativa)} | "
            f"Valor Líquido: R$ {formatar_moeda_br(valor_liquido_final)} | "
            f"IR Retido: R$ {formatar_moeda_br(ir_retido)} | "
            f"Período: {periodo} | "
            f"Empenho: {empenhos_str} | "
            f"Vencimento: {vencimento} | "
            f"DADOS BANCÁRIOS: Banco {dados_bancarios['banco']} | Ag. {dados_bancarios['agencia']} | C/C {dados_bancarios['conta']} | "
            f"CNPJ {info_empresa['cnpj']} – {info_empresa['nome']} | "
            f"Objeto: Prestação contínua de serviços de gerenciamento de abastecimento de combustíveis e ARLA em postos credenciados via sistema informatizado {objeto_contrato} | "
            f"VALOR DA CORRETAGEM OU COMISSÃO: ZERO - CONFORME LEI COMPLEMENTAR 878/2021, Art. 260 | "
            f"{consumo_str}"
        )
        relatorios_finais.append(texto_relatorio)
        
    return sorted(relatorios_finais)

# --- 3. INTERFACE DA PÁGINA ---
st.title("📑 Gerador de Relatório Detalhado - SUGESP")
st.markdown("Gere relatórios detalhados para as secretarias vinculadas ao cliente SUGESP.")
st.markdown("---")

st.subheader("1. Configurações da Consulta")
token = st.text_input("🔑 Token de Autenticação da API", type="password", help="Insira seu token Bearer para acessar os dados.")

col1, col2, col3 = st.columns(3)
hoje = datetime.now()
primeiro_dia_mes_atual = hoje.replace(day=1)
ultimo_dia_mes_anterior = primeiro_dia_mes_atual - timedelta(days=1)
primeiro_dia_mes_anterior = ultimo_dia_mes_anterior.replace(day=1)

with col1:
    data_inicio = st.date_input("🗓️ Data de Início (Período)", primeiro_dia_mes_anterior)
with col2:
    data_fim = st.date_input("🗓️ Data de Fim (Período)", ultimo_dia_mes_anterior)
with col3:
    # Novo seletor de status
    status_disponiveis = ["confirmada", "liquidada", "pendente", "cancelada"]
    status_selecionados = st.multiselect(
        "Status das Transações",
        options=status_disponiveis,
        default=["confirmada"],
        help="Selecione os status das transações a serem incluídos no relatório."
    )

st.markdown("---")
st.subheader("2. Informações Manuais e Ajustes")
col_a, col_b = st.columns(2)
with col_a:
    st.markdown("##### Dados da Empresa e Taxas")
    nome_empresa = st.text_input("Nome da Empresa", "Uzzipay Administradora de Convênios Ltda.")
    cnpj_empresa = st.text_input("CNPJ", "05.884.660/0001-04")
    taxa_adicional = st.number_input("Taxa Adicional (%)", min_value=0.0, value=0.0, step=0.1, format="%.2f", help="Taxa a ser calculada sobre o valor bruto. O valor será ajustado no líquido, mas não aparecerá como um item separado.")

with col_b:
    st.markdown("##### Dados Bancários e Vencimento")
    banco = st.text_input("Banco", "552")
    agencia = st.text_input("Agência", "0001")
    conta = st.text_input("Conta Corrente", "20-5")
    vencimento_manual = st.date_input("Data de Vencimento (Manual)", None, help="Deixe em branco para usar a data da API.")


if st.button("🚀 Gerar Relatórios", type="primary"):
    if not token:
        st.error("O token de autenticação é obrigatório.")
    elif not status_selecionados:
        st.error("Por favor, selecione pelo menos um status de transação para continuar.")
    else:
        with st.spinner("Buscando todos os dados da API... Isso pode levar alguns minutos."):
            faturas = buscar_dados_api(token, "fatura-recebimentos?expand=cliente,configuracao.faturamentoTipo,grupo")
            empenhos = buscar_dados_api(token, "empenhos?expand=contrato.empresa,grupo")
            contratos = buscar_dados_api(token, "contratos")
            produtos = buscar_dados_api(token, "produtos")
            transacoes = buscar_transacoes_em_partes(token, data_inicio, data_fim)

        if all(data is not None for data in [faturas, empenhos, contratos, produtos, transacoes]):
            st.success("Todos os dados foram carregados com sucesso!")
            
            with st.spinner("Processando relatórios com base nas transações..."):
                dados_bancarios = {"banco": banco, "agencia": agencia, "conta": conta}
                info_empresa = {"nome": nome_empresa, "cnpj": cnpj_empresa}

                relatorios = processar_relatorio_com_base_nas_transacoes(
                    faturas, transacoes, empenhos, contratos, produtos,
                    dados_bancarios, info_empresa, data_inicio, taxa_adicional, vencimento_manual, status_selecionados
                )
            
            st.markdown("---")
            st.subheader("3. Relatórios Gerados")

            if not relatorios:
                st.warning("Nenhum relatório pôde ser gerado. Verifique se existem transações para o cliente e os filtros selecionados.")
            else:
                st.success(f"{len(relatorios)} relatórios gerados com sucesso!")
                texto_completo_download = ""
                for rel in relatorios:
                    secretaria_nome = rel.split('|')[0].strip()[1:-1]
                    st.markdown(f"#### {secretaria_nome}")
                    st.code(rel, language=None)
                    texto_completo_download += rel + "\n\n"
                
                st.download_button(
                    label="📥 Baixar Todos os Relatórios (.txt)",
                    data=texto_completo_download.encode('utf-8'),
                    file_name=f"Relatorios_SUGESP_{datetime.now().strftime('%Y-%m-%d')}.txt",
                    mime='text/plain'
                )
