# auth_functions.py
import streamlit as st
import pyrebase
import json

# --- CONFIGURAÇÃO E INICIALIZAÇÃO DO FIREBASE ---
# Colocamos a inicialização em uma função para garantir que seja executada apenas uma vez.
@st.cache_resource
def initialize_firebase():
    """
    Inicializa a conexão com o Firebase e retorna os objetos de autenticação e banco de dados.
    Usa @st.cache_resource para evitar reinicializações a cada interação na página.
    """
    firebase_config = {
        "apiKey": "AIzaSyDmdjlRRFkxnVUjQxZ-vrvYdIRA834GLhw",
        "authDomain": "financeiro-verdio.firebaseapp.com",
        "projectId": "financeiro-verdio",
        "storageBucket": "financeiro-verdio.appspot.com",
        "messagingSenderId": "1025401913741",
        "appId": "1:1025401913741:web:1f0ddc584a51b3b1acfdc4",
        "measurementId": "G-4DM3428F0E",
        "databaseURL": "https://financeiro-verdio-default-rtdb.firebaseio.com/"
    }
    try:
        firebase = pyrebase.initialize_app(firebase_config)
        auth = firebase.auth()
        db = firebase.database()
        return auth, db
    except Exception as e:
        st.error(f"Erro ao inicializar o Firebase: {e}")
        return None, None

# --- FUNÇÕES DE AUTENTICAÇÃO E PERFIL ---

def login_user(auth, db, email, password):
    """
    Autentica o usuário e busca seu perfil (role, status) no Realtime Database.
    """
    try:
        user = auth.sign_in_with_email_and_password(email, password)
        uid = user['localId']
        user_profile = db.child("users").child(uid).get().val()

        if user_profile:
            if user_profile.get('status') == 'disabled':
                st.error("Sua conta está desabilitada. Contate o administrador.")
                return None
            user.update(user_profile)
            return user
        else:
            st.error("Perfil de usuário não encontrado. Contate o administrador.")
            return None
    except Exception as e:
        try:
            error_json = e.args[1]
            error_message = json.loads(error_json)['error']['message']
            if error_message == "EMAIL_NOT_FOUND":
                st.error("Email não encontrado.")
            elif error_message == "INVALID_PASSWORD":
                st.error("Senha incorreta.")
            else:
                st.error(f"Erro ao fazer login: {error_message}")
        except (json.JSONDecodeError, KeyError, IndexError):
            st.error(f"Ocorreu um erro inesperado durante o login.")
        return None

# --- FUNÇÕES DO PAINEL DE ADMIN ---

def create_user(auth, db, email, password, role):
    """
    Cria um novo usuário na Authentication e define seu perfil no Realtime Database.
    """
    try:
        new_user = auth.create_user_with_email_and_password(email, password)
        uid = new_user['localId']
        user_data = {"role": role, "status": "active", "email": email}
        db.child("users").child(uid).set(user_data)
        st.success(f"Usuário {email} criado com sucesso como {role}!")
        return True
    except Exception as e:
        try:
            error_json = e.args[1]
            error_message = json.loads(error_json)['error']['message']
            if error_message == "EMAIL_EXISTS":
                st.error("Este email já está cadastrado.")
            elif "WEAK_PASSWORD" in error_message:
                st.error("A senha é muito fraca. Use pelo menos 6 caracteres.")
            else:
                st.error(f"Erro ao criar conta: {error_message}")
        except (json.JSONDecodeError, KeyError, IndexError):
            st.error(f"Ocorreu um erro inesperado durante a criação do usuário.")
        return False

def get_all_users(db):
    """
    Retorna todos os perfis de usuário do Realtime Database.
    """
    try:
        users = db.child("users").get().val()
        return users if users else {}
    except Exception as e:
        st.error(f"Erro ao buscar usuários: {e}")
        return {}

def update_user_profile(db, uid, new_role, new_status):
    """
    Atualiza o perfil (role, status) de um usuário.
    """
    try:
        db.child("users").child(uid).update({"role": new_role, "status": new_status})
        st.success("Perfil do usuário atualizado com sucesso!")
        return True
    except Exception as e:
        st.error(f"Erro ao atualizar o perfil: {e}")
        return False
