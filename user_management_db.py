# user_management_db.py

import streamlit as st
from config_firebase import get_db
from datetime import datetime
import pytz
import streamlit_authenticator as stauth

# Obtém a instância do banco de dados Firestore
db = get_db()

# Define o fuso horário
BR_TIMEZONE = pytz.timezone('America/Sao_Paulo')

def get_current_time():
    """Retorna a data e hora atual no fuso horário de São Paulo."""
    return datetime.now(BR_TIMEZONE)

# --- FUNÇÕES DE LOG ---
def log_action(level, message, details=None):
    """
    Registra uma ação no log do sistema no Firestore.
    """
    try:
        user_email = st.session_state.get("email", "Sistema")
        log_entry = {
            "timestamp": get_current_time(),
            "level": level,
            "user": user_email,
            "message": message,
            "details": details or {}
        }
        db.collection('logs').add(log_entry)
    except Exception as e:
        st.error(f"Erro ao registrar log: {e}")
        print(f"Erro ao registrar log: {e}")

# --- FUNÇÕES DE AUTENTICAÇÃO E USUÁRIO (PARA streamlit-authenticator) ---

def fetch_all_users_for_auth():
    """
    Busca todos os usuários do Firestore e formata para o streamlit-authenticator.
    """
    users_ref = db.collection('users').stream()
    credentials = {'usernames': {}}
    for user in users_ref:
        user_data = user.to_dict()
        username = user_data.get('username')
        if username:
            credentials['usernames'][username] = {
                'name': user_data.get('name'),
                'email': user_data.get('email'),
                'password': user_data.get('hashed_password'),
                'role': user_data.get('role', 'user') # Adiciona o role
            }
    return credentials

def add_user(username, name, email, password, role):
    """
    Adiciona um novo usuário ao Firestore com senha hasheada.
    """
    try:
        hashed_password = stauth.Hasher([password]).generate()[0]
        user_data = {
            "username": username,
            "name": name,
            "email": email,
            "hashed_password": hashed_password,
            "role": role,
            "is_active": True,
            "created_at": get_current_time()
        }
        # Usa o username como ID do documento para fácil acesso
        db.collection('users').document(username).set(user_data)
        log_action("INFO", "Usuário criado com sucesso", {"username": username, "role": role})
        return True
    except Exception as e:
        log_action("ERROR", "Falha ao criar usuário", {"username": username, "error": str(e)})
        return False

def update_user(username, name, role, is_active):
    """
    Atualiza os dados de um usuário no Firestore.
    """
    try:
        user_ref = db.collection('users').document(username)
        user_ref.update({
            "name": name,
            "role": role,
            "is_active": is_active
        })
        log_action("INFO", "Usuário atualizado", {"username_atualizado": username, "novos_dados": {"name": name, "role": role, "is_active": is_active}})
        return True
    except Exception as e:
        log_action("ERROR", "Falha ao atualizar usuário", {"username": username, "error": str(e)})
        return False
        
def get_all_users():
    """
    Busca todos os usuários do Firestore para exibição no painel de admin.
    """
    users_ref = db.collection('users').stream()
    users_list = []
    for user in users_ref:
        user_data = user.to_dict()
        # Não inclui o hash da senha na exibição
        user_display = {
            "username": user_data.get("username"),
            "name": user_data.get("name"),
            "email": user_data.get("email"),
            "role": user_data.get("role"),
            "is_active": user_data.get("is_active"),
            "created_at": user_data.get("created_at")
        }
        users_list.append(user_display)
    return users_list

# --- FUNÇÕES DE FATURAMENTO (sem alterações) ---
def get_pricing_config():
    try:
        config_ref = db.collection('config').document('pricing').get()
        if config_ref.exists:
            return config_ref.to_dict()
    except: pass
    return {"PRECOS_PF": {"GPRS / Gsm": 60.0}, "PLANOS_PJ": {"36 Meses": {"Satélite": 120.0}}}

def log_faturamento(faturamento_data):
    try:
        log_entry = {"gerado_por": st.session_state.get("email", "N/A"), "data_geracao": get_current_time(), **faturamento_data}
        db.collection('billing_history').add(log_entry)
        log_action("INFO", "Faturamento gerado e salvo no histórico", faturamento_data)
        st.toast("Histórico de faturamento salvo com sucesso!")
    except Exception as e:
        log_action("ERROR", "Falha ao salvar histórico de faturamento", {"error": str(e)})
        st.error("Erro ao salvar o histórico no banco de dados.")

def get_billing_history():
    history_ref = db.collection('billing_history').order_by('data_geracao', direction='DESCENDING').stream()
    history_list = []
    for item in history_ref:
        data = item.to_dict()
        data['_id'] = item.id
        history_list.append(data)
    return history_list

def delete_billing_history(history_id):
    try:
        db.collection('billing_history').document(history_id).delete()
        log_action("WARNING", "Registro de histórico de faturamento excluído", {"history_id": history_id})
        st.success(f"Registro {history_id} excluído com sucesso!")
        return True
    except Exception as e:
        log_action("ERROR", "Falha ao excluir histórico de faturamento", {"history_id": history_id, "error": str(e)})
        return False
        
def get_system_logs():
    logs_ref = db.collection('logs').order_by('timestamp', direction='DESCENDING').stream()
    return [log.to_dict() for log in logs_ref]
