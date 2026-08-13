from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import secrets as pysecrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Iterable, Iterator

import streamlit as st
from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

log = logging.getLogger("financeiro_verdio.mongo")
DEFAULT_DB_NAME = "financeiro_verdio"
PASSWORD_SCHEME = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 600_000


def _secret_value(*names: str, default: str = "") -> str:
    for name in names:
        try:
            value = st.secrets[name]
        except Exception:
            value = None
        if value is None:
            value = os.getenv(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return default


def _mongo_uri() -> str:
    uri = _secret_value(
        "FINANCEIRO_MONGO_CONNECTION_STRING",
        "MONGO_CONNECTION_STRING",
        "mongo_connection_string",
    )
    if not uri:
        raise RuntimeError(
            "MongoDB não configurado. Defina MONGO_CONNECTION_STRING nos Secrets do Streamlit Cloud."
        )
    return uri


def _db_name() -> str:
    return _secret_value("FINANCEIRO_MONGO_DB", default=DEFAULT_DB_NAME)


def _mongo_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, dict):
        return {str(k): _mongo_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_mongo_safe(v) for v in value]
    if hasattr(value, "to_pydatetime"):
        try:
            converted = value.to_pydatetime()
            if isinstance(converted, datetime):
                return converted if converted.tzinfo else converted.replace(tzinfo=timezone.utc)
        except Exception:
            pass
    if hasattr(value, "item"):
        try:
            return _mongo_safe(value.item())
        except Exception:
            pass
    return str(value)


def _public_document(document: dict[str, Any] | None) -> dict[str, Any]:
    if not document:
        return {}
    return {
        k: v
        for k, v in document.items()
        if k != "_id" and not str(k).startswith("__mongo_")
    }


def _hash_password(password: str, *, salt: bytes | None = None) -> str:
    if not isinstance(password, str) or len(password) < 8:
        raise ValueError("A senha deve possuir pelo menos 8 caracteres.")
    salt = salt or pysecrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
    )
    return (
        f"{PASSWORD_SCHEME}${PASSWORD_ITERATIONS}$"
        f"{base64.urlsafe_b64encode(salt).decode('ascii')}$"
        f"{base64.urlsafe_b64encode(digest).decode('ascii')}"
    )


def _verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, iterations_text, salt_text, digest_text = str(encoded).split("$", 3)
        if scheme != PASSWORD_SCHEME:
            return False
        iterations = int(iterations_text)
        salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_text.encode("ascii"))
        candidate = hashlib.pbkdf2_hmac(
            "sha256", str(password).encode("utf-8"), salt, iterations
        )
        return hmac.compare_digest(candidate, expected)
    except Exception:
        return False


@st.cache_resource(show_spinner="Conectando ao MongoDB financeiro...")
def get_mongo_client() -> MongoClient:
    client = MongoClient(
        _mongo_uri(),
        serverSelectionTimeoutMS=10_000,
        connectTimeoutMS=10_000,
        socketTimeoutMS=20_000,
        retryWrites=True,
        tz_aware=True,
        appname="financeiro-verdio",
    )
    client.admin.command("ping")
    return client


@st.cache_resource(show_spinner=False)
def get_mongo_database() -> Database:
    database = get_mongo_client()[_db_name()]
    _ensure_indexes(database)
    return database


def _ensure_indexes(database: Database) -> None:
    specs = [
        ("system_logs", [("timestamp", DESCENDING)], {"name": "idx_logs_timestamp"}),
        ("billing_history", [("cliente", ASCENDING), ("periodo_relatorio", ASCENDING)], {"unique": True, "name": "uniq_billing_current"}),
        ("billing_history", [("data_geracao", DESCENDING)], {"name": "idx_billing_history_date"}),
        ("billing_runs", [("data_geracao", DESCENDING)], {"name": "idx_billing_runs_date"}),
        ("billing_runs", [("period_key", ASCENDING), ("cliente", ASCENDING)], {"name": "idx_billing_runs_period_client"}),
        ("billing_runs__items", [("__mongo_parent_id", ASCENDING), ("item_index", ASCENDING)], {"name": "idx_run_items_parent"}),
        ("billing_terminal_snapshots", [("period_key", ASCENDING), ("cliente", ASCENDING)], {"name": "idx_snapshots_period_client"}),
        ("billing_terminal_snapshots", [("run_id", ASCENDING)], {"name": "idx_snapshots_run"}),
        ("billing_monthly_metrics", [("period_key", ASCENDING), ("cliente", ASCENDING)], {"name": "idx_metrics_period_client"}),
        ("billing_month_closures", [("period_key", ASCENDING)], {"unique": True, "name": "uniq_closure_period"}),
        ("trackers", [("Modelo", ASCENDING)], {"name": "idx_trackers_model"}),
        ("client_contracts", [("cliente", ASCENDING)], {"name": "idx_contracts_client"}),
        ("terminais_parceiros", [("parceiro", ASCENDING)], {"name": "idx_partner_terminals"}),
    ]
    for collection_name, keys, kwargs in specs:
        try:
            database[collection_name].create_index(keys, **kwargs)
        except Exception:
            log.exception("Falha ao garantir índice %s em %s.", kwargs.get("name"), collection_name)


