# 1_Home.py
import streamlit as st
from firebase_config import auth_client, db
from auth_functions import get_user_role

def app():
    st.set_page_config(page_title="Login", page_icon="🔑", layout="centered")

    st.title("🔑 Sistema de Login")

    # Se já estiver logado, mostra informações e botão de logout
    if "authentication_status" in st.session_state and st.session_state["authentication_status"]:
        st.success(f"Você já está logado como **{st.session_state['email']}**.")
        st.info(f"Seu nível de acesso é: **{st.session_state['role']}**")
        
        if st.button("Ir para o Dashboard"):
            st.switch_page("pages/6_Faturamento.py")

        if st.button("Logout"):
            # Limpa o estado da sessão
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()
        
        st.stop()

    # Formulário de login
    with st.form("login_form"):
        email = st.text_input("E-mail")
        password = st.text_input("Senha", type="password")
        login_button = st.form_submit_button("Login")

        if login_button:
            if not email or not password:
                st.error("Por favor, preencha e-mail e senha.")
                return

            try:
                # Autentica com o Pyrebase
                user_credential = auth_client.sign_in_with_email_and_password(email, password)
                user_id_token = user_credential['idToken']
                
                # Obtém o UID do usuário a partir do token
                decoded_token = auth_client.get_account_info(user_id_token)['users'][0]
                uid = decoded_token['localId']

                # Busca o perfil e o nível de acesso no Firestore
                user_role = get_user_role(uid)

                # Define o estado da sessão
                st.session_state["authentication_status"] = True
                st.session_state["email"] = email
                st.session_state["uid"] = uid
                st.session_state["role"] = user_role
                st.session_state["name"] = email.split('@')[0].capitalize()
                
                st.rerun()

            except Exception as e:
                st.error("E-mail ou senha incorretos. Verifique suas credenciais.")
                st.error(f"Detalhe do erro: {e}", icon="ℹ️")


if __name__ == "__main__":
    app()
