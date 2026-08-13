from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import streamlit as st
from passlib.context import CryptContext
from pymongo import ASCENDING
from pymongo.collection import Collection
from pymongo.database import Database

from mongo_config import get_mongo_client

log = logging.getLogger("financeiro_verdio.shared_identity")

DEFAULT_IDENTITY_DB = "simulador_db"
FINANCE_ROLE_USER = "user"
FINANCE_ROLE_ADMIN = "admin"
VALID_FINANCE_ROLES = {FINANCE_ROLE_USER, FINANCE_ROLE_ADMIN}

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _secret_value(*names: str, default: str = "") -> str:
    for name in names:
        try:
            value = st.secrets.get(name)
        except Exception:
            value = None
        if value not in (None, ""):
            return str(value).strip()
    return default


def identity_database_name() -> str:
    return _secret_value(
        "IDENTITY_MONGO_DB",
        "SIMULADOR_MONGO_DB",
        default=DEFAULT_IDENTITY_DB,
    )


@st.cache_resource(show_spinner=False)
def get_identity_database() -> Database:
    database = get_mongo_client()[identity_database_name()]
    ensure_shared_user_schema(database)
    return database


def get_shared_users_collection() -> Collection:
    return get_identity_database()["users"]


def _normalize_username(value: Any) -> str:
    return str(value or "").strip().lower()


def _normalize_email(value: Any) -> str:
    return str(value or "").strip().lower()


def _normalize_finance_role(value: Any) -> str:
    return FINANCE_ROLE_ADMIN if str(value or "").strip().lower() == "admin" else FINANCE_ROLE_USER


def finance_role_label(value: Any) -> str:
    return "Admin" if _normalize_finance_role(value) == FINANCE_ROLE_ADMIN else "Usuário"


def _effective_finance_access(user: dict[str, Any] | None) -> tuple[bool, str]:
    if not user or user.get("active") is False:
        return False, FINANCE_ROLE_USER

    apps = user.get("apps")
    apps = apps if isinstance(apps, dict) else {}
    finance = apps.get("financeiro")
    finance = finance if isinstance(finance, dict) else None

    if finance is not None:
        enabled = bool(finance.get("enabled", False))
        role = _normalize_finance_role(finance.get("role"))
        return enabled, role

    # Compatibilidade para usuários existentes antes da implantação do controle
    # por aplicação: administradores globais entram no Financeiro como Admin.
    global_role = str(user.get("role") or "user").strip().lower()
    if global_role == "admin":
        return True, FINANCE_ROLE_ADMIN

    return False, FINANCE_ROLE_USER


def ensure_shared_user_schema(database: Database | None = None) -> None:
    """Adiciona metadados de aplicações sem alterar credenciais ou identidade."""
    database = database or get_mongo_client()[identity_database_name()]
    users = database["users"]

    try:
        users.create_index(
            [("username", ASCENDING)],
            unique=True,
            name="uq_users_username",
        )
    except Exception:
        # O Simulador já cria esse índice. Ignoramos somente divergência de nome.
        pass

    now = datetime.now(timezone.utc)

    for user in users.find({}):
        update: dict[str, Any] = {}
        global_role = str(user.get("role") or "user").strip().lower()
        global_active = user.get("active") is not False

        apps = user.get("apps")
        apps = apps if isinstance(apps, dict) else {}

        simulator_app = apps.get("simulador")
        if not isinstance(simulator_app, dict):
            update["apps.simulador"] = {
                "enabled": global_active,
                "role": global_role,
                "updated_at": now,
            }

        finance_app = apps.get("financeiro")
        if not isinstance(finance_app, dict):
            update["apps.financeiro"] = {
                "enabled": global_role == "admin" and global_active,
                "role": FINANCE_ROLE_ADMIN if global_role == "admin" else FINANCE_ROLE_USER,
                "updated_at": now,
            }

        if update:
            users.update_one({"_id": user["_id"]}, {"$set": update})


def _find_user(identifier: str) -> dict[str, Any] | None:
    normalized = _normalize_username(identifier)
    if not normalized:
        return None

    return get_shared_users_collection().find_one(
        {
            "$or": [
                {"username": normalized},
                {"email": normalized},
            ]
        }
    )


def get_shared_user(identifier: str) -> dict[str, Any] | None:
    user = _find_user(identifier)
    if not user:
        return None

    result = dict(user)
    result["_id"] = str(result.get("_id"))
    result.pop("hashed_password", None)
    return result


