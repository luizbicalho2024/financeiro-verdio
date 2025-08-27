# auth_functions.py

import streamlit as st
import firebase_admin
from firebase_admin import credentials, auth, firestore

# --- INICIALIZAÇÃO DO FIREBASE ---

def initialize_firebase():
    """
    Inicializa a conexão com o Firebase de forma segura.
    """
    if not firebase_admin._apps:
        try:  # <-- CORREÇÃO: Faltava um ':' nesta linha
            creds_dict = st.secrets["firebase_credentials"]
            creds = credentials.Certificate(creds_dict)
            firebase_admin.initialize_app(creds)
        except Exception as e:
            st.error(f"Falha ao inicializar o Firebase: {e}")
            st.stop()
    
    return firestore.client()


# --- FUNÇÕES DE BANCO DE DADOS E AUTENTICAÇÃO ---

def get_user_role(db, uid):
    """
    Busca o nível de acesso (role) de um usuário no Firestore.
    """
    try:
        user_doc = db.collection('users').document(uid).get()
        if user_doc.exists:
            return user_doc.to_dict().get('role', 'Usuário')
    except Exception as e:
        st.error(f"Erro ao buscar o nível de acesso: {e}")
    
    return 'Usuário'

def get_all_users(db):
    """
    Busca todos os usuários do Firebase Authentication e combina com suas roles do Firestore.
    """
    try:
        users_ref = auth.list_users()
        all_users = []
        for user in users_ref.iterate_all():
            user_data = {
                "uid": user.uid,
                "email": user.email,
                "disabled": user.disabled,
                "role": get_user_role(db, user.uid)
            }
            all_users.append(user_data)
        return all_users
    except Exception as e:
        st.error(f"Erro ao carregar a lista de usuários: {e}")
        return []

def create_new_user(db, email, password, role):
    """
    Cria um novo usuário no Firebase Auth e define sua role no Firestore.
    """
    try:
        new_user = auth.create_user(email=email, password=password)
        db.collection('users').document(new_user.uid).set({
            'role': role,
            'email': email
        })
        st.success(f"Usuário '{email}' criado com sucesso!")
        return True
    except Exception as e:
        st.error(f"Erro ao criar usuário: {e}")
        return False

def update_user_status(uid, disabled_status):
    """
    Atualiza o status (habilitado/desabilitado) de um usuário no Firebase Authentication.
    """
    try:
        auth.update_user(uid, disabled=disabled_status)
        return True
    except Exception as e:
        st.error(f"Erro ao atualizar o status do usuário {uid}: {e}")
        return False

def update_user_role(db, uid, new_role):
    """
    Atualiza a role de um usuário no documento correspondente no Firestore.
    """
    try:
        db.collection('users').document(uid).update({'role': new_role})
        return True
    except Exception as e:
        st.error(f"Erro ao atualizar o nível de acesso do usuário {uid}: {e}")
        return False
