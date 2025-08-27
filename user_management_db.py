import streamlit as st
from config_firebase import get_db, get_auth, get_admin_auth
from datetime import datetime
import pytz
import bcrypt

# Obtém a instância do banco de dados e autenticação
db = get_db()
auth_client = get_auth()
admin_auth = get_admin_auth()

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
        print(f"Erro ao registrar log: {e}")

# --- FUNÇÕES DE AUTENTICAÇÃO E USUÁRIO ---
def sign_in(email, password):
    """
    Autentica um usuário usando o Pyrebase e busca seus dados no Firestore.
    """
    try:
        user = auth_client.sign_in_with_email_and_password(email, password)
        user_info = db.collection('users').document(user['localId']).get()
        if user_info.exists:
            user_data = user_info.to_dict()
            if not user_data.get('is_active', True):
                log_action("WARNING", "Tentativa de login de usuário desabilitado", {"email": email})
                return False, "Usuário desabilitado. Contate o administrador."
            
            st.session_state.authentication_status = True
            st.session_state.email = email
            st.session_state.name = user_data.get('name', 'N/A')
            st.session_state.role = user_data.get('role', 'user')
            st.session_state.uid = user['localId']
            
            log_action("INFO", "Login bem-sucedido", {"email": email})
            return True, "Login bem-sucedido!"
        else:
            log_action("ERROR", "Usuário autenticado mas não encontrado no Firestore", {"email": email, "uid": user['localId']})
            return False, "Erro: dados do usuário não encontrados."
    except Exception as e:
        log_action("ERROR", "Falha no login", {"email": email, "error": str(e)})
        return False, "E-mail ou senha inválidos."

def create_user(email, password, name, role):
    """
    Cria um novo usuário na autenticação do Firebase e no Firestore.
    Acessível apenas por Admins.
    """
    try:
        # Cria o usuário no Firebase Authentication
        new_user = admin_auth.create_user(email=email, password=password)
        uid = new_user.uid

        # Armazena informações adicionais no Firestore
        user_data = {
            "name": name,
            "email": email,
            "role": role,
            "is_active": True,
            "created_at": get_current_time()
        }
        db.collection('users').document(uid).set(user_data)
        
        log_action("INFO", "Usuário criado com sucesso", {"email_criado": email, "role": role})
        return True, "Usuário criado com sucesso!"
    except Exception as e:
        log_action("ERROR", "Falha ao criar usuário", {"email": email, "error": str(e)})
        return False, f"Erro ao criar usuário: {e}"

def get_all_users():
    """
    Busca todos os usuários do Firestore.
    """
    users_ref = db.collection('users').stream()
    users_list = []
    for user in users_ref:
        user_data = user.to_dict()
        user_data['uid'] = user.id
        users_list.append(user_data)
    return users_list

def update_user(uid, name, role, is_active):
    """
    Atualiza os dados de um usuário no Firestore.
    """
    try:
        user_ref = db.collection('users').document(uid)
        user_ref.update({
            "name": name,
            "role": role,
            "is_active": is_active
        })
        log_action("INFO", "Usuário atualizado", {"uid_atualizado": uid, "novos_dados": {"name": name, "role": role, "is_active": is_active}})
        return True, "Usuário atualizado com sucesso!"
    except Exception as e:
        log_action("ERROR", "Falha ao atualizar usuário", {"uid": uid, "error": str(e)})
        return False, f"Erro ao atualizar usuário: {e}"

# --- FUNÇÕES DE LOGS (LEITURA) ---
def get_system_logs():
    """
    Busca todos os logs do sistema, ordenados pelo mais recente.
    """
    logs_ref = db.collection('logs').order_by('timestamp', direction='DESCENDING').stream()
    return [log.to_dict() for log in logs_ref]

# --- FUNÇÕES DE FATURAMENTO (CONFORME SEU SCRIPT) ---
def get_pricing_config():
    """
    Busca configurações de preço do Firestore.
    Exemplo de estrutura no Firestore: coleção 'config', documento 'pricing'.
    """
    try:
        config_ref = db.collection('config').document('pricing').get()
        if config_ref.exists:
            return config_ref.to_dict()
    except Exception:
        pass # Retorna o fallback se não encontrar
    
    # Fallback caso não exista no DB
    return {
        "PRECOS_PF": {"GPRS / Gsm": 60.0},
        "PLANOS_PJ": {"36 Meses": {"Satélite": 120.0}}
    }

def log_faturamento(faturamento_data):
    """
    Salva os dados do faturamento gerado no histórico (billing_history).
    """
    try:
        log_entry = {
            "gerado_por": st.session_state.get("email", "N/A"),
            "data_geracao": get_current_time(),
            **faturamento_data # Adiciona todos os dados do dicionário
        }
        db.collection('billing_history').add(log_entry)
        log_action("INFO", "Faturamento gerado e salvo no histórico", faturamento_data)
        st.toast("Histórico de faturamento salvo com sucesso!")
    except Exception as e:
        log_action("ERROR", "Falha ao salvar histórico de faturamento", {"error": str(e)})
        st.error("Erro ao salvar o histórico no banco de dados.")

def get_billing_history():
    """
    Busca todo o histórico de faturamento do Firestore.
    """
    history_ref = db.collection('billing_history').order_by('data_geracao', direction='DESCENDING').stream()
    history_list = []
    for item in history_ref:
        data = item.to_dict()
        data['_id'] = item.id  # Adiciona o ID do documento
        history_list.append(data)
    return history_list

def delete_billing_history(history_id):
    """
    Exclui um registro de histórico de faturamento pelo seu ID.
    """
    try:
        db.collection('billing_history').document(history_id).delete()
        log_action("WARNING", "Registro de histórico de faturamento excluído", {"history_id": history_id})
        st.success(f"Registro {history_id} excluído com sucesso!")
        return True
    except Exception as e:
        log_action("ERROR", "Falha ao excluir histórico de faturamento", {"history_id": history_id, "error": str(e)})
        return False
