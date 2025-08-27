# auth_functions.py
import streamlit as st
import pyrebase
import json
import firebase_admin
from firebase_admin import credentials, db as admin_db
from requests.exceptions import HTTPError
import base64

# --- CONFIGURAÇÃO E INICIALIZAÇÃO DO FIREBASE ---
@st.cache_resource
def initialize_firebase():
    """
    Inicializa a conexão com o Firebase decodificando as credenciais Base64 de st.secrets.
    Esta é a abordagem mais robusta para evitar erros de formatação.
    """
    if "firebase_config" not in st.secrets or "firebase_credentials_b64" not in st.secrets:
        st.error("Configuração do Firebase (firebase_config ou firebase_credentials_b64) não encontrada nos segredos.")
        return None, None

    firebase_config = dict(st.secrets.firebase_config)
    
    # --- DECODIFICAÇÃO DAS CREDENCIAIS BASE64 ---
    try:
        # Pega a string Base64 dos segredos
        cred_b64 = st.secrets["firebase_credentials_b64"]
        # Decodifica de Base64 para bytes
        cred_bytes = base64.b64decode(cred_b64)
        # Converte os bytes para um dicionário Python
        firebase_credentials = json.loads(cred_bytes)
    except Exception as e:
        st.error(f"Erro ao decodificar as credenciais do Firebase a partir do Base64: {e}")
        st.info("Verifique se a variável 'firebase_credentials_b64' em seus segredos está correta.")
        return None, None

    # Inicialização do SDK Admin
    if not firebase_admin._apps:
        try:
            cred = credentials.Certificate(firebase_credentials)
            firebase_admin.initialize_app(cred, {
                'databaseURL': firebase_config['databaseURL']
            })
        except Exception as e:
            st.error(f"Erro CRÍTICO ao inicializar o SDK Admin: {e}")
            return None, None

    # Inicialização do Pyrebase
    try:
        firebase_client = pyrebase.initialize_app(firebase_config)
        auth_client = firebase_client.auth()
        db_admin_ref = admin_db.reference()
        return auth_client, db_admin_ref
    except Exception as e:
        st.error(f"Erro CRÍTICO ao inicializar o Pyrebase: {e}")
        return None, None

# --- FUNÇÕES DE AUTENTICAÇÃO E PERFIL ---
# Nenhuma alteração necessária nas funções abaixo, elas permanecem as mesmas.

def login_user(auth, db, email, password):
    try:
        user = auth.sign_in_with_email_and_password(email, password)
        uid = user['localId']
        user_profile = db.child("profiles").child(uid).get()
        if user_profile:
            if user_profile.get('status') == 'disabled':
                st.error("Sua conta está desabilitada. Contate o administrador.")
                return None
            user.update(user_profile)
            return user
        else:
            st.error("Perfil de usuário não encontrado. Contate o administrador.")
            return None
    except HTTPError as e:
        try:
            error_data = e.response.json()
            error_message = error_data.get("error", {}).get("message", "ERRO_DESCONHECIDO")
            if "INVALID_LOGIN_CREDENTIALS" in error_message:
                st.error("Credenciais inválidas. Verifique seu email e senha.")
            else:
                st.error(f"Ocorreu um erro de autenticação: {error_message}")
        except json.JSONDecodeError:
            st.error("Ocorreu um erro de conexão com o Firebase.")
        return None
    except Exception as e:
        st.error(f"Ocorreu um erro inesperado durante o login: {e}")
        return None

def create_user(auth, db, email, password, role):
    try:
        new_user = auth.create_user_with_email_and_password(email, password)
        uid = new_user['localId']
        user_data = {"role": role, "status": "active", "email": email}
        db.child("profiles").child(uid).set(user_data)
        st.success(f"Usuário {email} criado com sucesso como {role}!")
        return True
    except Exception as e:
        try:
            error_message = json.loads(e.args[1])['error']['message']
            if "EMAIL_EXISTS" in error_message:
                st.error("Este email já está cadastrado.")
            elif "WEAK_PASSWORD" in error_message:
                st.error("A senha é muito fraca. Use pelo menos 6 caracteres.")
            else:
                st.error(f"Erro ao criar conta: {error_message}")
        except:
            st.error("Ocorreu um erro inesperado durante a criação do usuário.")
        return False

def get_all_users(db):
    try:
        users = db.child("profiles").get()
        return users if users else {}
    except Exception as e:
        st.error(f"Erro ao buscar usuários: {e}")
        return {}

def update_user_profile(db, uid, new_role, new_status):
    try:
        db.child("profiles").child(uid).update({"role": new_role, "status": new_status})
        st.success("Perfil do usuário atualizado com sucesso!")
        return True
    except Exception as e:
        st.error(f"Erro ao atualizar o perfil: {e}")
        return False
