from __future__ import annotations

import logging
from typing import Any

import firebase_admin
import pyrebase
import streamlit as st
from firebase_admin import auth, credentials, firestore

log = logging.getLogger("financeiro_verdio.firebase")


def _secret_section(name: str) -> dict[str, Any]:
    try:
        return dict(st.secrets[name])
    except Exception as exc:
        raise RuntimeError(f"Secret obrigatório ausente: {name}") from exc


@st.cache_resource(show_spinner="Conectando aos serviços financeiros...")
def initialize_firebase():
    """Inicializa Firebase Admin, Firestore e autenticação Web uma única vez por processo."""
    try:
        if not firebase_admin._apps:
            service_account = _secret_section("service_account")
            firebase_admin.initialize_app(credentials.Certificate(service_account))

        firebase_web_config = _secret_section("firebase")
        firebase_app = pyrebase.initialize_app(firebase_web_config)
        auth_client = firebase_app.auth()
        db_client = firestore.client()

        # Validação pequena e sem leitura de documentos: confirma acesso ao cliente.
        if db_client is None or auth_client is None:
            raise RuntimeError("Clientes Firebase não foram inicializados.")

        return db_client, auth_client
    except Exception as exc:
        log.exception("Falha crítica ao inicializar Firebase.")
        st.error("Não foi possível conectar aos serviços de autenticação e banco de dados.")
        st.caption("Revise os Secrets 'service_account' e 'firebase' no ambiente do Streamlit Cloud.")
        st.stop()
        raise RuntimeError("Firebase indisponível") from exc


db, auth_client = initialize_firebase()


def get_auth_admin_client():
    """Retorna o módulo de autenticação do Firebase Admin SDK."""
    return auth