def _ensure_bootstrap_admin(database: Database) -> None:
    if database["users"].estimated_document_count() > 0:
        return
    email = _secret_value("FINANCEIRO_ADMIN_EMAIL", "ADMIN_EMAIL").lower()
    password = _secret_value("FINANCEIRO_ADMIN_PASSWORD", "ADMIN_PASSWORD")
    if not email or not password:
        log.warning(
            "Banco financeiro sem usuários. Configure FINANCEIRO_ADMIN_EMAIL e "
            "FINANCEIRO_ADMIN_PASSWORD nos Secrets para criar o primeiro administrador."
        )
        return
    now = datetime.now(timezone.utc)
    try:
        database["users"].insert_one(
            {
                "_id": uuid.uuid4().hex,
                "email": email,
                "password_hash": _hash_password(password),
                "role": "Admin",
                "disabled": False,
                "created_at": now,
                "last_sign_in_at": None,
                "updated_at": now,
                "bootstrap": True,
            }
        )
        log.warning("Usuário administrador inicial criado no MongoDB: %s", email)
    except DuplicateKeyError:
        pass


@dataclass
class MongoDocumentSnapshot:
    id: str
    reference: "MongoDocumentReference"
    _document: dict[str, Any] | None

    @property
    def exists(self) -> bool:
        return self._document is not None

    def to_dict(self) -> dict[str, Any]:
        return _public_document(self._document)


class MongoQuery:
    def __init__(
        self,
        database: Database,
        collection_name: str,
        *,
        parent_id: str | None = None,
        parent_collection: str | None = None,
        filters: list[tuple[str, str, Any]] | None = None,
        sorts: list[tuple[str, int]] | None = None,
        limit_value: int | None = None,
    ) -> None:
        self.database = database
        self.collection_name = collection_name
        self.parent_id = parent_id
        self.parent_collection = parent_collection
        self.filters = list(filters or [])
        self.sorts = list(sorts or [])
        self.limit_value = limit_value

    def _clone(self, **changes: Any) -> "MongoQuery":
        values = {
            "database": self.database,
            "collection_name": self.collection_name,
            "parent_id": self.parent_id,
            "parent_collection": self.parent_collection,
            "filters": self.filters,
            "sorts": self.sorts,
            "limit_value": self.limit_value,
        }
        values.update(changes)
        return MongoQuery(**values)

    def where(self, field_path: str, op_string: str, value: Any) -> "MongoQuery":
        return self._clone(
            filters=self.filters + [(str(field_path), str(op_string), _mongo_safe(value))]
        )

    def order_by(self, field_path: str, direction: Any = "ASCENDING") -> "MongoQuery":
        descending = direction in (-1, DESCENDING) or str(direction).upper().endswith("DESCENDING")
        return self._clone(
            sorts=self.sorts + [(str(field_path), DESCENDING if descending else ASCENDING)]
        )

    def limit(self, count: int) -> "MongoQuery":
        return self._clone(limit_value=max(0, int(count)))

    def _mongo_filter(self) -> dict[str, Any]:
        query: dict[str, Any] = {}
        if self.parent_id is not None:
            query["__mongo_parent_id"] = self.parent_id
            query["__mongo_parent_collection"] = self.parent_collection
        op_map = {"!=": "$ne", "<": "$lt", "<=": "$lte", ">": "$gt", ">=": "$gte", "in": "$in", "not-in": "$nin"}
        for field, op, value in self.filters:
            if op in {"==", "array_contains", "array-contains"}:
                query[field] = value
            elif op in op_map:
                query.setdefault(field, {})
                query[field][op_map[op]] = value
            else:
                raise NotImplementedError(f"Operador de consulta não suportado: {op}")
        return query

    def stream(self) -> Iterator[MongoDocumentSnapshot]:
        cursor = self.database[self.collection_name].find(self._mongo_filter())
        if self.sorts:
            cursor = cursor.sort(self.sorts)
        if self.limit_value is not None:
            cursor = cursor.limit(self.limit_value)
        for document in cursor:
            doc_id = str(document.get("_id"))
            ref = MongoDocumentReference(
                self.database,
                self.collection_name,
                doc_id,
                parent_id=self.parent_id,
                parent_collection=self.parent_collection,
            )
            yield MongoDocumentSnapshot(doc_id, ref, document)

    def get(self) -> list[MongoDocumentSnapshot]:
        return list(self.stream())


