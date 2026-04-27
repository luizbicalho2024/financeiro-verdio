# pages/10_Contratos_Clientes.py
import sys
import os
from datetime import datetime, date
import calendar
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import streamlit as st
import pandas as pd
from firebase_config import db
import user_management_db as umdb

st.set_page_config(layout="wide", page_title="Contratos e Preços por Cliente", page_icon="📝")

# --- VERIFICAÇÃO DE LOGIN E PERMISSÃO ---
if "user_info" not in st.session_state:
    st.error("🔒 Acesso Negado! Por favor, faça login para visualizar esta página.")
    st.stop()

if st.session_state.get("role", "Usuário").lower() != "admin":
    st.error("🚫 Você não tem permissão para acessar esta página. Apenas Administradores.")
    st.stop()

# --- BARRA LATERAL ---
st.sidebar.image("imgs/v-c.png", width=120)
st.sidebar.title(f"Olá, {st.session_state.get('name', 'N/A')}! 👋")
st.sidebar.markdown("---")
if st.sidebar.button("Logout"):
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.switch_page("1_Home.py")

# --- FUNÇÕES AUXILIARES ---
def add_months(sourcedate, months):
    """Adiciona meses a uma data considerando os limites do calendário (ex: ano bissexto)"""
    month = sourcedate.month - 1 + months
    year = sourcedate.year + month // 12
    month = month % 12 + 1
    day = min(sourcedate.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)

def get_contracts():
    """Busca todos os contratos salvos no banco de dados"""
    try:
        docs = db.collection("client_contracts").stream()
        return {doc.id: doc.to_dict() for doc in docs}
    except Exception as e:
        st.error(f"Erro ao buscar contratos: {e}")
        return {}

def save_contract(cliente_id, data):
    """Salva ou atualiza um contrato"""
    try:
        db.collection("client_contracts").document(cliente_id).set(data)
        return True
    except Exception as e:
        st.error(f"Erro ao salvar contrato: {e}")
        return False

def delete_contract(cliente_id):
    """Exclui um contrato"""
    try:
        db.collection("client_contracts").document(cliente_id).delete()
        return True
    except Exception as e:
        st.error(f"Erro ao excluir contrato: {e}")
        return False

# --- CARREGAMENTO DE DADOS ---
contratos = get_contracts()
# Puxa os modelos dinâmicos diretamente do estoque
model_types = umdb.get_unique_models_and_types() 
if not model_types:
    model_types = {"Nenhum Modelo Encontrado": "GPRS"} # Fallback

# --- INTERFACE PRINCIPAL ---
st.title("📝 Gestão de Contratos e Preços por Cliente")
st.markdown("Controle o termo de adesão, vencimento contratual e os valores personalizados cobrados por cada **modelo de equipamento**.")

tab1, tab2 = st.tabs(["➕ Novo / Editar Contrato", "📋 Lista de Contratos Vigentes"])

