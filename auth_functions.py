from __future__ import annotations

import logging
from typing import Any

import streamlit as st

from app_core.shared_identity import (
    finance_role_label,
    get_all_shared_users,
    get_finance_role,
    get_shared_user,
    update_finance_access as _update_finance_access,
)

log = logging.getLogger("financeiro_verdio.auth")
VALID_ROLES = {"Usuário", "Admin"}


def normalize_role(role: Any) -> str:
    return finance_role_label(role)


def get_user_role(uid: str) -> str:
    return get_finance_role(str(uid)) or "Usuário"


def get_all_users() -> list[dict[str, Any]]:
    try:
        return get_all_shared_users()
    except Exception:
        log.exception("Erro ao carregar usuários compartilhados do Simulador.")
        st.error(
            "Não foi possível carregar os usuários compartilhados. "
            "Consulte os logs do aplicativo."
        )
        return []


def update_finance_access(uid: str, enabled: bool, role: str) -> bool:
    try:
        return _update_finance_access(
            str(uid),
            enabled=bool(enabled),
            role=role,
        )
    except ValueError as exc:
        st.error(str(exc))
        return False
    except Exception:
        log.exception("Erro ao atualizar acesso financeiro de %s", uid)
        st.error("Não foi possível atualizar o acesso ao Financeiro.")
        return False


# Compatibilidade com chamadas antigas. No Financeiro, status e role significam
# apenas autorização para este aplicativo; identidade e senha continuam no Simulador.
def update_user_status(uid: str, is_disabled: bool) -> bool:
    user = get_shared_user(str(uid))
    if not user:
        return False
    current_role = get_finance_role(str(uid)) or "Usuário"
    return update_finance_access(
        str(uid),
        enabled=not bool(is_disabled),
        role=current_role,
    )


def update_user_role(uid: str, new_role: str) -> bool:
    user = get_shared_user(str(uid))
    if not user:
        return False
    current_role = get_finance_role(str(uid))
    enabled = current_role is not None
    return update_finance_access(
        str(uid),
        enabled=enabled,
        role=new_role,
    )


def create_new_user(email: str, password: str, role: str) -> bool:
    st.info(
        "Os usuários são administrados no Simulador de Telemetria. "
        "Cadastre a identidade lá e depois habilite o acesso ao Financeiro aqui."
    )
    return False
