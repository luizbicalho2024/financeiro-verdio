from __future__ import annotations

import base64
import io
import logging
from datetime import datetime, timezone
from typing import Any

import streamlit as st
from PIL import Image

from app_core.branding import DEFAULT_BRANDING, normalize_branding
from firebase_config import db

log = logging.getLogger("financeiro_verdio.settings")
BRANDING_DOCUMENT_PATH = ("settings", "branding")
MAX_LOGO_BYTES = 220 * 1024
MAX_LOGO_WIDTH = 900
MAX_LOGO_HEIGHT = 360


@st.cache_data(ttl=120, show_spinner=False)
def get_branding() -> dict[str, Any]:
    try:
        document = db.collection(BRANDING_DOCUMENT_PATH[0]).document(BRANDING_DOCUMENT_PATH[1]).get()
        if document.exists:
            return normalize_branding(document.to_dict())
    except Exception:
        log.exception("Falha ao carregar identidade visual do Firestore.")
    return normalize_branding(DEFAULT_BRANDING)


def save_branding(settings: dict[str, Any]) -> bool:
    normalized = normalize_branding(settings)
    payload = dict(normalized)
    payload["updated_at"] = datetime.now(timezone.utc)
    try:
        db.collection(BRANDING_DOCUMENT_PATH[0]).document(BRANDING_DOCUMENT_PATH[1]).set(payload, merge=True)
        get_branding.clear()
        return True
    except Exception:
        log.exception("Falha ao salvar identidade visual.")
        return False


def update_logo(raw_bytes: bytes, filename: str, *, sidebar: bool = False) -> tuple[bool, str | None]:
    if not raw_bytes:
        return False, "Arquivo de imagem vazio."

    try:
        processed, mime = optimize_logo(raw_bytes)
    except Exception:
        log.exception("Falha ao processar logomarca.")
        return False, "Não foi possível processar a imagem. Use PNG, JPG, JPEG ou WEBP."

    if len(processed) > MAX_LOGO_BYTES:
        return False, "A imagem continuou muito grande após a otimização. Use uma logomarca mais simples."

    branding = get_branding()
    prefix = "sidebar_logo" if sidebar else "logo"
    branding[f"{prefix}_base64"] = base64.b64encode(processed).decode("ascii")
    branding[f"{prefix}_mime"] = mime
    branding[f"{prefix}_filename"] = str(filename or "logo").strip()[:255]

    if save_branding(branding):
        return True, None
    return False, "Não foi possível salvar a logomarca no Firestore."


def reset_logo(*, sidebar: bool = False) -> bool:
    branding = get_branding()
    prefix = "sidebar_logo" if sidebar else "logo"
    branding[f"{prefix}_base64"] = None
    branding[f"{prefix}_mime"] = None
    branding[f"{prefix}_filename"] = None
    return save_branding(branding)


def reset_branding_colors() -> bool:
    current = get_branding()
    for key, value in DEFAULT_BRANDING.items():
        if key.endswith("_color") or key in {"system_name", "system_subtitle", "footer_text"}:
            current[key] = value
    return save_branding(current)


def optimize_logo(raw_bytes: bytes) -> tuple[bytes, str]:
    """Redimensiona e comprime uma logomarca para caber com folga no documento Firestore."""
    image = Image.open(io.BytesIO(raw_bytes))
    image.load()
    image.thumbnail((MAX_LOGO_WIDTH, MAX_LOGO_HEIGHT), Image.Resampling.LANCZOS)

    has_alpha = "A" in image.getbands() or image.mode in {"LA", "PA"}
    if has_alpha:
        converted = image.convert("RGBA")
    else:
        converted = image.convert("RGB")

    png_buffer = io.BytesIO()
    converted.save(png_buffer, format="PNG", optimize=True)
    png_bytes = png_buffer.getvalue()
    if len(png_bytes) <= MAX_LOGO_BYTES:
        return png_bytes, "image/png"

    # WEBP mantém transparência e reduz bastante o tamanho de logos grandes.
    for quality in (88, 80, 72, 64, 56):
        webp_buffer = io.BytesIO()
        converted.save(webp_buffer, format="WEBP", quality=quality, method=6)
        webp_bytes = webp_buffer.getvalue()
        if len(webp_bytes) <= MAX_LOGO_BYTES:
            return webp_bytes, "image/webp"

    # Última tentativa: reduz dimensões progressivamente.
    reduced = converted
    for factor in (0.85, 0.70, 0.55):
        width = max(120, int(converted.width * factor))
        height = max(60, int(converted.height * factor))
        reduced = converted.resize((width, height), Image.Resampling.LANCZOS)
        webp_buffer = io.BytesIO()
        reduced.save(webp_buffer, format="WEBP", quality=62, method=6)
        webp_bytes = webp_buffer.getvalue()
        if len(webp_bytes) <= MAX_LOGO_BYTES:
            return webp_bytes, "image/webp"

    return webp_bytes, "image/webp"


def decode_logo(branding: dict[str, Any], *, sidebar: bool = False) -> tuple[bytes | None, str | None]:
    normalized = normalize_branding(branding)
    prefix = "sidebar_logo" if sidebar else "logo"
    encoded = normalized.get(f"{prefix}_base64")
    mime = normalized.get(f"{prefix}_mime")

    if sidebar and not encoded:
        encoded = normalized.get("logo_base64")
        mime = normalized.get("logo_mime")

    if not encoded:
        return None, None
    try:
        return base64.b64decode(encoded), str(mime or "image/png")
    except Exception:
        log.exception("Logomarca armazenada não pôde ser decodificada.")
        return None, None
