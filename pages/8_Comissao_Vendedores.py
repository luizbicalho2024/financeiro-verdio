# pages/8_Comissao_Vendedores.py
import sys
import os
import io
import pandas as pd
import streamlit as st
from datetime import datetime

# Adiciona o diretório pai ao path para importar módulos locais
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import user_management_db as umdb
from firebase_config import db  # Importação direta para salvar os mapeamentos de vendedores

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(layout="wide", page_title="Comissões e Premiações", page_icon="💰")

# --- VERIFICAÇÃO DE LOGIN ---
if "user_info" not in st.session_state:
    st.error("🔒 Acesso Negado! Por favor, faça login para visualizar esta página.")
    st.stop()

# Apenas Admins devem ter acesso a dados financeiros sensíveis
if st.session_state.get("role", "Usuário").lower() != "admin":
    st.error("🚫 Acesso restrito a Administradores.")
    st.stop()

# --- BARRA LATERAL ---
st.sidebar.image("imgs/v-c.png", width=120)
st.sidebar.title(f"Olá, {st.session_state.get('name', 'N/A')}! 👋")
st.sidebar.markdown("---")
if st.sidebar.button("Logout"):
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.switch_page("1_Home.py")

# --- FUNÇÕES DE BANCO DE DADOS (ESPECÍFICAS DESTA PÁGINA) ---
def get_seller_mappings():
    """Busca o mapeamento de Cliente -> Vendedor no Firestore."""
    try:
        doc = db.collection("settings").document("seller_mappings").get()
        if doc.exists:
            return doc.to_dict()
        return {}
    except Exception as e:
        st.error(f"Erro ao carregar vendedores: {e}")
        return {}

def save_seller_mappings(mapping_data):
    """Salva o mapeamento de Cliente -> Vendedor."""
    try:
        db.collection("settings").document("seller_mappings").set(mapping_data, merge=True)
        st.toast("Vendedores vinculados com sucesso!", icon="✅")
        return True
    except Exception as e:
        st.error(f"Erro ao salvar vendedores: {e}")
        return False

# --- TÍTULO E INTRODUÇÃO ---
st.title("💰 Gestão de Comissões e Premiações")
st.markdown("Defina as regras de comissão, vincule vendedores aos clientes e gere os relatórios de pagamento.")

# --- 1. CONFIGURAÇÃO DE REGRAS (BASE DE CÁLCULO) ---
with st.expander("⚙️ Configuração da Base de Cálculo (Regras de Comissão)", expanded=True):
    st.info("Ajuste os valores abaixo conforme a política de premiação atual.")
    
    col_rule1, col_rule2, col_rule3 = st.columns(3)
    
    with col_rule1:
        comissao_percentual = st.number_input(
            "Comissão sobre Faturamento (%)", 
            min_value=0.0, 
            max_value=100.0, 
            value=10.0, 
            step=0.5,
            help="Porcentagem aplicada sobre o Valor Total da fatura (Recorrência)."
        )
    
    with col_rule2:
        bonus_ativacao = st.number_input(
            "Bônus por Ativação/Novo (R$)", 
            min_value=0.0, 
            value=50.00, 
            step=10.0,
            help="Valor fixo pago por cada terminal 'Proporcional' (indicativo de novas ativações no mês)."
        )
        
    with col_rule3:
        meta_minima = st.number_input(
            "Faturamento Mínimo para Comissão (R$)",
            min_value=0.0,
            value=0.0,
            help="O vendedor só recebe comissão se a fatura do cliente for superior a este valor."
        )

# --- 2. CARREGAMENTO E PREPARAÇÃO DOS DADOS ---
history_data = umdb.get_billing_history()

if not history_data:
    st.warning("Nenhum histórico de faturamento encontrado para calcular comissões.")
    st.stop()

# Carrega mapeamento de vendedores salvo
seller_map = get_seller_mappings()

df = pd.DataFrame(history_data)

# --- CORREÇÃO DE TIPOS DE DADOS (CRUCIAL PARA O DATA_EDITOR) ---
# Garante que as colunas numéricas sejam float/int e preenche nulos com 0
if 'valor_total' in df.columns:
    df['valor_total'] = pd.to_numeric(df['valor_total'], errors='coerce').fillna(0.0)
if 'terminais_cheio' in df.columns:
    df['terminais_cheio'] = pd.to_numeric(df['terminais_cheio'], errors='coerce').fillna(0).astype(int)
if 'terminais_proporcional' in df.columns:
    df['terminais_proporcional'] = pd.to_numeric(df['terminais_proporcional'], errors='coerce').fillna(0).astype(int)

df['data_geracao'] = pd.to_datetime(df['data_geracao'])
df['mes_ano'] = df['data_geracao'].dt.to_period('M').astype(str)

# Filtro de Período
st.markdown("---")
col_filt1, col_filt2 = st.columns([1, 3])
with col_filt1:
    periodos_disponiveis = sorted(df['mes_ano'].unique(), reverse=True)
    if periodos_disponiveis:
        periodo_selecionado = st.selectbox("Selecione o Mês de Competência:", periodos_disponiveis)
    else:
        st.warning("Nenhum período disponível.")
        st.stop()

# Filtra dados pelo mês
df_filtered = df[df['mes_ano'] == periodo_selecionado].copy()

# Adiciona coluna de Vendedor baseada no mapeamento salvo
# CORREÇÃO: fillna("") e astype(str) garantem que a coluna seja compatível com TextColumn
df_filtered['Vendedor'] = df_filtered['cliente'].map(seller_map).fillna("").astype(str)

