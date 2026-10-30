"""Credenciais de leitura do relatorio SUGESP.

Streamlit Secrets tem prioridade; variavel de ambiente serve para desenvolvimento
local. O token nunca e gravado em arquivos ou logs pelo modulo.
"""
from __future__ import annotations

from typing import Any, Mapping

from app_core.sigyo_api import SIGYO_BASE_URL, normalize_token


def _get(source: Mapping[str, Any] | None, key: str) -> str:
    if source is None:
        return ""
    try:
        return str(source.get(key, "") or "").strip()
    except (KeyError, FileNotFoundError, OSError):
        # st.secrets sem arquivo configurado pode levantar FileNotFoundError.
        return ""


def resolve_configuration(
    secrets: Mapping[str, Any] | None,
    environment: Mapping[str, Any] | None,
) -> tuple[str, str, str]:
    """Retorna (token normalizado, origem, URL); sem imprimir credenciais."""
    token_secret = normalize_token(_get(secrets, "SIGYO_API_TOKEN"))
    token_env = normalize_token(_get(environment, "SIGYO_API_TOKEN"))

    if token_secret:
        token, source = token_secret, "Secrets do Streamlit"
    elif token_env:
        token, source = token_env, "variavel de ambiente"
    else:
        token, source = "", "nao configurado"

    base_url = (
        _get(secrets, "SIGYO_API_BASE_URL")
        or _get(environment, "SIGYO_API_BASE_URL")
        or SIGYO_BASE_URL
    ).rstrip("/")
    return token, source, base_url