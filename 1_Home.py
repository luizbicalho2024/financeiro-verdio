# 1_Home.py

import streamlit as st
import user_management_db as umdb
import streamlit_authenticator as stauth

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Sistema Financeiro",
    page_icon="💰",
    layout="centered"
)

# --- 2. CONFIGURAÇÃO DO AUTENTICADOR E DIAGNÓSTICO ---
st.info("1. Aplicação iniciada. Tentando conectar ao banco de dados...")

# Busca todos os usuários do Firestore no formato que a biblioteca precisa
credentials = umdb.fetch_all_users_for_auth()

st.info("2. Conexão com o banco de dados e busca de usuários concluída com sucesso!")

authenticator = stauth.Authenticate(
    credentials,
    st.secrets["auth"]["cookie_name"],
    st.secrets["auth"]["cookie_key"],
    cookie_expiry_days=st.secrets["auth"]["cookie_expiry_days"],
)

# --- 3. LÓGICA DE EXIBIÇÃO ---

# A. Se não houver nenhum usuário no banco de dados, mostra a tela para criar o primeiro admin
if not credentials['usernames']:
    st.image("imgs/logo.png", width=200)
    st.title("🚀 Bem-vindo ao Sistema Financeiro!")
    st.subheader("Configuração Inicial: Crie sua Conta de Administrador")
    
    with st.form("form_create_first_admin"):
        name = st.text_input("Nome Completo")
        email = st.text_input("Seu Email")
        username = st.text_input("Nome de Usuário (para login)")
        password = st.text_input("Senha", type="password")
        
        if st.form_submit_button("✨ Criar Administrador"):
            if all([name, email, username, password]):
                if umdb.add_user(username, name, email, password, "admin"):
                    umdb.log_action("INFO", "Primeiro administrador criado", {"username": username})
                    st.success("Conta de Administrador criada com sucesso!")
                    st.info("A página será recarregada para que você possa fazer o login.")
                    st.rerun()
                else:
                    st.error("Ocorreu um erro ao criar a conta. Verifique os logs.")
            else:
                st.warning("Por favor, preencha todos os campos.")
    st.stop()

# B. Processo de Login
authenticator.login(location='main')

if st.session_state["authentication_status"]:
    # --- PÁGINA DE BOAS-VINDAS PÓS-LOGIN ---
    st.sidebar.image("imgs/v-c.png", width=120)
    st.sidebar.title(f"Olá, {st.session_state['name']}! 👋")
    
    st.session_state['role'] = credentials['usernames'][st.session_state['username']]['role']
    st.session_state['email'] = credentials['usernames'][st.session_state['username']]['email']
    
    st.sidebar.info(f"**Nível de Acesso:** {st.session_state.get('role', 'N/A').capitalize()}")
    authenticator.logout('Logout', 'sidebar')
    st.sidebar.markdown("---")

    st.title("Bem-vindo ao Sistema Financeiro! 🚀")
    st.markdown("---")
    st.header("Apresentação do Sistema")
    st.write("Navegue entre as funcionalidades no menu lateral.")

elif st.session_state["authentication_status"] is False:
    st.error('Usuário ou senha incorreto(s).')
elif st.session_state["authentication_status"] is None:
    st.image("imgs/logo.png", width=200)
    st.title("Login no Sistema Financeiro")
    st.info('Por favor, insira seu nome de usuário e senha para acessar.')
