from __future__ import annotations

from copy import deepcopy
from typing import Any

DEFAULT_BRANDING: dict[str, Any] = {
    "system_name": "Financeiro Verdio",
    "system_subtitle": "Gestão financeira, faturamento e controles operacionais",
    "footer_text": "Financeiro Verdio",
    "primary_color": "#006494",
    "secondary_color": "#123B57",
    "accent_color": "#0EA5A4",
    "background_color": "#F4F7FB",
    "surface_color": "#FFFFFF",
    "text_color": "#172033",
    "muted_text_color": "#667085",
    "border_color": "#D6DEE8",
    "input_background_color": "#FFFFFF",
    "sidebar_background_color": "#102A43",
    "sidebar_text_color": "#F8FAFC",
    "sidebar_muted_color": "#C7D2E0",
    "logo_base64": None,
    "logo_mime": None,
    "logo_filename": None,
    "sidebar_logo_base64": None,
    "sidebar_logo_mime": None,
    "sidebar_logo_filename": None,
}

_HEX_FIELDS = {
    "primary_color",
    "secondary_color",
    "accent_color",
    "background_color",
    "surface_color",
    "text_color",
    "muted_text_color",
    "border_color",
    "input_background_color",
    "sidebar_background_color",
    "sidebar_text_color",
    "sidebar_muted_color",
}

_TEXT_FIELDS = {"system_name", "system_subtitle", "footer_text"}


def normalize_hex_color(value: Any, fallback: str) -> str:
    text = str(value or "").strip().upper()
    if len(text) == 7 and text.startswith("#"):
        try:
            int(text[1:], 16)
            return text
        except ValueError:
            pass
    return fallback.upper()


def normalize_branding(data: dict[str, Any] | None) -> dict[str, Any]:
    result = deepcopy(DEFAULT_BRANDING)
    provided = data or {}

    for key in _TEXT_FIELDS:
        if key in provided:
            value = str(provided.get(key) or "").strip()
            if value:
                result[key] = value[:180]

    for key in _HEX_FIELDS:
        result[key] = normalize_hex_color(provided.get(key), result[key])

    for key in (
        "logo_base64",
        "logo_mime",
        "logo_filename",
        "sidebar_logo_base64",
        "sidebar_logo_mime",
        "sidebar_logo_filename",
    ):
        value = provided.get(key)
        result[key] = value if value not in ("", None) else None

    return result


def _rgb(hex_color: str) -> tuple[int, int, int]:
    value = normalize_hex_color(hex_color, "#000000")[1:]
    return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))


def _relative_luminance(hex_color: str) -> float:
    channels = []
    for channel in _rgb(hex_color):
        value = channel / 255.0
        channels.append(value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast_ratio(first: str, second: str) -> float:
    first_lum = _relative_luminance(first)
    second_lum = _relative_luminance(second)
    lighter = max(first_lum, second_lum)
    darker = min(first_lum, second_lum)
    return (lighter + 0.05) / (darker + 0.05)


def readable_text_color(background: str) -> str:
    white_ratio = contrast_ratio(background, "#FFFFFF")
    black_ratio = contrast_ratio(background, "#111827")
    return "#FFFFFF" if white_ratio >= black_ratio else "#111827"


def branding_contrast_warnings(branding: dict[str, Any]) -> list[str]:
    normalized = normalize_branding(branding)
    warnings: list[str] = []

    checks = [
        ("Texto principal", normalized["text_color"], normalized["background_color"]),
        ("Texto em cartões", normalized["text_color"], normalized["surface_color"]),
        ("Texto da sidebar", normalized["sidebar_text_color"], normalized["sidebar_background_color"]),
    ]
    for label, foreground, background in checks:
        if contrast_ratio(foreground, background) < 4.5:
            warnings.append(f"{label}: contraste abaixo de 4,5:1.")
    return warnings
