# auth_functions.py
import streamlit as st
from firebase_config import db, get_auth_admin_client

# Obtém o cliente de autenticação do Admin SDK
auth_admin = get_auth_admin_client()

def get_user_role(uid):
    """Busca o nível de acesso (role) de um usuário no Firestore pelo UID."""
    try:
        user_doc = db.collection('users').document(uid).get()
        if user_doc.exists:
            return user_doc.to_dict().get('role', 'Usuário')
    except Exception as e:
        st.error(f"Erro ao buscar o nível de acesso: {e}")
    return 'Usuário'

def get_all_users():
    """Busca todos os usuários do Firebase Authentication e combina com suas roles do Firestore."""
    try:
        all_users = []
        for user in auth_admin.list_users().iterate_all():
            user_data = {
                "uid": user.uid,
                "email": user.email,
                "disabled": user.disabled,
                "role": get_user_role(user.uid)
            }
            all_users.append(user_data)
        return all_users
    except Exception as e:
        st.error(f"Erro ao carregar a lista de usuários: {e}")
        return []

def create_new_user(email, password, role):
    """Cria um novo usuário no Firebase Auth e define sua role no Firestore."""
    try:
        new_user = auth_admin.create_user(email=email, password=password, disabled=False)
        db.collection('users').document(new_user.uid).set({
            'email': email,
            'role': role
        })
        st.success(f"Usuário '{email}' criado com sucesso!")
        return True
    except Exception as e:
        st.error(f"Erro ao criar usuário: {e}")
        return False

def update_user_status(uid, is_disabled):
    """Atualiza o status (habilitado/desabilitado) de um usuário no Firebase Authentication."""
    try:
        auth_admin.update_user(uid, disabled=is_disabled)
        status_text = "desabilitado" if is_disabled else "re-habilitado"
        st.success(f"Usuário {status_text} com sucesso!")
        return True
    except Exception as e:
        st.error(f"Erro ao atualizar o status do usuário: {e}")
        return False

def update_user_role(uid, new_role):
    """Atualiza a role de um usuário no documento correspondente no Firestore."""
    try:
        db.collection('users').document(uid).update({'role': new_role})
        st.success("Nível de acesso atualizado com sucesso!")
        return True
    except Exception as e:
        st.error(f"Erro ao atualizar o nível de acesso do usuário: {e}")
        return False
