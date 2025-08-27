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
    Inicializa a conexão com o Firebase usando as credenciais de st.secrets.
    """
    if "firebase_config" not in st.secrets or "firebase_credentials" not in st.secrets:
        st.error("Configuração do Firebase não encontrada nos segredos. Adicione-a em .streamlit/secrets.toml.")
        return None, None

    firebase_config = dict(st.secrets.firebase_config)
    firebase_credentials = dict(st.secrets.firebase_credentials)

    if 'private_key' in firebase_credentials:
        firebase_credentials['private_key'] = firebase_credentials['private_key'].replace('\\n', '\n')

    if not firebase_admin._apps:
        try:
            cred = credentials.Certificate(firebase_credentials)
            firebase_admin.initialize_app(cred, {
                'databaseURL': firebase_config['databaseURL']
            })
        except Exception as e:
            st.error(f"Erro CRÍTICO ao inicializar o SDK Admin: {e}")
            return None, None

    try:
        firebase_client = pyrebase.initialize_app(firebase_config)
        auth_client = firebase_client.auth()
        db_admin_ref = admin_db.reference()
        return auth_client, db_admin_ref
    except Exception as e:
        st.error(f"Erro CRÍTICO ao inicializar o Pyrebase: {e}")
        return None, None

# --- FUNÇÕES DE AUTENTICAÇÃO E PERFIL ---

def login_user(auth, db, email, password):
    """
    Autentica o usuário e busca seu perfil. Agora com tratamento de erro detalhado.
    """
    try:
        user = auth.sign_in_with_email_and_password(email, password)
        uid = user['localId']
        user_profile = db.child("users").child(uid).get()

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
        # Este é o bloco mais importante. Erros de autenticação vêm como HTTPError.
        try:
            # Tenta extrair a mensagem de erro específica do Firebase
            error_data = e.response.json()
            error_message = error_data.get("error", {}).get("message", "ERRO_DESCONHECIDO")

            if "INVALID_LOGIN_CREDENTIALS" in error_message:
                st.error("Credenciais inválidas. Verifique seu email e senha.")
            # Este erro indica um problema com a chave de API (restrições, etc.)
            elif "API_KEY_NOT_VALID" in error_message or "IP_ADDRESS_NOT_ALLOWED" in error_message:
                st.error("Erro de configuração do Firebase: A chave de API não é válida ou está restrita. Verifique o Passo 2.")
                st.code(f"Detalhe do erro: {error_message}")
            else:
                st.error(f"Ocorreu um erro de autenticação: {error_message}")
        except json.JSONDecodeError:
            st.error(f"Ocorreu um erro de conexão com o Firebase. Verifique sua conexão e as configurações da chave de API.")
        return None
    except Exception as e:
        # Captura qualquer outro erro inesperado
        st.error(f"Ocorreu um erro inesperado: {e}")
        return None


# --- As outras funções (create_user, get_all_users, update_user_profile) permanecem as mesmas ---

def create_user(auth, db, email, password, role):
    try:
        new_user = auth.create_user_with_email_and_password(email, password)
        uid = new_user['localId']
        user_data = {"role": role, "status": "active", "email": email}
        db.child("users").child(uid).set(user_data)
        st.success(f"Usuário {email} criado com sucesso como {role}!")
        return True
    except Exception as e:
        try:
            error_message = json.loads(e.args[1])['error']['message']
            if error_message == "EMAIL_EXISTS":
                st.error("Este email já está cadastrado.")
            elif "WEAK_PASSWORD" in error_message:
                st.error("A senha é muito fraca. Use pelo menos 6 caracteres.")
            else:
                st.error(f"Erro ao criar conta: {error_message}")
        except:
            st.error(f"Ocorreu um erro inesperado durante a criação do usuário.")
        return False

def get_all_users(db):
    try:
        users = db.child("users").get()
        return users if users else {}
    except Exception as e:
        st.error(f"Erro ao buscar usuários: {e}")
        return {}

def update_user_profile(db, uid, new_role, new_status):
    try:
        db.child("users").child(uid).update({"role": new_role, "status": new_status})
        st.success("Perfil do usuário atualizado com sucesso!")
        return True
    except Exception as e:
        st.error(f"Erro ao atualizar o perfil: {e}")
        return False
