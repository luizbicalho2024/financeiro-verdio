# auth_functions.py
import streamlit as st
import pyrebase
import json
import firebase_admin
from firebase_admin import credentials, db as admin_db
from requests.exceptions import HTTPError

# --- CONFIGURAÇÃO E INICIALIZAÇÃO DO FIREBASE ---
@st.cache_resource
def initialize_firebase():
    """
    Inicializa a conexão com o Firebase usando as credenciais de st.secrets,
    corrigindo a formatação da chave privada.
    """
    if "firebase_config" not in st.secrets or "firebase_credentials" not in st.secrets:
        st.error("Configuração do Firebase não encontrada nos segredos. Adicione-a em .streamlit/secrets.toml.")
        return None, None

    firebase_config = dict(st.secrets.firebase_config)
    firebase_credentials = dict(st.secrets.firebase_credentials)

    # --- CORREÇÃO DEFINITIVA PARA O ERRO 'Invalid JWT Signature' ---
    # Garante que os caracteres de nova linha na chave privada sejam interpretados corretamente.
    if 'private_key' in firebase_credentials:
        firebase_credentials['private_key'] = firebase_credentials['private_key'].replace('\\n', '\n')

    # Inicialização do SDK Admin
    if not firebase_admin._apps:
        try:
            cred = credentials.Certificate(firebase_credentials)
            firebase_admin.initialize_app(cred, {
                'databaseURL': firebase_config['databaseURL']
            })
        except Exception as e:
            st.error(f"Erro CRÍTICO ao inicializar o SDK Admin: {e}")
            st.info("Verifique se a formatação do seu 'private_key' em secrets.toml está correta e se o arquivo de credenciais é válido.")
            return None, None

    # Inicialização do Pyrebase
    try:
        firebase_client = pyrebase.initialize_app(firebase_config)
        auth_client = firebase_client.auth()
        # A referência do banco de dados agora virá do SDK Admin
        db_admin_ref = admin_db.reference()
        return auth_client, db_admin_ref
    except Exception as e:
        st.error(f"Erro CRÍTICO ao inicializar o Pyrebase: {e}")
        return None, None

# --- FUNÇÕES DE AUTENTICAÇÃO E PERFIL ---

def login_user(auth, db, email, password):
    """
    Autentica o usuário e busca seu perfil na coleção 'profiles'.
    """
    try:
        user = auth.sign_in_with_email_and_password(email, password)
        uid = user['localId']
        # ATUALIZADO: Busca na coleção 'profiles'
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
            st.error("Ocorreu um erro de conexão com o Firebase. Verifique sua conexão e as configurações da chave de API.")
        return None
    except Exception as e:
        st.error(f"Ocorreu um erro inesperado durante o login: {e}")
        return None

# --- FUNÇÕES DO PAINEL DE ADMIN ---

def create_user(auth, db, email, password, role):
    """
    Cria um novo usuário na Authentication e define seu perfil na coleção 'profiles'.
    """
    try:
        new_user = auth.create_user_with_email_and_password(email, password)
        uid = new_user['localId']
        user_data = {"role": role, "status": "active", "email": email}
        # ATUALIZADO: Salva na coleção 'profiles'
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
    """
    Retorna todos os perfis da coleção 'profiles'.
    """
    try:
        # ATUALIZADO: Busca na coleção 'profiles'
        users = db.child("profiles").get()
        return users if users else {}
    except Exception as e:
        st.error(f"Erro ao buscar usuários: {e}")
        return {}

def update_user_profile(db, uid, new_role, new_status):
    """
    Atualiza o perfil de um usuário na coleção 'profiles'.
    """
    try:
        # ATUALIZADO: Atualiza na coleção 'profiles'
        db.child("profiles").child(uid).update({"role": new_role, "status": new_status})
        st.success("Perfil do usuário atualizado com sucesso!")
        return True
    except Exception as e:
        st.error(f"Erro ao atualizar o perfil: {e}")
        return False
