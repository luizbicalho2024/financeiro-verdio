# pages/2_Gerenciar_Usuarios.py
import streamlit as st
from auth_functions import initialize_firebase, create_user, get_all_users, update_user_profile

# --- INICIALIZAÇÃO E VERIFICAÇÃO DE PERMISSÃO ---
st.set_page_config(page_title="Gerenciar Usuários", layout="wide")
st.title("Painel de Gerenciamento de Usuários")

# Inicializa o Firebase
auth, db = initialize_firebase()

# Verifica se o usuário está logado e se é Admin
if 'user' not in st.session_state or st.session_state.user.get('role') != 'Admin':
    st.error("Acesso restrito. Esta página é apenas para administradores.")
    st.stop()

# Se a inicialização falhar, interrompe a execução
if not auth or not db:
    st.stop()

# --- INTERFACE DO PAINEL DE ADMIN ---

tab1, tab2 = st.tabs(["Gerenciar Usuários Existentes", "Adicionar Novo Usuário"])

with tab1:
    st.subheader("Lista de Usuários")
    all_users = get_all_users(db)
    if not all_users:
        st.write("Nenhum usuário encontrado.")
    else:
        # Cria um cabeçalho para a tabela
        col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
        col1.write("**Email**")
        col2.write("**Perfil**")
        col3.write("**Status**")
        col4.write("**Ações**")
        st.divider()

        for uid, profile in all_users.items():
            with st.container():
                col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
                
                with col1:
                    st.write(profile.get('email', 'Email não informado'))
                    st.caption(f"UID: {uid}")

                with col2:
                    new_role = st.selectbox(
                        "Perfil",
                        ["Admin", "Usuário"],
                        index=0 if profile.get('role') == 'Admin' else 1,
                        key=f"role_{uid}",
                        label_visibility="collapsed"
                    )
                with col3:
                    new_status = st.selectbox(
                        "Status",
                        ["active", "disabled"],
                        index=0 if profile.get('status') == 'active' else 1,
                        key=f"status_{uid}",
                        label_visibility="collapsed"
                    )
                with col4:
                    if st.button("Salvar", key=f"save_{uid}"):
                        update_user_profile(db, uid, new_role, new_status)
                        st.rerun()

with tab2:
    st.subheader("Criar Nova Conta de Usuário")
    with st.form("create_user_form", clear_on_submit=True):
        new_email = st.text_input("Email do Novo Usuário")
        new_password = st.text_input("Senha Provisória", type="password")
        new_role = st.selectbox("Selecione o Perfil", ["Usuário", "Admin"])
        
        create_button = st.form_submit_button("Criar Usuário")
        if create_button:
            if new_email and new_password:
                create_user(auth, db, new_email, new_password, new_role)
            else:
                st.warning("Preencha todos os campos para criar um usuário.")
