import firebase_admin
from firebase_admin import credentials, firestore, auth
import pyrebase
import streamlit as st

# --- CONFIGURAÇÃO PYREBASE (PARA AUTENTICAÇÃO DO LADO DO CLIENTE) ---
# Substitua com as credenciais do seu aplicativo da Web do Firebase
FIREBASE_CONFIG = {
    "apiKey": "SUA_API_KEY",
    "authDomain": "SEU_AUTH_DOMAIN.firebaseapp.com",
    "projectId": "SEU_PROJECT_ID",
    "storageBucket": "SEU_STORAGE_BUCKET.appspot.com",
    "messagingSenderId": "SEU_MESSAGING_SENDER_ID",
    "appId": "SEU_APP_ID",
    "databaseURL": "https://SEU_DATABASE_URL.firebaseio.com/" # Opcional, mas recomendado
}

# --- INICIALIZAÇÃO FIREBASE ADMIN SDK (PARA OPERAÇÕES DE BACKEND) ---
try:
    # Tenta inicializar o app usando as credenciais do Streamlit secrets
    # Ideal para deploy no Streamlit Community Cloud
    firebase_creds_dict = st.secrets["firebase_credentials"]
    cred = credentials.Certificate(firebase_creds_dict)

except (KeyError, FileNotFoundError):
    # Fallback para o arquivo local, ideal para desenvolvimento
    try:
        cred = credentials.Certificate("firebase_credentials.json")
    except Exception as e:
        st.error("Arquivo de credenciais 'firebase_credentials.json' não encontrado.")
        st.stop()

# Inicializa o app principal apenas uma vez
if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)

# Inicializa Pyrebase para autenticação
try:
    firebase_auth_app = pyrebase.initialize_app(FIREBASE_CONFIG)
except Exception as e:
    st.error(f"Erro ao inicializar o Pyrebase. Verifique sua configuração FIREBASE_CONFIG: {e}")
    st.stop()


# Acessa os serviços do Firebase
db = firestore.client()
firebase_auth = firebase_auth_app.auth()

def get_db():
    """Retorna a instância do cliente Firestore."""
    return db

def get_auth():
    """Retorna a instância do serviço de autenticação do Pyrebase."""
    return firebase_auth

def get_admin_auth():
    """Retorna o módulo de autenticação do Firebase Admin SDK."""
    return auth
