# firebase_config.py
import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore, auth
import pyrebase
import json

def initialize_firebase():
    """
    Inicializa o Firebase de forma segura, garantindo que a inicialização 
    ocorra apenas uma vez e tratando erros de secrets.
    """
    try:
        # Tenta inicializar o Firebase Admin SDK
        if not firebase_admin._apps:
            # Carrega as credenciais da conta de serviço dos secrets
            service_account_creds = dict(st.secrets["service_account"])
            cred = credentials.Certificate(service_account_creds)
            firebase_admin.initialize_app(cred)
            
        # Carrega a configuração web do Firebase (para autenticação) dos secrets
        firebase_web_config = dict(st.secrets["firebase"])
        
        # Inicializa o Pyrebase para autenticação
        firebase_app = pyrebase.initialize_app(firebase_web_config)
        
        # Obtém os clientes de autenticação e banco de dados
        auth_client = firebase_app.auth()
        db_client = firestore.client()
        
        return db_client, auth_client

    except KeyError as e:
        st.error(f"🚨 Erro de Configuração: O segredo '{e.args[0]}' não foi encontrado no Streamlit Cloud.")
        st.info("Por favor, verifique se os secrets 'service_account' e 'firebase' estão configurados corretamente.")
        st.stop()
    except Exception as e:
        st.error("❌ Falha crítica ao inicializar o Firebase. Verifique a validade das suas credenciais.")
        st.exception(e)
        st.stop()

# Inicializa e exporta os clientes para serem usados em outros módulos
db, auth_client = initialize_firebase()

def get_auth_admin_client():
    """Retorna o cliente de autenticação do Admin SDK para tarefas administrativas."""
    return auth
