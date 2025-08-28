import streamlit as st
from firebase_config import auth_client, db
import firebase_admin

st.set_page_config(page_title="Login", page_icon="🔑", layout="centered")

st.title("🔑 Sistema de Login")

# Campos de login
email = st.text_input("E-mail")
password = st.text_input("Senha", type="password")

if st.button("Login"):
    try:
        user = auth_client.sign_in_with_email_and_password(email, password)
        st.success("✅ Login realizado com sucesso!")

        # Buscar perfil no Firestore
        doc_ref = db.collection("usuarios").document(email)
        perfil = doc_ref.get()

        if perfil.exists:
            dados = perfil.to_dict()
            st.session_state["email"] = email
            st.session_state["role"] = dados.get("role", "Usuário")

            st.info(f"Você entrou como: **{st.session_state['role']}**")

            # Redireciona
            st.switch_page("usuarios.py")
        else:
            st.error("❌ Usuário não possui perfil configurado.")

    except Exception as e:
        st.error(f"Erro: {e}")