# --- 3. EDITOR DE VENDEDORES ---
st.subheader(f"Vínculo de Vendedores - {periodo_selecionado}")
st.markdown("Atribua os vendedores aos clientes abaixo. **As alterações são salvas automaticamente ao clicar no botão 'Salvar' abaixo da tabela.**")

# Prepara o DataFrame para edição
df_to_edit = df_filtered[['cliente', 'valor_total', 'terminais_cheio', 'terminais_proporcional', 'Vendedor']].copy()
df_to_edit = df_to_edit.rename(columns={
    'cliente': 'Cliente',
    'valor_total': 'Faturamento (R$)',
    'terminais_cheio': 'Terminais Base',
    'terminais_proporcional': 'Novas Ativações/Prop.',
})

# Editor de Dados
edited_df = st.data_editor(
    df_to_edit,
    column_config={
        "Cliente": st.column_config.TextColumn("Cliente", disabled=True),
        "Faturamento (R$)": st.column_config.NumberColumn("Faturamento", format="R$ %.2f", disabled=True),
        "Terminais Base": st.column_config.NumberColumn("Base", disabled=True),
        "Novas Ativações/Prop.": st.column_config.NumberColumn("Ativações", disabled=True),
        "Vendedor": st.column_config.TextColumn(
            "Vendedor Responsável", 
            help="Digite o nome do vendedor"
        )
    },
    use_container_width=True,
    hide_index=True,
    num_rows="fixed"
)

# Botão para salvar os vendedores no banco
col_btn1, col_btn2 = st.columns([1, 4])
if col_btn1.button("💾 Salvar Vínculos de Vendedores", type="primary"):
    # Atualiza o dicionário de mapeamento com os novos valores
    new_mappings = dict(zip(edited_df['Cliente'], edited_df['Vendedor']))
    # Remove entradas vazias
    new_mappings = {k: v for k, v in new_mappings.items() if v and str(v).strip() != ""}
    
    # Salva no Firestore
    if save_seller_mappings(new_mappings):
        st.cache_data.clear() # Limpa cache se necessário
        st.rerun()

# --- 4. CÁLCULO E RELATÓRIO FINAL ---
st.markdown("---")
st.subheader("📊 Relatório de Comissões Calculado")

# Verifica se a coluna tem dados válidos (não vazios)
tem_vendedores = edited_df['Vendedor'].str.strip().astype(bool).any()

if not tem_vendedores:
    st.info("👆 Por favor, preencha a coluna 'Vendedor Responsável' na tabela acima e clique em Salvar para ver os cálculos.")
else:
    # Lógica de Cálculo
    # 1. Comissão por % (Recorrência)
    edited_df['Comissão Recorrência'] = edited_df.apply(
        lambda x: (x['Faturamento (R$)'] * (comissao_percentual / 100.0)) if x['Faturamento (R$)'] >= meta_minima else 0.0,
        axis=1
    )
    
    # 2. Bônus por Ativação (Baseado em terminais proporcionais como proxy de ativação)
    edited_df['Bônus Ativação'] = edited_df['Novas Ativações/Prop.'] * bonus_ativacao
    
    # 3. Total
    edited_df['Premiação Total'] = edited_df['Comissão Recorrência'] + edited_df['Bônus Ativação']
    
    # Remove linhas sem vendedor para o resumo
    df_calculado = edited_df[edited_df['Vendedor'].str.strip() != ""].copy()

    if not df_calculado.empty:
        # Agrupamento por Vendedor
        resumo_vendedor = df_calculado.groupby('Vendedor').agg({
            'Cliente': 'count',
            'Faturamento (R$)': 'sum',
            'Novas Ativações/Prop.': 'sum',
            'Comissão Recorrência': 'sum',
            'Bônus Ativação': 'sum',
            'Premiação Total': 'sum'
        }).reset_index()

        resumo_vendedor = resumo_vendedor.rename(columns={'Cliente': 'Qtd Clientes', 'Novas Ativações/Prop.': 'Qtd Ativações'})

        # Exibição dos Cards de Totais
        total_pagar = resumo_vendedor['Premiação Total'].sum()
        total_faturado_vendedores = resumo_vendedor['Faturamento (R$)'].sum()
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Total de Comissões a Pagar", f"R$ {total_pagar:,.2f}")
        c2.metric("Faturamento Base (Comissionado)", f"R$ {total_faturado_vendedores:,.2f}")
        c3.metric("Total de Ativações Bonificadas", int(resumo_vendedor['Qtd Ativações'].sum()))

        st.markdown("### Resumo por Vendedor")
        st.dataframe(
            resumo_vendedor,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Faturamento (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
                "Comissão Recorrência": st.column_config.NumberColumn(format="R$ %.2f"),
                "Bônus Ativação": st.column_config.NumberColumn(format="R$ %.2f"),
                "Premiação Total": st.column_config.NumberColumn(format="R$ %.2f"),
            }
        )

        # Botão de Exportação Excel
        def to_excel_download(df_summary, df_detailed):
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_summary.to_excel(writer, index=False, sheet_name='Resumo Vendedores')
                df_detailed.to_excel(writer, index=False, sheet_name='Detalhado por Cliente')
            return output.getvalue()

        excel_data = to_excel_download(resumo_vendedor, df_calculado)
        
        st.download_button(
            label="📥 Baixar Relatório de Comissões (Excel)",
            data=excel_data,
            file_name=f"Comissoes_Verdio_{periodo_selecionado}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
        with st.expander("Ver Detalhamento Completo (Lista de Clientes)"):
            st.dataframe(df_calculado, use_container_width=True, hide_index=True)
            
    else:
        st.warning("Nenhum vendedor atribuído neste período.")
