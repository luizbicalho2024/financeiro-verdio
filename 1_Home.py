# app.py
import streamlit as st
import pyrebase
import json
import os

# --- CONFIGURAÇÃO DO FIREBASE ---
# As credenciais foram extraídas do seu texto e convertidas para um dicionário Python.

firebase_config = {
    "apiKey": "AIzaSyDmdjlRRFkxnVUjQxZ-vrvYdIRA834GLhw",
    "authDomain": "financeiro-verdio.firebaseapp.com",
    "projectId": "financeiro-verdio",
    "storageBucket": "financeiro-verdio.appspot.com", # Corrigido: removido 'firebasestorage'
    "messagingSenderId": "1025401913741",
    "appId": "1:1025401913741:web:1f0ddc584a51b3b1acfdc4",
    "measurementId": "G-4DM3428F0E",
    "databaseURL": "https://financeiro-verdio-default-rtdb.firebaseio.com/"
}

# --- INICIALIZAÇÃO DO FIREBASE ---
# Inicializa a conexão com o Firebase para autenticação e outros serviços.
try:
    firebase = pyrebase.initialize_app(firebase_config)
    auth = firebase.auth()
    st.session_state.firebase_initialized = True
except Exception as e:
    st.error(f"Erro ao inicializar o Firebase: {e}")
    st.session_state.firebase_initialized = False

# --- FUNÇÕES DE AUTENTICAÇÃO ---

def login_user(email, password):
    """
    Função para autenticar um usuário com email e senha.
    Retorna o objeto do usuário em caso de sucesso ou None em caso de falha.
    """
    try:
        user = auth.sign_in_with_email_and_password(email, password)
        return user
    except Exception as e:
        # Tenta extrair a mensagem de erro específica do Firebase
        try:
            error_json = e.args[1]
            error_message = json.loads(error_json)['error']['message']
            if error_message == "EMAIL_NOT_FOUND":
                st.error("Email não encontrado. Por favor, cadastre-se.")
            elif error_message == "INVALID_PASSWORD":
                st.error("Senha incorreta. Tente novamente.")
            else:
                st.error(f"Erro ao fazer login: {error_message}")
        except (json.JSONDecodeError, KeyError, IndexError):
            st.error(f"Ocorreu um erro inesperado durante o login.")
        return None

def signup_user(email, password):
    """
    Função para registrar um novo usuário com email e senha.
    Retorna o objeto do usuário em caso de sucesso ou None em caso de falha.
    """
    try:
        user = auth.create_user_with_email_and_password(email, password)
        st.success("Conta criada com sucesso! Por favor, faça o login.")
        return user
    except Exception as e:
        # Tenta extrair a mensagem de erro específica do Firebase
        try:
            error_json = e.args[1]
            error_message = json.loads(error_json)['error']['message']
            if error_message == "EMAIL_EXISTS":
                st.error("Este email já está cadastrado. Tente fazer login.")
            elif "WEAK_PASSWORD" in error_message:
                st.error("A senha é muito fraca. Use pelo menos 6 caracteres.")
            else:
                st.error(f"Erro ao criar conta: {error_message}")
        except (json.JSONDecodeError, KeyError, IndexError):
            st.error(f"Ocorreu um erro inesperado durante o cadastro.")
        return None

# --- INTERFACE DA APLICAÇÃO ---

# Título da aplicação
st.set_page_config(page_title="Sistema de Login", layout="centered")
st.title("Sistema com Autenticação Firebase")

# Verifica se o Firebase foi inicializado corretamente
if not st.session_state.get('firebase_initialized', False):
    st.stop()

# --- LÓGICA DE EXIBIÇÃO ---

# Se o usuário não estiver logado, mostra as opções de Login/Cadastro
if 'user' not in st.session_state:
    choice = st.sidebar.selectbox("Login/Cadastro", ["Login", "Cadastre-se"])

    if choice == "Login":
        st.header("Faça seu Login")
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Senha", type="password")
            login_button = st.form_submit_button("Login")

            if login_button:
                if email and password:
                    user = login_user(email, password)
                    if user:
                        st.session_state.user = user  # Armazena o objeto do usuário na sessão
                        st.rerun() # Recarrega a página para mostrar o conteúdo logado
                else:
                    st.warning("Por favor, preencha todos os campos.")

    elif choice == "Cadastre-se":
        st.header("Crie sua Conta")
        with st.form("signup_form"):
            new_email = st.text_input("Email")
            new_password = st.text_input("Senha", type="password")
            signup_button = st.form_submit_button("Cadastrar")

            if signup_button:
                if new_email and new_password:
                    signup_user(new_email, new_password)
                else:
                    st.warning("Por favor, preencha todos os campos.")

# Se o usuário estiver logado, mostra a página principal
else:
    user_info = st.session_state.user
    # O email do usuário pode estar em diferentes locais dependendo da resposta do Firebase
    user_email = user_info.get('email', 'Email não disponível')

    st.sidebar.header(f"Bem-vindo(a)!")
    st.sidebar.write(f"{user_email}")

    st.header("Página Principal")
    st.write("Você está logado no sistema!")
    st.write("Aqui você pode adicionar o conteúdo principal da sua aplicação.")

    # Botão de Logout
    if st.sidebar.button("Logout"):
        del st.session_state.user # Remove as informações do usuário da sessão
        st.rerun() # Recarrega a página para voltar à tela de login
