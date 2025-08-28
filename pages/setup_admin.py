# pages/setup_admin.py
import streamlit as st
from auth_functions import create_new_user

st.set_page_config(page_title="Setup Admin", page_icon="🔑", layout="centered")

st.title("🔑 Criar Primeiro Usuário Admin")
st.warning("Use esta página apenas para a configuração inicial do sistema.")

with st.form("create_admin_form"):
    email = st.text_input("E-mail do Admin")
    password = st.text_input("Senha", type="password")
    submit = st.form_submit_button("Criar Admin")

if submit:
    if not email or not password:
        st.error("Preencha todos os campos.")
    else:
        # A função create_new_user já lida com Auth e Firestore
        create_new_user(email, password, "Admin")