class MongoCollectionReference(MongoQuery):
    def document(self, document_id: str | None = None) -> "MongoDocumentReference":
        return MongoDocumentReference(
            self.database,
            self.collection_name,
            str(document_id or uuid.uuid4().hex),
            parent_id=self.parent_id,
            parent_collection=self.parent_collection,
        )

    def add(self, data: dict[str, Any]):
        ref = self.document()
        ref.set(data)
        return datetime.now(timezone.utc), ref


class MongoDocumentReference:
    def __init__(
        self,
        database: Database,
        collection_name: str,
        document_id: str,
        *,
        parent_id: str | None = None,
        parent_collection: str | None = None,
    ) -> None:
        self.database = database
        self.collection_name = collection_name
        self.id = str(document_id)
        self.parent_id = parent_id
        self.parent_collection = parent_collection

    def _filter(self) -> dict[str, Any]:
        query: dict[str, Any] = {"_id": self.id}
        if self.parent_id is not None:
            query["__mongo_parent_id"] = self.parent_id
            query["__mongo_parent_collection"] = self.parent_collection
        return query

    def get(self) -> MongoDocumentSnapshot:
        document = self.database[self.collection_name].find_one(self._filter())
        return MongoDocumentSnapshot(self.id, self, document)

    def set(self, data: dict[str, Any], merge: bool = False) -> None:
        payload = _mongo_safe(dict(data or {}))
        if self.parent_id is not None:
            payload["__mongo_parent_id"] = self.parent_id
            payload["__mongo_parent_collection"] = self.parent_collection
        collection = self.database[self.collection_name]
        if merge:
            collection.update_one(self._filter(), {"$set": payload}, upsert=True)
        else:
            payload["_id"] = self.id
            collection.replace_one(self._filter(), payload, upsert=True)

    def update(self, data: dict[str, Any]) -> None:
        self.database[self.collection_name].update_one(
            self._filter(), {"$set": _mongo_safe(dict(data or {}))}, upsert=False
        )

    def delete(self) -> None:
        self.database[self.collection_name].delete_one(self._filter())

    def collection(self, name: str) -> MongoCollectionReference:
        return MongoCollectionReference(
            self.database,
            f"{self.collection_name}__{str(name)}",
            parent_id=self.id,
            parent_collection=self.collection_name,
        )


class MongoBatch:
    def __init__(self) -> None:
        self.operations: list[tuple[str, MongoDocumentReference, dict[str, Any] | None, bool]] = []

    def set(self, ref: MongoDocumentReference, data: dict[str, Any], merge: bool = False) -> None:
        self.operations.append(("set", ref, dict(data or {}), bool(merge)))

    def update(self, ref: MongoDocumentReference, data: dict[str, Any]) -> None:
        self.operations.append(("update", ref, dict(data or {}), False))

    def delete(self, ref: MongoDocumentReference) -> None:
        self.operations.append(("delete", ref, None, False))

    def commit(self) -> None:
        for operation, ref, data, merge in self.operations:
            if operation == "set":
                ref.set(data or {}, merge=merge)
            elif operation == "update":
                ref.update(data or {})
            elif operation == "delete":
                ref.delete()
        self.operations.clear()


