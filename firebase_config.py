# firebase_config.py
import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore, auth
import pyrebase
import sys

def initialize_firebase():
    """
    Inicializa o Firebase usando credenciais de st.secrets.
    Fornece mensagens de erro detalhadas se os secrets estiverem faltando.
    """
    # Verifica a existência do segredo 'service_account'
    if "service_account" not in st.secrets:
        st.error("🚨 Segredo 'service_account' não encontrado! Por favor, verifique suas configurações de segredo no Streamlit Cloud.")
        st.info("O segredo 'service_account' deve conter as credenciais JSON da sua conta de serviço do Firebase.")
        st.stop()

    # Verifica a existência do segredo 'firebase' (configuração web)
    if "firebase" not in st.secrets:
        st.error("🚨 Segredo 'firebase' não encontrado! Por favor, verifique suas configurações de segredo no Streamlit Cloud.")
        st.info("O segredo 'firebase' deve conter a configuração da web do seu projeto Firebase (apiKey, authDomain, etc.).")
        st.stop()

    # Inicializa o Firebase Admin SDK (se ainda não foi inicializado)
    if not firebase_admin._apps:
        try:
            service_account_creds = dict(st.secrets["service_account"])
            cred = credentials.Certificate(service_account_creds)
            firebase_admin.initialize_app(cred)
        except Exception as e:
            st.error("❌ Erro ao inicializar o Firebase Admin SDK. Verifique se o conteúdo do segredo 'service_account' é um JSON válido.")
            st.exception(e)
            st.stop()

    # Inicializa o Pyrebase para autenticação do cliente
    try:
        firebase_web_config = dict(st.secrets["firebase"])
        firebase = pyrebase.initialize_app(firebase_web_config)
        auth_client = firebase.auth()
    except Exception as e:
        st.error("❌ Erro ao inicializar o Pyrebase. Verifique se o conteúdo do segredo 'firebase' está correto.")
        st.exception(e)
        st.stop()
        
    db_client = firestore.client()
    return db_client, auth_client

# Tenta inicializar a conexão
try:
    db, auth_client = initialize_firebase()
except BaseException:
    # Impede que o app continue se st.stop() for chamado
    sys.exit()

def get_auth_admin_client():
    """Retorna o cliente de autenticação do Admin SDK."""
    return auth
