# pages/2_Gerenciar_Usuarios.py
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import streamlit as st
import pandas as pd
from auth_functions import get_all_users, create_new_user, update_user_status, update_user_role

st.set_page_config(page_title="Gestão de Usuários", page_icon="👥", layout="wide")

# --- VERIFICAÇÃO DE LOGIN E PERMISSÃO (CORRIGIDO) ---
if "user_info" not in st.session_state:
    st.error("🔒 Acesso Negado! Por favor, faça login para visualizar esta página.")
    st.stop()

if st.session_state.get("role", "Usuário").lower() != "admin":
    st.error("🚫 Você não tem permissão para acessar esta página. Apenas Administradores.")
    st.stop()

# --- BARRA LATERAL PADRONIZADA ---
st.sidebar.image("imgs/v-c.png", width=120)
st.sidebar.title(f"Olá, {st.session_state.get('name', 'N/A')}! 👋")
st.sidebar.markdown("---")
if st.sidebar.button("Logout"):
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.switch_page("1_Home.py")

# --- Conteúdo da Página (sem alterações) ---
st.title("👥 Gestão de Usuários")
st.markdown("Crie, visualize e gerencie os usuários da plataforma.")

with st.expander("➕ Cadastrar Novo Usuário", expanded=False):
    with st.form("novo_usuario_form", clear_on_submit=True):
        novo_email = st.text_input("E-mail do novo usuário")
        senha = st.text_input("Senha", type="password")
        role = st.selectbox("Nível de Acesso", ["Usuário", "Admin"], index=0)
        submit_button = st.form_submit_button("Criar Usuário")

        if submit_button:
            if not novo_email or not senha:
                st.warning("Por favor, preencha todos os campos.")
            elif "@" not in novo_email or "." not in novo_email:
                st.error("E-mail inválido.")
            else:
                if create_new_user(novo_email, senha, role):
                    st.rerun()
st.markdown("---")
st.subheader("Lista de Usuários Cadastrados")
try:
    users_list = get_all_users()
    if not users_list:
        st.info("Nenhum usuário encontrado.")
    else:
        for user in users_list:
            st.markdown(f"**E-mail:** {user['email']}")
            col1, col2, col3 = st.columns([2, 2, 1])
            with col1:
                new_role = st.selectbox("Nível", ["Usuário", "Admin"], index=["Usuário", "Admin"].index(user['role']), key=f"role_{user['uid']}")
                if new_role != user['role']:
                    if update_user_role(user['uid'], new_role):
                        st.rerun()
            with col2:
                if user['disabled']:
                    if st.button("✅ Reativar Usuário", key=f"enable_{user['uid']}"):
                        update_user_status(user['uid'], is_disabled=False)
                        st.rerun()
                else:
                    if st.button("❌ Desabilitar Usuário", key=f"disable_{user['uid']}", type="primary"):
                        if user['email'] == st.session_state['user_info']['email']:
                            st.error("Você não pode desabilitar a si mesmo.")
                        else:
                            update_user_status(user['uid'], is_disabled=True)
                            st.rerun()
            with col3:
                st.write(f"Status: {'Inativo' if user['disabled'] else 'Ativo'}")
            st.markdown("---")
except Exception as e:
    st.error(f"Ocorreu um erro ao carregar os usuários: {e}")
