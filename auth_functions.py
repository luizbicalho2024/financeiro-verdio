from __future__ import annotations

import logging
from typing import Any

import streamlit as st

from firebase_config import db, get_auth_admin_client

log = logging.getLogger("financeiro_verdio.auth")
auth_admin = get_auth_admin_client()
VALID_ROLES = {"Usuário", "Admin"}


def normalize_role(role: Any) -> str:
    return "Admin" if str(role or "").strip().lower() == "admin" else "Usuário"


def get_user_role(uid: str) -> str:
    try:
        user_doc = db.collection("users").document(str(uid)).get()
        if user_doc.exists:
            return normalize_role(user_doc.to_dict().get("role"))
    except Exception:
        log.exception("Erro ao buscar role do usuário %s", uid)
    return "Usuário"


def get_all_users() -> list[dict[str, Any]]:
    try:
        all_users: list[dict[str, Any]] = []
        for user in auth_admin.list_users().iterate_all():
            metadata = getattr(user, "user_metadata", None)
            all_users.append(
                {
                    "uid": user.uid,
                    "email": user.email or "",
                    "disabled": bool(user.disabled),
                    "role": get_user_role(user.uid),
                    "created_at": getattr(metadata, "creation_timestamp", None),
                    "last_sign_in_at": getattr(metadata, "last_sign_in_timestamp", None),
                }
            )
        return sorted(all_users, key=lambda item: str(item.get("email") or "").lower())
    except Exception:
        log.exception("Erro ao carregar usuários do Firebase Authentication.")
        st.error("Não foi possível carregar os usuários. Consulte os logs do aplicativo.")
        return []


def create_new_user(email: str, password: str, role: str) -> bool:
    normalized_email = str(email or "").strip().lower()
    normalized_role = normalize_role(role)

    if not normalized_email or "@" not in normalized_email:
        st.error("Informe um e-mail válido.")
        return False
    if len(password or "") < 8:
        st.error("A senha inicial deve possuir pelo menos 8 caracteres.")
        return False

    try:
        new_user = auth_admin.create_user(
            email=normalized_email,
            password=password,
            disabled=False,
        )
        db.collection("users").document(new_user.uid).set(
            {
                "email": normalized_email,
                "role": normalized_role,
            },
            merge=True,
        )
        return True
    except Exception as exc:
        log.exception("Erro ao criar usuário %s", normalized_email)
        message = str(exc).lower()
        if "email_already_exists" in message or "email already exists" in message:
            st.error("Já existe um usuário com este e-mail.")
        elif "invalid_grant" in message or "jwt" in message:
            st.error("As credenciais administrativas do Firebase precisam ser renovadas.")
        else:
            st.error("Não foi possível criar o usuário. Consulte os logs do aplicativo.")
        return False


def update_user_status(uid: str, is_disabled: bool) -> bool:
    try:
        auth_admin.update_user(str(uid), disabled=bool(is_disabled))
        return True
    except Exception:
        log.exception("Erro ao atualizar status do usuário %s", uid)
        st.error("Não foi possível atualizar o status do usuário.")
        return False


def update_user_role(uid: str, new_role: str) -> bool:
    normalized_role = normalize_role(new_role)
    try:
        db.collection("users").document(str(uid)).set({"role": normalized_role}, merge=True)
        return True
    except Exception:
        log.exception("Erro ao atualizar role do usuário %s", uid)
        st.error("Não foi possível atualizar o nível de acesso.")
        return False
