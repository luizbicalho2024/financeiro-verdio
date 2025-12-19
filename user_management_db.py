# user_management_db.py
import streamlit as st
from firebase_config import db
from datetime import datetime
import pandas as pd

# --- FUNÇÕES DE LOG E SISTEMA ---

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
    try:
        logs_ref = db.collection("system_logs").order_by("timestamp", direction="DESCENDING").stream()
        return [log.to_dict() for log in logs_ref]
    except Exception as e:
        st.error(f"Erro ao buscar logs do sistema: {e}")
        return []

# --- FUNÇÕES DE FATURAMENTO E HISTÓRICO ---

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

def log_faturamento(faturamento_data, detalhes_itens=None):
    """
    Salva um registro de faturamento gerado no Firestore.
    Agora suporta salvar o 'detalhes_itens' (lista de dicionários) para cálculo de comissão item a item.
    """
    try:
        user_email = st.session_state.get("user_info", {}).get("email", "sistema")
        
        # Dados principais do cabeçalho
        faturamento_data.update({
            "data_geracao": datetime.now(),
            "gerado_por": user_email
        })
        
        # Se houver itens detalhados (terminais), adiciona ao payload
        if detalhes_itens is not None and isinstance(detalhes_itens, list):
            # Firestore tem limite de tamanho por documento (1MB). 
            # Se a lista for muito grande, ideal seria salvar em subcoleção, 
            # mas para uso moderado, salvar dentro do documento funciona.
            faturamento_data["itens_detalhados"] = detalhes_itens

        db.collection("billing_history").add(faturamento_data)
        
        # Log sem os detalhes pesados
        log_data_summary = {k: v for k, v in faturamento_data.items() if k != "itens_detalhados"}
        log_action("INFO", user_email, "Relatório de faturamento gerado e salvo.", log_data_summary)
        
        st.toast("Histórico de faturamento (com detalhes) salvo com sucesso!")
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

# --- FUNÇÕES DE ESTOQUE E PREÇOS ---

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
    """Atualiza/Cria registros de rastreadores no Firestore em lote."""
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
                'Tipo': str(row['Tipo']).upper().strip()
            }
            batch.set(tracker_ref, data, merge=True)
            count += 1
        batch.commit()
        return count
    except Exception as e:
        st.error(f"Erro ao salvar o inventário no banco de dados: {e}")
        return None

@st.cache_data(ttl=600)
def get_unique_models_and_types():
    try:
        trackers = get_tracker_inventory()
        if not trackers: return {}
        df = pd.DataFrame(trackers)
        model_types = df.groupby('Modelo')['Tipo'].first().to_dict()
        return model_types
    except Exception as e:
        st.error(f"Erro ao buscar modelos únicos: {e}")
        return {}

def update_type_for_models(updates):
    success_count = 0
    failed_models = []
    for model, new_type in updates.items():
        try:
            docs = db.collection('trackers').where('Modelo', '==', model).stream()
            batch = db.batch()
            doc_found = False
            for doc in docs:
                doc_found = True
                batch.update(doc.reference, {'Tipo': new_type})
            if doc_found:
                batch.commit()
                success_count += 1
            else:
                failed_models.append(model)
        except Exception as e:
            st.error(f"Erro ao atualizar o modelo '{model}': {e}")
            failed_models.append(model)
    return success_count, failed_models

@st.cache_data(ttl=3600)
def get_pricing_config():
    """
    Busca as configurações de preço do Firestore.
    Retorna estrutura normalizada com 3 preços por tipo.
    """
    defaults = {"GPRS": 59.90, "SATELITE": 159.90, "CAMERA": 0.0, "RADIO": 0.0}
    try:
        config_doc = db.collection("settings").document("pricing").get()
        data = config_doc.to_dict() if config_doc.exists else {}
    except Exception as e:
        st.warning(f"Erro ao buscar configurações de preço: {e}. Usando valores padrão.")
        data = {}

    tipo_equip = data.get("TIPO_EQUIPAMENTO", {})
    normalized_types = {}
    
    all_keys = set(tipo_equip.keys()) | set(defaults.keys())
    
    for key in all_keys:
        val = tipo_equip.get(key, defaults.get(key, 0.0))
        if isinstance(val, (int, float)):
            normalized_types[key] = {"price1": float(val), "price2": float(val), "price3": float(val)}
        elif isinstance(val, dict):
            normalized_types[key] = {
                "price1": float(val.get("price1", 0.0)),
                "price2": float(val.get("price2", 0.0)),
                "price3": float(val.get("price3", 0.0))
            }
        else:
            normalized_types[key] = {"price1": 0.0, "price2": 0.0, "price3": 0.0}
            
    return {"TIPO_EQUIPAMENTO": normalized_types}

def update_pricing_config(new_prices):
    try:
        db.collection("settings").document("pricing").set(new_prices, merge=True)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Erro ao atualizar os preços: {e}")
        return False
