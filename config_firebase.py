import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore, auth
import pyrebase
import json

# --- Tenta carregar as credenciais do Streamlit Secrets ---
try:
    # Para deploy no Streamlit Community Cloud
    firebase_creds_dict = st.secrets["firebase_credentials"]
    firebase_config_dict = st.secrets["firebase_config"]
    
    # Converte a chave privada que pode vir com escapes incorretos
    firebase_creds_dict['private_key'] = firebase_creds_dict['private_key'].replace('\\n', '\n')
    
    cred = credentials.Certificate(firebase_creds_dict)
    
# --- Se falhar, tenta carregar do arquivo local (para desenvolvimento) ---
except (KeyError, FileNotFoundError):
    try:
        cred = credentials.Certificate("firebase_credentials.json")
        # Para carregar a config localmente, podemos criar um segundo arquivo ou embutir,
        # mas para o Pyrebase, é mais fácil usar o que já temos.
        with open("firebase_credentials.json") as f:
            local_creds = json.load(f)
        
        # NOTE: Para a autenticação do Pyrebase, ainda precisamos da apiKey, etc.
        # A melhor prática local seria ter um arquivo de configuração separado e ignorado.
        # Por simplicidade aqui, vamos preencher com placeholders se não estiver no st.secrets.
        # Lembre-se de substituir com sua config real se precisar testar a autenticação localmente.
        firebase_config_dict = {
            "apiKey": "SUA_API_KEY_LOCAL", # Substitua se for testar localmente
            "authDomain": f"{local_creds['project_id']}.firebaseapp.com",
            "projectId": local_creds['project_id'],
            "storageBucket": f"{local_creds['project_id']}.appspot.com",
            "messagingSenderId": "SEU_MESSAGING_SENDER_ID_LOCAL",
            "appId": "SEU_APP_ID_LOCAL",
            "databaseURL": f"https://{local_creds['project_id']}.firebaseio.com/"
        }
    except Exception as e:
        st.error("Falha ao carregar as credenciais do Firebase.")
        st.info("Certifique-se de que o arquivo 'firebase_credentials.json' está na pasta raiz ou que os segredos estão configurados no Streamlit Cloud.")
        st.stop()


# --- INICIALIZAÇÃO DOS SERVIÇOS ---

# Inicializa o Firebase Admin SDK (para backend)
# A verificação `if not firebase_admin._apps:` previne a reinicialização se o script recarregar.
if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)

# Inicializa o Pyrebase (para autenticação do lado do cliente)
try:
    firebase_auth_app = pyrebase.initialize_app(firebase_config_dict)
except Exception as e:
    st.error(f"Erro ao inicializar o Pyrebase. Verifique sua configuração: {e}")
    st.stop()


# Acessa os serviços do Firebase
db = firestore.client()
firebase_auth = firebase_auth_app.auth()
admin_auth = auth

def get_db():
    """Retorna a instância do cliente Firestore."""
    return db

def get_auth():
    """Retorna a instância do serviço de autenticação do Pyrebase."""
    return firebase_auth

def get_admin_auth():
    """Retorna o módulo de autenticação do Firebase Admin SDK."""
    return admin_auth
