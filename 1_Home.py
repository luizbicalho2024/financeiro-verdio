# 1_Home.py
import streamlit as st
from firebase_config import auth_client, db

st.set_page_config(page_title="Login", page_icon="🔑", layout="centered")

st.title("🔑 Sistema de Login Verdio")

# --- Lógica de Login ---
# Se o usuário já estiver logado, mostra mensagem e botão de logout
if 'user_info' in st.session_state:
    user_email = st.session_state['user_info']['email']
    st.success(f"Login realizado com sucesso como **{user_email}**.")
    st.info(f"Nível de acesso: **{st.session_state.get('role', 'Usuário')}**")
    
    if st.button("Logout"):
        del st.session_state['user_info']
        if 'role' in st.session_state:
            del st.session_state['role']
        st.rerun()
    st.stop()

# Formulário de login
with st.form("login_form"):
    email = st.text_input("E-mail")
    password = st.text_input("Senha", type="password")
    submit_button = st.form_submit_button("Entrar")

    if submit_button:
        if not email or not password:
            st.error("Por favor, preencha todos os campos.")
        else:
            try:
                # Tenta fazer login com e-mail e senha
                user = auth_client.sign_in_with_email_and_password(email, password)
                st.session_state['user_info'] = user # Salva informações do usuário na sessão
                
                # Após o login, busca a "role" do usuário no Firestore
                uid = user['localId']
                user_doc = db.collection('users').document(uid).get()

                if user_doc.exists:
                    st.session_state['role'] = user_doc.to_dict().get('role', 'Usuário')
                else:
                    st.session_state['role'] = 'Usuário' # Role padrão se não encontrar
                
                # Força o recarregamento da página para refletir o estado de login
                st.rerun()

            except Exception as e:
                st.error("E-mail ou senha inválidos. Verifique suas credenciais.")
