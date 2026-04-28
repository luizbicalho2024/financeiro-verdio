# pages/7_Contratos_Clientes.py
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import streamlit as st
import pandas as pd
from datetime import datetime
import plotly.express as px
from firebase_config import db
import user_management_db as umdb

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(layout="wide", page_title="Gestão de Contratos", page_icon="📝")

# --- FUNÇÕES DE AUXÍLIO ---
def sanitize_id(name):
    """Substitui barras por traços para evitar erro de path do Firestore"""
    return name.strip().replace('/', '-')

def obter_status(data_vencimento):
    """Calcula se o contrato está vigente ou vencido"""
    if not data_vencimento:
        return "⚪ S/ Data"
    hoje = datetime.now().date()
    venc = pd.to_datetime(data_vencimento).date()
    return "🟢 Vigente" if venc >= hoje else "🔴 Vencido"

# --- LÓGICA DE CARREGAMENTO ---
if "user_info" not in st.session_state:
    st.error("🔒 Por favor, faça login.")
    st.stop()

# Inicializa estados para edição
if 'edit_mode' not in st.session_state:
    st.session_state.edit_mode = False
if 'edit_data' not in st.session_state:
    st.session_state.edit_data = None

# --- 1. CABEÇALHO ---
st.title("📝 Gestão de Contratos de Clientes")
st.markdown("---")

# --- 2. FORMULÁRIO DE CADASTRO / EDIÇÃO ---
with st.expander(f"➕ { 'Editar Contrato' if st.session_state.edit_mode else 'Cadastrar Novo Contrato'}", expanded=st.session_state.edit_mode):
    with st.form("form_contrato", clear_on_submit=True):
        # Se estiver editando, bloqueia o nome do cliente para não criar um novo doc sem querer
        default_cliente = st.session_state.edit_data['cliente'] if st.session_state.edit_mode else ""
        cliente_nome = st.text_input("Nome do Cliente (Igual ao Relatório)", value=default_cliente, disabled=st.session_state.edit_mode)
        
        c1, c2 = st.columns(2)
        # Preços
        default_gprs = float(st.session_state.edit_data['precos_por_tipo'].get('GPRS', 0.0)) if st.session_state.edit_mode else 0.0
        default_sat = float(st.session_state.edit_data['precos_por_tipo'].get('SATELITE', 0.0)) if st.session_state.edit_mode else 0.0
        
        preco_gprs = c1.number_input("Valor Mensal GPRS (R$)", min_value=0.0, value=default_gprs, format="%.2f")
        preco_sat = c2.number_input("Valor Mensal Satelital (R$)", min_value=0.0, value=default_sat, format="%.2f")
        
        # Vencimento
        default_venc = pd.to_datetime(st.session_state.edit_data['data_vencimento']).date() if st.session_state.edit_mode else datetime.now().date()
        data_vencimento = st.date_input("Data de Vencimento do Contrato", value=default_venc)
        
        col_btn1, col_btn2 = st.columns([1, 5])
        submit = col_btn1.form_submit_button("Salvar Contrato")
        
        if st.session_state.edit_mode:
            if col_btn2.form_submit_button("Cancelar Edição"):
                st.session_state.edit_mode = False
                st.session_state.edit_data = None
                st.rerun()

        if submit:
            if not cliente_nome:
                st.error("O nome do cliente é obrigatório.")
            else:
                try:
                    doc_id = sanitize_id(cliente_nome)
                    contrato_data = {
                        "cliente": cliente_nome,
                        "precos_por_tipo": {
                            "GPRS": preco_gprs,
                            "SATELITE": preco_sat
                        },
                        "data_vencimento": data_vencimento.strftime('%Y-%m-%d'),
                        "updated_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    }
                    db.collection("client_contracts").document(doc_id).set(contrato_data, merge=True)
                    st.success(f"Contrato de {cliente_nome} salvo com sucesso!")
                    st.session_state.edit_mode = False
                    st.session_state.edit_data = None
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao salvar contrato: {e}")

# --- 3. PAINEL DE CONTRATOS ---
st.subheader("📋 Painel de Contratos Ativos")

# Busca dados do Firestore
try:
    contracts_ref = db.collection("client_contracts").stream()
    list_contracts = []
    for doc in contracts_ref:
        data = doc.to_dict()
        data['id'] = doc.id
        data['status'] = obter_status(data.get('data_vencimento'))
        list_contracts.append(data)
    
    if list_contracts:
        df_contracts = pd.DataFrame(list_contracts)
        
        # Layout: Tabela e Gráfico lado a lado
        col_tabela, col_grafico = st.columns([2, 1])
        
        with col_tabela:
            # Mostrando a tabela com botões de ação (Edição e Exclusão)
            for _, row in df_contracts.iterrows():
                with st.container(border=True):
                    c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
                    c1.markdown(f"**{row['cliente']}**")
                    c2.markdown(f"Venc: {row['data_vencimento']}")
                    c3.markdown(row['status'])
                    
                    # Botões de Ação
                    btn_edit, btn_del = c4.columns(2)
                    if btn_edit.button("✏️", key=f"edit_{row['id']}", help="Editar Contrato"):
                        st.session_state.edit_mode = True
                        st.session_state.edit_data = row
                        st.rerun()
                        
                    if btn_del.button("🗑️", key=f"del_{row['id']}", help="Excluir Contrato"):
                        try:
                            db.collection("client_contracts").document(row['id']).delete()
                            st.toast(f"Contrato de {row['cliente']} removido!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao deletar: {e}")
                    
                    # Detalhes de preço escondidos
                    with st.expander("Ver Preços"):
                        st.write(f"GPRS: R$ {row['precos_por_tipo'].get('GPRS', 0.0):.2f}")
                        st.write(f"SATELITE: R$ {row['precos_por_tipo'].get('SATELITE', 0.0):.2f}")

        with col_grafico:
            st.markdown("### Status dos Contratos")
            # Contagem de status para o gráfico
            status_counts = df_contracts['status'].value_counts().reset_index()
            status_counts.columns = ['Status', 'Quantidade']
            
            # Cores personalizadas
            color_map = {
                "🟢 Vigente": "#22c55e",
                "🔴 Vencido": "#ef4444",
                "⚪ S/ Data": "#94a3b8"
            }
            
            fig = px.pie(
                status_counts, 
                values='Quantidade', 
                names='Status', 
                hole=0.5, # Espaçamento central de 50%
                color='Status',
                color_discrete_map=color_map
            )
            
            fig.update_traces(textposition='inside', textinfo='percent+label')
            fig.update_layout(showlegend=False, height=350, margin=dict(t=0, b=0, l=0, r=0))
            
            st.plotly_chart(fig, use_container_width=True)
            
            # Resumo numérico abaixo do gráfico
            st.write(f"**Total de Contratos:** {len(df_contracts)}")

    else:
        st.info("Nenhum contrato cadastrado ainda.")

except Exception as e:
    st.error(f"Erro ao carregar painel: {e}")

# --- BARRA LATERAL ---
st.sidebar.markdown("---")
if st.sidebar.button("Voltar para Home"):
    st.switch_page("1_Home.py")
