# app.py
import streamlit as st
from auth_functions import initialize_firebase, login_user

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Sistema de Login", layout="centered")

# --- INICIALIZAÇÃO DO FIREBASE ---
auth, db = initialize_firebase()

# Se a inicialização falhar, interrompe a execução
if not auth or not db:
    st.stop()

# --- LÓGICA DE EXIBIÇÃO ---

# Se o usuário não estiver logado, mostra a tela de Login
if 'user' not in st.session_state:
    st.title("Sistema com Autenticação Firebase")
    st.header("Faça seu Login")
    with st.form("login_form"):
        email = st.text_input("Email")
        password = st.text_input("Senha", type="password")
        login_button = st.form_submit_button("Login")

        if login_button:
            if email and password:
                user = login_user(auth, db, email, password)
                if user:
                    st.session_state.user = user
                    st.rerun()
            else:
                st.warning("Por favor, preencha todos os campos.")

# Se o usuário estiver logado
else:
    user_info = st.session_state.user
    user_email = user_info.get('email', 'Email não disponível')
    user_role = user_info.get('role', 'Usuário')

    st.sidebar.header(f"Bem-vindo(a)!")
    st.sidebar.write(f"**Email:** {user_email}")
    st.sidebar.write(f"**Perfil:** {user_role}")

    if st.sidebar.button("Logout"):
        del st.session_state.user
        st.rerun()

    # --- CONTEÚDO PRINCIPAL ---
    st.title("Página Principal")
    st.write("Navegue pelo menu na barra lateral para acessar as funcionalidades.")
    
    if user_role == 'Admin':
        st.info("Como administrador, você tem acesso à página 'Gerenciar Usuários'.")
    else:
        st.success("Você está logado como Usuário.")
