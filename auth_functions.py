# auth_functions.py

import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore

def initialize_firebase():
    """Inicializa a conexão com o Firebase."""
    if not firebase_admin._apps:
        try
            # O Streamlit lê o secrets.toml formatado corretamente e já entrega um dicionário.
            creds_dict = st.secrets["firebase_credentials"]
            creds = credentials.Certificate(creds_dict)
            firebase_admin.initialize_app(creds)
        except Exception as e:
            st.error(f"Falha ao inicializar o Firebase: {e}")
            st.stop()
    
    return firestore.client()
