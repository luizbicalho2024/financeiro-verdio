from __future__ import annotations

import re
from typing import Any, Mapping

import requests


SIGYO_BASE_URL = "https://sigyo.uzzipay.com/api"
SIGYO_TIMEOUT = (15, 180)


class SigyoApiError(RuntimeError):
    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        endpoint: str | None = None,
        detail: str | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.endpoint = endpoint
        self.detail = detail

    def user_message(self) -> str:
        endpoint = (
            f" no endpoint '{self.endpoint}'"
            if self.endpoint
            else ""
        )

        if self.status_code == 401:
            return (
                f"Erro HTTP 401{endpoint}: "
                "token SIGYO inválido ou expirado."
            )

        if self.status_code == 403:
            return (
                f"Erro HTTP 403{endpoint}: "
                "a API SIGYO recusou o acesso. "
                "Verifique se o token está ativo e possui autorização "
                "para esta API."
            )

        if self.status_code == 429:
            return (
                f"Erro HTTP 429{endpoint}: "
                "limite de requisições da API SIGYO atingido."
            )

        if self.status_code and self.status_code >= 500:
            return (
                f"Erro HTTP {self.status_code}{endpoint}: "
                "falha interna ou indisponibilidade da API SIGYO."
            )

        if self.status_code:
            return (
                f"Erro HTTP {self.status_code}{endpoint}: "
                f"{self.message}"
            )

        return (
            f"Falha de comunicação com a API SIGYO{endpoint}: "
            f"{self.message}"
        )


def normalize_token(value: Any) -> str:
    """
    Aceita:
      TOKEN
      Bearer TOKEN
      Authorization: Bearer TOKEN
      "TOKEN"
      'TOKEN'

    Retorna somente o token.
    """

    token = str(value or "").strip()

    if not token:
        return ""

    token = re.sub(
        r"^\s*Authorization\s*:\s*",
        "",
        token,
        flags=re.IGNORECASE,
    ).strip()

    while (
        len(token) >= 2
        and token[0] == token[-1]
        and token[0] in ('"', "'")
    ):
        token = token[1:-1].strip()

    while re.match(
        r"^Bearer\s+",
        token,
        flags=re.IGNORECASE,
    ):
        token = re.sub(
            r"^Bearer\s+",
            "",
            token,
            count=1,
            flags=re.IGNORECASE,
        ).strip()

    return token


def _safe_detail(response: requests.Response) -> str:
    """
    Retorna somente diagnóstico seguro da API.
    Nunca inclui Authorization/token.
    """

    detail = ""

    try:
        payload = response.json()

        if isinstance(payload, dict):
            parts = []

            for key in (
                "message",
                "error",
                "detail",
                "name",
                "title",
            ):
                value = payload.get(key)

                if value:
                    parts.append(str(value))

            detail = " | ".join(parts)

        elif payload:
            detail = str(payload)

    except Exception:
        detail = response.text or ""

    detail = re.sub(
        r"<[^>]+>",
        " ",
        detail,
    )

    detail = re.sub(
        r"\s+",
        " ",
        detail,
    ).strip()

    detail = re.sub(
        r"(?i)(Bearer\s+)[A-Za-z0-9._~+/=-]+",
        r"\1***",
        detail,
    )

    request_id = (
        response.headers.get("x-request-id")
        or response.headers.get("x-correlation-id")
        or response.headers.get("cf-ray")
    )

    if request_id:
        if detail:
            detail += " | "

        detail += f"request-id={request_id}"

    return detail[:1000]


def get_json(
    token: Any,
    endpoint: str,
    *,
    params: Mapping[str, Any] | None = None,
    base_url: str = SIGYO_BASE_URL,
):
    token = normalize_token(token)

    if not token:
        raise SigyoApiError(
            "Token SIGYO não informado.",
            endpoint=endpoint,
        )

    endpoint = str(endpoint).strip().lstrip("/")
    base_url = str(base_url).strip().rstrip("/")

    url = f"{base_url}/{endpoint}"

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "Financeiro-Verdio-SUGESP/2026.10",
    }

    try:
        response = requests.get(
            url,
            headers=headers,
            params=dict(params or {}),
            timeout=SIGYO_TIMEOUT,
            allow_redirects=False,
        )

    except requests.Timeout as exc:
        raise SigyoApiError(
            "Tempo limite excedido.",
            endpoint=endpoint,
        ) from exc

    except requests.ConnectionError as exc:
        raise SigyoApiError(
            "Falha de conexão.",
            endpoint=endpoint,
        ) from exc

    except requests.RequestException as exc:
        raise SigyoApiError(
            str(exc),
            endpoint=endpoint,
        ) from exc

    if not 200 <= response.status_code < 300:
        raise SigyoApiError(
            response.reason or "Requisição recusada.",
            status_code=response.status_code,
            endpoint=endpoint,
            detail=_safe_detail(response),
        )

    if response.status_code == 204:
        return []

    if not response.content:
        return []

    try:
        return response.json()

    except ValueError as exc:
        raise SigyoApiError(
            "Resposta SIGYO não contém JSON válido.",
            status_code=response.status_code,
            endpoint=endpoint,
            detail=_safe_detail(response),
        ) from exc