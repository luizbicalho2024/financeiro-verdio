"""Cliente HTTP de leitura exclusivo do relatorio SUGESP / SIGYO.

Autenticacao carregada pelo modulo de credenciais existente; utiliza headers
nativos de requests e permite apenas overrides seguros nos Secrets.
Nunca tenta contornar desafios WAF e nao registra tokens.
"""
from __future__ import annotations

import re
import threading
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app_core.sigyo_api import (
    SIGYO_BASE_URL,
    SIGYO_TIMEOUT,
    SigyoApiError as _BaseSigyoApiError,
    normalize_token,
)


class SigyoApiError(_BaseSigyoApiError):
    def user_message(self) -> str:
        if self.status_code == 403 and self.detail and "Bloqueio Cloudflare" in self.detail:
            suffix = f" no endpoint '{self.endpoint}'" if self.endpoint else ""
            return (
                f"Erro HTTP 403{suffix}: o Cloudflare bloqueou a requisicao "
                "antes da validacao do token pela API SIGYO. "
                "Confira o Ray ID no diagnostico e a regra aplicada ao IP de saida."
            )
        return super().user_message()


_ALLOWED_HEADERS = {
    "accept": "Accept",
    "accept-language": "Accept-Language",
    "user-agent": "User-Agent",
    "referer": "Referer",
    "origin": "Origin",
    "x-requested-with": "X-Requested-With",
    "cache-control": "Cache-Control",
    "pragma": "Pragma",
}

_thread = threading.local()


def _headers_from_streamlit() -> dict[str, str]:
    """Le headers opcionais dos Secrets sem expor credenciais ou falhar sem Streamlit."""
    try:
        import streamlit as st
        raw = st.secrets.get("SIGYO_SUGESP_HEADERS", {})
        if isinstance(raw, Mapping):
            return {str(key): str(value) for key, value in raw.items() if value is not None}
    except (ImportError, KeyError, OSError, FileNotFoundError):
        pass
    return {}


def _build_headers(
    base_url: str,
    overrides: Mapping[str, Any] | None = None,
) -> dict[str, str]:
    """Imita um cliente Python requests real, sem fingir ser um navegador.

    GET nao envia Content-Type, Origin, Referer ou X-Requested-With sem
    necessidade. Headers adicionais so entram se forem explicitamente
    configurados e estiverem na lista permitida.
    """
    headers = {
        # Mesmos headers do teste.py que consultou /clientes com HTTP 200.
        # Authorization e sempre definido por requisicao em get_json.
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "SIGYO-API-Client/1.0",
        "Cache-Control": "no-cache",
    }
    _apply_overrides(headers, overrides)
    return headers


def _apply_overrides(
    headers: dict[str, str], overrides: Mapping[str, Any] | None
) -> None:
    for name, value in (overrides or {}).items():
        canonical = _ALLOWED_HEADERS.get(str(name).strip().lower())
        if canonical is None:
            continue  # Protege Authorization, Cookie, Host e cabecalhos sensiveis.
        sanitized = str(value).strip()
        if sanitized and "\r" not in sanitized and "\n" not in sanitized:
            headers[canonical] = sanitized


def _session_for_thread() -> requests.Session:
    """Pool HTTPS reutilizavel por thread, sem armazenar o token na sessao."""
    session = getattr(_thread, "session", None)
    if session is None:
        session = requests.Session()
        # Politica equivalente a do teste.py local, sem retry para HTTP 403.
        retries = Retry(
            total=3,
            connect=3,
            read=2,
            status=3,
            backoff_factor=1,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
            respect_retry_after_header=True,
            raise_on_status=False,
        )
        session.mount(
            "https://",
            HTTPAdapter(pool_connections=5, pool_maxsize=10, max_retries=retries),
        )
        _thread.session = session
    return session


def _http_get(url: str, **kwargs: Any) -> requests.Response:
    return _session_for_thread().get(url, **kwargs)


def _safe_error_detail(response: requests.Response, token: str) -> str:
    """Retorna somente diagnostico seguro: sem HTML WAF nem token."""
    body = (response.text or "")[:8000]
    lower = body.lower()
    cloudflare = response.status_code == 403 and (
        "sorry, you have been blocked" in lower
        or "attention required!" in lower
        or ("cloudflare" in lower and "<html" in lower)
    )
    ray = re.sub(
        r"[^a-zA-Z0-9.\-]", "", response.headers.get("cf-ray", "")
    )[:100]
    if cloudflare:
        return "Bloqueio Cloudflare antes da API SIGYO" + (
            f" | Ray ID: {ray}" if ray else ""
        )

    detail = response.reason or "Requisicao recusada"
    try:
        payload = response.json()
        if isinstance(payload, Mapping):
            parts = [
                str(payload[key])
                for key in ("message", "error", "detail", "title")
                if payload.get(key)
            ]
            if parts:
                detail = " | ".join(parts)
    except (ValueError, TypeError):
        pass
    detail = re.sub(r"<[^>]+>", " ", detail)
    detail = re.sub(r"\s+", " ", detail).strip()[:450]
    if token:
        detail = detail.replace(token, "***")
    return detail + (f" | request-id={ray}" if ray else "")


def get_json(
    token: Any,
    endpoint: str,
    *,
    params: Mapping[str, Any] | None = None,
    base_url: str = SIGYO_BASE_URL,
    request_headers: Mapping[str, Any] | None = None,
):
    token = normalize_token(token)
    if not token:
        raise SigyoApiError("Token SIGYO nao informado.", endpoint=endpoint)

    endpoint = str(endpoint).strip().lstrip("/")
    base_url = str(base_url).strip().rstrip("/")
    parsed = urlsplit(base_url)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9/_-]*", endpoint)
    ):
        raise SigyoApiError("Endpoint ou URL HTTPS da API invalidos.", endpoint=endpoint)

    headers = _build_headers(base_url, _headers_from_streamlit())
    if request_headers:
        _apply_overrides(headers, request_headers)
    headers["Authorization"] = f"Bearer {token}"

    try:
        response = _http_get(
            f"{base_url}/{endpoint}",
            headers=headers,
            params=dict(params or {}),
            timeout=SIGYO_TIMEOUT,
            allow_redirects=False,
            verify=True,
        )
    except requests.Timeout as exc:
        raise SigyoApiError("Tempo limite excedido.", endpoint=endpoint) from exc
    except requests.ConnectionError as exc:
        raise SigyoApiError("Falha de conexao.", endpoint=endpoint) from exc
    except requests.RequestException as exc:
        raise SigyoApiError("Falha na requisicao.", endpoint=endpoint) from exc

    if not 200 <= response.status_code < 300:
        raise SigyoApiError(
            response.reason or "Requisicao recusada.",
            status_code=response.status_code,
            endpoint=endpoint,
            detail=_safe_error_detail(response, token),
        )
    if response.status_code == 204 or not response.content:
        return []
    try:
        return response.json()
    except ValueError as exc:
        raise SigyoApiError(
            "Resposta da API nao e JSON valido.",
            status_code=response.status_code,
            endpoint=endpoint,
            detail="Resposta inesperada (nao JSON).",
        ) from exc
