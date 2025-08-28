# firebase_config.py
import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore, auth
import pyrebase
import json

def initialize_firebase():
    """
    Inicializa o Firebase Admin SDK e o Pyrebase de forma segura,
    utilizando as credenciais armazenadas nos secrets do Streamlit.
    Retorna os clientes do Firestore e do Pyrebase Auth.
    """
    if not firebase_admin._apps:
        try:
            # Carrega as credenciais do service account a partir dos secrets
            service_account_creds = dict(st.secrets["service_account"])
            cred = credentials.Certificate(service_account_creds)
            firebase_admin.initialize_app(cred)
            st.session_state['firebase_admin_initialized'] = True
        except Exception as e:
            st.error(f"Erro ao inicializar o Firebase Admin SDK: {e}")
            st.stop()

    try:
        # Carrega a configuração do Firebase para o cliente web (Pyrebase)
        firebase_web_config = dict(st.secrets["firebase"])
        firebase = pyrebase.initialize_app(firebase_web_config)
        auth_client = firebase.auth()
    except Exception as e:
        st.error(f"Erro ao inicializar o Pyrebase: {e}")
        st.stop()
        
    db_client = firestore.client()
    
    return db_client, auth_client

# Inicializa e obtém os clientes
db, auth_client = initialize_firebase()

def get_auth_admin_client():
    """Retorna o cliente de autenticação do Admin SDK."""
    return auth
