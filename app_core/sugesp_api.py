"""Cliente HTTP exclusivo do relatorio SUGESP.

Mantem intacto app_core.sigyo_api, utilizado pelas outras paginas.
Headers personalizados podem ser fornecidos por [SIGYO_SUGESP_HEADERS]
nos Secrets do Streamlit. Nao armazena nem registra credenciais.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

import requests

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
                f"Erro HTTP 403{suffix}: bloqueio na protecao Cloudflare "
                "antes da API SIGYO. Confirme o IP de saida do Streamlit "
                "e solicite ao administrador da API a revisao da regra WAF."
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


def _headers_from_streamlit() -> dict[str, str]:
    """Le configuracao opcional sem falhar quando executado fora do Streamlit."""
    try:
        import streamlit as st
        raw = st.secrets.get("SIGYO_SUGESP_HEADERS", {})
        if isinstance(raw, Mapping):
            return {str(key): str(value) for key, value in raw.items() if value is not None}
    except Exception:
        # Headers opcionais nunca podem derrubar a consulta principal.
        pass
    return {}


def _build_headers(base_url: str, overrides: Mapping[str, Any] | None = None) -> dict[str, str]:
    parsed = urlsplit(base_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    headers = {
        "Authorization": "",  # Preenchido exclusivamente por get_json.
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        "Content-Type": "application/json",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        "Referer": f"{origin}/",
        "X-Requested-With": "XMLHttpRequest",
    }
    for name, value in (overrides or {}).items():
        canonical = _ALLOWED_HEADERS.get(str(name).strip().lower())
        if canonical is None:
            continue  # Nao permite sobrescrever Authorization, Host ou Cookie.
        value = str(value).strip()
        if value and "\r" not in value and "\n" not in value:
            headers[canonical] = value
    return headers


def _safe_error_detail(response: requests.Response, token: str) -> str:
    """Diagnosticavel, sem exibir HTML do WAF nem o token."""
    body = (response.text or "")[:8000]
    lower = body.lower()
    is_cloudflare = response.status_code == 403 and (
        "sorry, you have been blocked" in lower
        or "attention required!" in lower
        or ("cloudflare" in lower and "<html" in lower)
    )
    ray = re.sub(r"[^a-zA-Z0-9.\-]", "", response.headers.get("cf-ray", ""))[:100]
    if is_cloudflare:
        return "Bloqueio Cloudflare antes da API SIGYO" + (f" | Ray ID: {ray}" if ray else "")

    detail = response.reason or "Requisicao recusada"
    try:
        payload = response.json()
        if isinstance(payload, Mapping):
            parts = [str(payload[key]) for key in ("message", "error", "detail", "title") if payload.get(key)]
            if parts:
                detail = " | ".join(parts)
    except ValueError:
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
    if not endpoint or not base_url.startswith("https://"):
        raise SigyoApiError("Endpoint ou URL HTTPS da API invalidos.", endpoint=endpoint)

    headers = _build_headers(base_url, _headers_from_streamlit())
    if request_headers:
        # Configuracao explicita substitui headers opcionais sem afetar Authorization.
        for name, value in request_headers.items():
            canonical = _ALLOWED_HEADERS.get(str(name).strip().lower())
            if canonical is not None:
                value = str(value).strip()
                if value and "\r" not in value and "\n" not in value:
                    headers[canonical] = value
    headers["Authorization"] = f"Bearer {token}"

    try:
        response = requests.get(
            f"{base_url}/{endpoint}",
            headers=headers,
            params=dict(params or {}),
            timeout=SIGYO_TIMEOUT,
            allow_redirects=False,
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
