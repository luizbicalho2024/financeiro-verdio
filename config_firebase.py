import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore, auth
import pyrebase
import json

# --- Tenta carregar as credenciais do Streamlit Secrets ---
try:
    # Para deploy no Streamlit Community Cloud
    
    # 1. Copia os secrets para um dicionário normal (mutável)
    firebase_creds_dict = dict(st.secrets["firebase_credentials"])
    firebase_config_dict = dict(st.secrets["firebase_config"])
    
    # ==================================================================
    # LINHA DE DIAGNÓSTICO: Mostra a qual projeto estamos conectados.
    st.warning(f"CONECTADO AO PROJETO FIREBASE: {firebase_creds_dict.get('project_id')}")
    # ==================================================================
    
    # 2. Agora modifica a cópia, não o original
    if 'private_key' in firebase_creds_dict:
        firebase_creds_dict['private_key'] = firebase_creds_dict['private_key'].replace('\\n', '\n')
    
    cred = credentials.Certificate(firebase_creds_dict)
    
# --- Se falhar, tenta carregar do arquivo local (para desenvolvimento) ---
except (KeyError, FileNotFoundError):
    try:
        cred = credentials.Certificate("firebase_credentials.json")
        with open("firebase_credentials.json") as f:
            local_creds = json.load(f)
        
        # NOTE: Lembre-se de substituir com sua config real se precisar testar a autenticação localmente.
        firebase_config_dict = {
            "apiKey": "SUA_API_KEY_LOCAL", 
            "authDomain": f"{local_creds.get('project_id', '')}.firebaseapp.com",
            "projectId": local_creds.get('project_id', ''),
            "storageBucket": f"{local_creds.get('project_id', '')}.appspot.com",
            "messagingSenderId": "SEU_MESSAGING_SENDER_ID_LOCAL",
            "appId": "SEU_APP_ID_LOCAL",
            "databaseURL": f"https://{local_creds.get('project_id', '')}-default-rtdb.firebaseio.com/"
        }
    except Exception as e:
        st.error("Falha ao carregar as credenciais do Firebase.")
        st.info("Certifique-se de que o arquivo 'firebase_credentials.json' está na pasta raiz ou que os segredos estão configurados no Streamlit Cloud.")
        st.stop()


# --- INICIALIZAÇÃO DOS SERVIÇOS ---
if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)

try:
    firebase_auth_app = pyrebase.initialize_app(firebase_config_dict)
except Exception as e:
    st.error(f"Erro ao inicializar o Pyrebase. Verifique sua configuração: {e}")
    st.stop()

db = firestore.client()
firebase_auth = firebase_auth_app.auth()
admin_auth = auth

def get_db():
    return db

def get_auth():
    return firebase_auth

def get_admin_auth():
    return admin_auth