with tab1:
    st.subheader("Configuração de Contrato")
    
    opcoes_clientes = ["-- NOVO CLIENTE --"] + sorted(list(contratos.keys()))
    cliente_selecionado = st.selectbox("Selecione um cliente existente para editar ou crie um novo:", opcoes_clientes)
    
    if cliente_selecionado == "-- NOVO CLIENTE --":
        nome_cliente = st.text_input("Nome do Novo Cliente:")
        dados_atuais = {}
    else:
        nome_cliente = cliente_selecionado
        st.text_input("Nome do Cliente (Fixo):", value=nome_cliente, disabled=True)
        dados_atuais = contratos.get(cliente_selecionado, {})

    if nome_cliente:
        with st.form("form_contrato"):
            st.markdown("### 📅 Termo de Adesão e Vencimento")
            
            # Formata a data atual caso já exista
            dt_str = dados_atuais.get("ultima_atualizacao_termo", None)
            dt_obj = datetime.strptime(dt_str, "%Y-%m-%d").date() if dt_str else datetime.today().date()
            
            c1, c2, c3 = st.columns([2, 2, 2])
            with c1:
                data_atualizacao = st.date_input("Última Atualização do Termo", value=dt_obj, format="DD/MM/YYYY")
            with c2:
                prazo_meses = st.number_input("Prazo de Contrato (meses)", min_value=1, max_value=120, value=dados_atuais.get("prazo_contrato_meses", 12), step=1)
            
            # Cálculo instantâneo do vencimento
            vencimento = add_months(data_atualizacao, prazo_meses)
            
            with c3:
                # Mostramos num info box chamativo a data que o sistema calculou
                st.info(f"**Vencimento do Contrato:**\n\n🎯 {vencimento.strftime('%d/%m/%Y')}")

            st.markdown("---")
            st.markdown("### 💰 Valores Personalizados por Modelo de Rastreador")
            st.caption("Insira os valores acordados para este cliente por cada modelo. Deixe zerado (0.00) caso não haja preço específico.")
            
            precos_atuais = dados_atuais.get("precos_por_modelo", {})
            
            # Renderiza inputs de forma dinâmica de acordo com os modelos em estoque
            cols = st.columns(4)
            idx = 0
            novos_precos = {}
            for modelo in sorted(model_types.keys()):
                val_atual = float(precos_atuais.get(modelo, 0.0))
                with cols[idx % 4]:
                    novos_precos[modelo] = st.number_input(f"{modelo} (R$)", min_value=0.0, value=val_atual, format="%.2f", key=f"preco_{modelo}")
                idx += 1

            st.markdown("<br>", unsafe_allow_html=True)
            submit_btn = st.form_submit_button("💾 Salvar Contrato e Preços", type="primary")
            
            if submit_btn:
                if not nome_cliente.strip():
                    st.error("O nome do cliente não pode estar vazio.")
                else:
                    # Monta o pacote de dados para salvar no Firestore
                    dados_salvar = {
                        "cliente": nome_cliente.strip(),
                        "ultima_atualizacao_termo": data_atualizacao.strftime("%Y-%m-%d"),
                        "prazo_contrato_meses": int(prazo_meses),
                        "vencimento_contrato": vencimento.strftime("%Y-%m-%d"),
                        "precos_por_modelo": novos_precos,
                        "atualizado_em": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    if save_contract(nome_cliente.strip(), dados_salvar):
                        st.success(f"Contrato e tabela de preços de {nome_cliente} salvos com sucesso!")
                        st.rerun()

with tab2:
    st.subheader("Painel de Contratos")
    
    if not contratos:
        st.info("Nenhum contrato cadastrado na base de dados.")
    else:
        lista_tabela = []
        hoje = datetime.today().date()
        
        for k, v in contratos.items():
            venc = datetime.strptime(v['vencimento_contrato'], "%Y-%m-%d").date()
            status = "🟢 Vigente" if venc >= hoje else "🔴 Vencido"
            
            # Formata os preços maiores que zero para exibição no resumo da tabela
            precos_ativos = [f"{m}: R${p:.2f}" for m, p in v.get("precos_por_modelo", {}).items() if p > 0]
            resumo_precos = " | ".join(precos_ativos) if precos_ativos else "Nenhum valor fixo"

            lista_tabela.append({
                "Cliente": v.get("cliente", k),
                "Assinatura/Termo": datetime.strptime(v['ultima_atualizacao_termo'], "%Y-%m-%d").strftime("%d/%m/%Y"),
                "Prazo (Meses)": v.get("prazo_contrato_meses"),
                "Vencimento": venc.strftime("%d/%m/%Y"),
                "Status": status,
                "Preços (Modelos)": resumo_precos
            })
        
        # Exibe como um DataFrame interativo do Streamlit
        df_contratos = pd.DataFrame(lista_tabela)
        
        # Opcional: ordenar pelo vencimento mais próximo
        df_contratos['Vencimento_Date'] = pd.to_datetime(df_contratos['Vencimento'], format='%d/%m/%Y')
        df_contratos = df_contratos.sort_values(by='Vencimento_Date').drop(columns=['Vencimento_Date'])
        
        st.dataframe(df_contratos, use_container_width=True, hide_index=True)
        
        st.markdown("---")
        st.subheader("Ações Avançadas")
        
        cliente_excluir = st.selectbox("Deseja remover um contrato do banco de dados?", ["-- SELECIONE --"] + sorted(list(contratos.keys())))
        if st.button("🗑️ Excluir Contrato", type="primary"):
            if cliente_excluir != "-- SELECIONE --":
                if delete_contract(cliente_excluir):
                    st.success(f"O contrato de {cliente_excluir} foi excluído permanentemente.")
                    st.rerun()
            else:
                st.warning("Selecione um contrato antes de clicar em excluir.")
