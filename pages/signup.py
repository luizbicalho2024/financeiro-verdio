# signup.py

import streamlit as st
import user_management_db as umdb

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Criar Nova Conta",
    page_icon="📝",
    layout="centered"
)

# --- FUNÇÃO DE CADASTRO ---
def signup_form():
    """
    Exibe um formulário para que novos usuários possam se cadastrar.
    O cargo (role) é sempre definido como 'user' por segurança.
    """
    st.image("imgs/logo.png", width=200)
    st.title("📝 Criar Nova Conta")
    st.write("Preencha os campos abaixo para se cadastrar no sistema.")

    with st.form("signup_form", clear_on_submit=False):
        name = st.text_input("Nome Completo", key="signup_name")
        email = st.text_input("Email", key="signup_email")
        
        col1, col2 = st.columns(2)
        with col1:
            password = st.text_input("Senha", type="password", key="signup_password")
        with col2:
            confirm_password = st.text_input("Confirme a Senha", type="password", key="signup_confirm_password")

        submit_button = st.form_submit_button("Criar Conta")

        if submit_button:
            # --- Validações ---
            if not all([name, email, password, confirm_password]):
                st.warning("Por favor, preencha todos os campos.")
            elif password != confirm_password:
                st.error("As senhas não coincidem. Por favor, tente novamente.")
            elif len(password) < 6:
                st.error("A senha deve ter no mínimo 6 caracteres.")
            else:
                # --- Tentativa de Criação do Usuário ---
                # O cargo é 'user' por padrão para qualquer pessoa que se cadastre por esta página.
                # Isso é uma medida de segurança para evitar que criem contas de admin.
                success, message = umdb.create_user(email, password, name, role="user")
                
                if success:
                    st.success("Conta criada com sucesso!")
                    st.info("Agora você pode fechar esta página e fazer o login na tela principal do sistema.")
                    # Limpa o formulário visualmente, embora o estado ainda possa ser mantido
                    st.session_state.signup_name = ""
                    st.session_state.signup_email = ""
                    st.session_state.signup_password = ""
                    st.session_state.signup_confirm_password = ""
                else:
                    # Exibe o erro retornado pelo Firebase (ex: email já existe)
                    st.error(message)

# --- Executa a função do formulário ---
signup_form()