class MongoDatabaseCompat:
    def __init__(self, database: Database) -> None:
        self.database = database

    def collection(self, name: str) -> MongoCollectionReference:
        return MongoCollectionReference(self.database, str(name))

    def batch(self) -> MongoBatch:
        return MongoBatch()


class MongoAuthClient:
    def __init__(self, database: Database) -> None:
        self.database = database

    def sign_in_with_email_and_password(self, email: str, password: str) -> dict[str, Any]:
        normalized_email = str(email or "").strip().lower()
        user = self.database["users"].find_one({"email": normalized_email})
        if not user or bool(user.get("disabled")):
            raise ValueError("E-mail ou senha inválidos.")
        if not _verify_password(str(password or ""), str(user.get("password_hash") or "")):
            raise ValueError("E-mail ou senha inválidos.")
        now = datetime.now(timezone.utc)
        self.database["users"].update_one(
            {"_id": user["_id"]}, {"$set": {"last_sign_in_at": now, "updated_at": now}}
        )
        return {"localId": str(user["_id"]), "email": normalized_email}


class MongoUserRecord:
    def __init__(self, document: dict[str, Any]) -> None:
        self.uid = str(document.get("_id"))
        self.email = str(document.get("email") or "")
        self.disabled = bool(document.get("disabled"))
        self.user_metadata = SimpleNamespace(
            creation_timestamp=_datetime_ms(document.get("created_at")),
            last_sign_in_timestamp=_datetime_ms(document.get("last_sign_in_at")),
        )


def _datetime_ms(value: Any) -> int | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return int(value.timestamp() * 1000)


class MongoUserIterator:
    def __init__(self, users: Iterable[MongoUserRecord]) -> None:
        self._users = list(users)

    def iterate_all(self) -> Iterator[MongoUserRecord]:
        return iter(self._users)


class MongoAuthAdmin:
    def __init__(self, database: Database) -> None:
        self.database = database

    def list_users(self) -> MongoUserIterator:
        return MongoUserIterator(
            MongoUserRecord(document)
            for document in self.database["users"].find({}).sort("email", ASCENDING)
        )

    def create_user(self, *, email: str, password: str, disabled: bool = False) -> MongoUserRecord:
        normalized_email = str(email or "").strip().lower()
        if not normalized_email or "@" not in normalized_email:
            raise ValueError("E-mail inválido.")
        now = datetime.now(timezone.utc)
        document = {
            "_id": uuid.uuid4().hex,
            "email": normalized_email,
            "password_hash": _hash_password(password),
            "role": "Usuário",
            "disabled": bool(disabled),
            "created_at": now,
            "last_sign_in_at": None,
            "updated_at": now,
        }
        try:
            self.database["users"].insert_one(document)
        except DuplicateKeyError as exc:
            raise ValueError("EMAIL_ALREADY_EXISTS") from exc
        return MongoUserRecord(document)

    def update_user(
        self,
        uid: str,
        *,
        disabled: bool | None = None,
        password: str | None = None,
    ) -> MongoUserRecord:
        changes: dict[str, Any] = {"updated_at": datetime.now(timezone.utc)}
        if disabled is not None:
            changes["disabled"] = bool(disabled)
        if password is not None:
            changes["password_hash"] = _hash_password(password)
        self.database["users"].update_one({"_id": str(uid)}, {"$set": changes})
        document = self.database["users"].find_one({"_id": str(uid)})
        if not document:
            raise ValueError("Usuário não encontrado.")
        return MongoUserRecord(document)


db = MongoDatabaseCompat(get_mongo_database())
auth_client = MongoAuthClient(get_mongo_database())
_auth_admin = MongoAuthAdmin(get_mongo_database())


def get_auth_admin_client() -> MongoAuthAdmin:
    return _auth_admin


def get_database_name() -> str:
    return _db_name()


def connection_diagnostics() -> dict[str, Any]:
    try:
        client = get_mongo_client()
        client.admin.command("ping")
        database = get_mongo_database()
        return {
            "ok": True,
            "database": database.name,
            "users": database["users"].estimated_document_count(),
            "billing_history": database["billing_history"].estimated_document_count(),
        }
    except Exception as exc:
        return {"ok": False, "error": f"{exc.__class__.__name__}: {exc}"}