def authenticate_finance_user(identifier: str, password: str) -> dict[str, Any]:
    """Autentica usando exatamente o hash bcrypt mantido pelo Simulador."""
    user = _find_user(identifier)

    if not user or user.get("active") is False:
        raise ValueError("Credenciais inválidas ou usuário sem acesso ao Financeiro.")

    enabled, finance_role = _effective_finance_access(user)
    if not enabled:
        raise ValueError("Credenciais inválidas ou usuário sem acesso ao Financeiro.")

    hashed_password = str(user.get("hashed_password") or "")
    if not hashed_password:
        raise ValueError("Credenciais inválidas ou usuário sem acesso ao Financeiro.")

    try:
        valid_password = pwd_context.verify(str(password or ""), hashed_password)
    except Exception:
        valid_password = False

    if not valid_password:
        raise ValueError("Credenciais inválidas ou usuário sem acesso ao Financeiro.")

    username = _normalize_username(user.get("username"))
    email = _normalize_email(user.get("email"))
    name = str(user.get("name") or username or email).strip()

    now = datetime.now(timezone.utc)
    get_shared_users_collection().update_one(
        {"_id": user["_id"]},
        {
            "$set": {
                "last_finance_sign_in_at": now,
                "apps.financeiro.last_sign_in_at": now,
            }
        },
    )

    return {
        "localId": username,
        "username": username,
        "email": email,
        "name": name,
        "role": finance_role_label(finance_role),
    }


def get_finance_role(identifier: str) -> str | None:
    user = _find_user(identifier)
    enabled, role = _effective_finance_access(user)
    if not enabled:
        return None
    return finance_role_label(role)


def get_all_shared_users() -> list[dict[str, Any]]:
    users: list[dict[str, Any]] = []

    projection = {"hashed_password": 0}
    for document in get_shared_users_collection().find({}, projection).sort("name", ASCENDING):
        enabled, finance_role = _effective_finance_access(document)
        username = _normalize_username(document.get("username"))
        users.append(
            {
                "uid": username,
                "username": username,
                "name": str(document.get("name") or username).strip(),
                "email": _normalize_email(document.get("email")),
                "global_role": str(document.get("role") or "user").strip().lower(),
                "global_active": document.get("active") is not False,
                "finance_enabled": enabled,
                "finance_role": finance_role_label(finance_role),
                "created_at": document.get("created_at"),
                "updated_at": document.get("updated_at"),
                "last_finance_sign_in_at": document.get("last_finance_sign_in_at"),
            }
        )
    return users


def count_finance_admins() -> int:
    count = 0
    for user in get_shared_users_collection().find({"active": {"$ne": False}}):
        enabled, role = _effective_finance_access(user)
        if enabled and role == FINANCE_ROLE_ADMIN:
            count += 1
    return count


def update_finance_access(
    username: str,
    *,
    enabled: bool,
    role: str,
) -> bool:
    normalized_username = _normalize_username(username)
    user = get_shared_users_collection().find_one({"username": normalized_username})
    if not user:
        raise ValueError("Usuário não encontrado na base compartilhada do Simulador.")

    current_enabled, current_role = _effective_finance_access(user)
    new_role = _normalize_finance_role(role)

    removing_admin = (
        current_enabled
        and current_role == FINANCE_ROLE_ADMIN
        and (not enabled or new_role != FINANCE_ROLE_ADMIN)
    )
    if removing_admin and count_finance_admins() <= 1:
        raise ValueError("Não é possível remover o último administrador do Financeiro.")

    now = datetime.now(timezone.utc)
    result = get_shared_users_collection().update_one(
        {"_id": user["_id"]},
        {
            "$set": {
                "apps.financeiro.enabled": bool(enabled),
                "apps.financeiro.role": new_role,
                "apps.financeiro.updated_at": now,
            }
        },
    )
    return result.matched_count > 0


def connection_diagnostics() -> dict[str, Any]:
    try:
        database = get_identity_database()
        database.command("ping")
        total_users = database["users"].estimated_document_count()
        return {
            "ok": True,
            "database": database.name,
            "collection": "users",
            "total_users": int(total_users),
        }
    except Exception as exc:
        log.exception("Falha ao consultar identidade compartilhada.")
        return {
            "ok": False,
            "database": identity_database_name(),
            "collection": "users",
            "error": f"{exc.__class__.__name__}: {exc}",
        }
