# user_management_db.py
import streamlit as st
from firebase_config import db
from datetime import datetime
import pandas as pd

def log_action(level, user, message, details=None):
    """Registra uma ação no log do sistema no Firestore."""
    try:
        log_entry = {
            "timestamp": datetime.now(),
            "level": level,
            "user": user,
            "message": message,
            "details": details or {}
        }
        db.collection("system_logs").add(log_entry)
    except Exception as e:
        st.warning(f"Não foi possível registrar o log: {e}")

def get_system_logs():
    """Busca todos os logs do sistema, ordenados por data."""
    try:
        logs_ref = db.collection("system_logs").order_by("timestamp", direction="DESCENDING").stream()
        return [log.to_dict() for log in logs_ref]
    except Exception as e:
        st.error(f"Erro ao buscar logs do sistema: {e}")
        return []

def get_billing_history():
    """Busca todo o histórico de faturamento, ordenado por data."""
    try:
        history_ref = db.collection("billing_history").order_by("data_geracao", direction="DESCENDING").stream()
        history = []
        for doc in history_ref:
            doc_data = doc.to_dict()
            doc_data["_id"] = doc.id
            history.append(doc_data)
        return history
    except Exception as e:
        st.error(f"Erro ao buscar histórico de faturamento: {e}")
        return []

def get_last_billing_for_client(client_name):
    """Busca o último registro de faturamento para um cliente específico."""
    try:
        history_ref = db.collection("billing_history").where("cliente", "==", client_name).order_by("data_geracao", direction="DESCENDING").limit(1).stream()
        for doc in history_ref:
            return doc.to_dict()
        return None
    except Exception as e:
        st.error(f"Erro ao buscar o último faturamento do cliente: {e}")
        return None

def log_faturamento(faturamento_data):
    """Salva um registro de faturamento gerado no Firestore."""
    try:
        user_email = st.session_state.get("user_info", {}).get("email", "sistema")
        faturamento_data.update({
            "data_geracao": datetime.now(),
            "gerado_por": user_email
        })
        db.collection("billing_history").add(faturamento_data)
        log_action("INFO", user_email, "Relatório de faturamento gerado e salvo.", faturamento_data)
        st.toast("Histórico de faturamento salvo com sucesso!")
    except Exception as e:
        st.error(f"Erro ao salvar o histórico de faturamento: {e}")

def delete_billing_history(history_id):
    """Exclui um registro do histórico de faturamento pelo seu ID."""
    try:
        db.collection("billing_history").document(history_id).delete()
        user_email = st.session_state.get("user_info", {}).get("email", "sistema")
        log_action("WARNING", user_email, f"Registro de histórico de faturamento excluído.", {"history_id": history_id})
        st.success("Registro de histórico excluído com sucesso!")
        return True
    except Exception as e:
        st.error(f"Erro ao excluir o registro de histórico: {e}")
        return False

# --- NOVAS FUNÇÕES DE ESTOQUE E PREÇOS ---

@st.cache_data(ttl=600)
def get_tracker_inventory():
    """Busca todo o inventário de rastreadores do Firestore."""
    try:
        trackers_ref = db.collection("trackers").stream()
        return [doc.to_dict() for doc in trackers_ref]
    except Exception as e:
        st.error(f"Erro ao buscar inventário de rastreadores: {e}")
        return []

def update_tracker_inventory(df):
    """
    Atualiza/Cria registros de rastreadores no Firestore em lote.
    O ID do documento é o número de série do equipamento.
    """
    try:
        batch = db.batch()
        count = 0
        for index, row in df.iterrows():
            serial_number = str(row['Nº Equipamento']).strip()
            if not serial_number:
                continue
            
            tracker_ref = db.collection("trackers").document(serial_number)
            data = {
                'Nº Equipamento': serial_number,
                'Modelo': row['Modelo'],
                'Tipo': str(row['Tipo']).upper().strip() # Garante que o tipo seja maiúsculo
            }
            batch.set(tracker_ref, data, merge=True) # merge=True para não sobrescrever outros campos
            count += 1
        batch.commit()
        return count
    except Exception as e:
        st.error(f"Erro ao salvar o inventário no banco de dados: {e}")
        return None

@st.cache_data(ttl=3600)
def get_pricing_config():
    """Busca as configurações de preço do Firestore. Retorna valores padrão se não encontrar."""
    try:
        config_doc = db.collection("settings").document("pricing").get()
        if config_doc.exists:
            return config_doc.to_dict()
    except Exception as e:
        st.warning(f"Não foi possível buscar configurações de preço: {e}. Usando valores padrão.")
    
    # Estrutura padrão
    return {
        "TIPO_EQUIPAMENTO": {
            "GPRS": 59.90,
            "SATELITE": 159.90,
            "CAMERA": 0.0,
            "RADIO": 0.0,
        }
    }

def update_pricing_config(new_prices):
    """Atualiza as configurações de preço no Firestore."""
    try:
        db.collection("settings").document("pricing").set(new_prices, merge=True)
        # Limpa o cache para que a próxima leitura pegue os valores atualizados
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Erro ao atualizar os preços: {e}")
        return False
