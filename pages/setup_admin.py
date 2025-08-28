# pages/setup_admin.py
import sys
import os

# Adiciona o diretório raiz do projeto ao sys.path para resolver o ImportError
# Esta linha é crucial para que o script encontre 'auth_functions.py'
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import streamlit as st
from auth_functions import create_new_user

st.set_page_config(page_title="Setup Admin", page_icon="🔑", layout="centered")

st.title("🔑 Criar Primeiro Usuário Admin")
st.warning("Use esta página apenas para a configuração inicial do sistema. Após o uso, você pode removê-la.")

# Formulário para criar o usuário admin
with st.form("create_admin_form", clear_on_submit=True):
    email = st.text_input("E-mail do Administrador")
    password = st.text_input("Senha", type="password")
    submit_button = st.form_submit_button("Criar Admin")

    if submit_button:
        if not email or not password:
            st.error("Por favor, preencha todos os campos.")
        elif "@" not in email or "." not in email:
            st.error("Formato de e-mail inválido.")
        else:
            # Chama a função centralizada para criar o usuário com a role "Admin"
            # Esta função já exibe as mensagens de sucesso ou erro
            if create_new_user(email, password, "Admin"):
                st.success(f"Administrador '{email}' criado com sucesso!")
                st.info("Você já pode fazer login na página inicial.")
            else:
                # A função create_new_user já mostra o erro detalhado
                st.error("Não foi possível criar o administrador. Verifique os logs do Firebase se o problema persistir.")
