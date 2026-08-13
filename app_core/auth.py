from __future__ import annotations

from typing import Any

import streamlit as st

from app_core.shared_identity import get_finance_role


def is_authenticated() -> bool:
    user_info = st.session_state.get("user_info")
    return isinstance(user_info, dict) and bool(
        user_info.get("localId") or user_info.get("email")
    )


def current_role() -> str:
    return str(st.session_state.get("role") or "Usuário").strip()


def is_admin() -> bool:
    return current_role().lower() == "admin"


def role_label(role: str | None = None) -> str:
    normalized = str(role or current_role()).strip().lower()
    return "Administrador" if normalized == "admin" else "Usuário"


def _identity_identifier() -> str:
    info: Any = st.session_state.get("user_info") or {}
    return str(
        info.get("localId")
        or info.get("username")
        or info.get("email")
        or ""
    ).strip().lower()


def require_auth(*, admin: bool = False) -> None:
    if not is_authenticated():
        st.error("Acesso restrito. Faça login para continuar.")
        st.page_link("1_Home.py", label="Ir para o login", width="stretch")
        st.stop()

    identifier = _identity_identifier()
    finance_role = get_finance_role(identifier) if identifier else None

    if finance_role is None:
        for key in ("user_info", "role", "name"):
            st.session_state.pop(key, None)
        st.error(
            "Seu usuário está inativo ou não possui mais acesso ao Financeiro."
        )
        st.page_link("1_Home.py", label="Voltar para o login", width="stretch")
        st.stop()

    st.session_state["role"] = finance_role

    if admin and finance_role.lower() != "admin":
        st.error("Esta área é restrita a administradores do Financeiro.")
        st.page_link("1_Home.py", label="Voltar para a visão geral", width="stretch")
        st.stop()


def logout() -> None:
    for key in list(st.session_state.keys()):
        st.session_state.pop(key, None)
    try:
        st.switch_page("1_Home.py")
    except Exception:
        st.rerun()


def user_email() -> str:
    info: Any = st.session_state.get("user_info") or {}
    return str(info.get("email") or "").strip().lower()


def user_username() -> str:
    info: Any = st.session_state.get("user_info") or {}
    return str(
        info.get("localId") or info.get("username") or ""
    ).strip().lower()


def user_name() -> str:
    return str(
        st.session_state.get("name")
        or user_email().split("@")[0]
        or user_username()
        or "Usuário"
    ).strip()
