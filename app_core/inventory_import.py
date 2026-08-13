from __future__ import annotations

import io
import re
import unicodedata
from typing import Any

import pandas as pd

SUPPORTED_TYPES = ["GPRS", "SATELITE", "CAMERA", "RADIO"]

COLUMN_ALIASES = {
    "modelo": "Modelo",
    "gateway": "Gateway",
    "equipamento": "Nº Equipamento",
    "n equipamento": "Nº Equipamento",
    "no equipamento": "Nº Equipamento",
    "nº equipamento": "Nº Equipamento",
    "numero equipamento": "Nº Equipamento",
    "número equipamento": "Nº Equipamento",
    "n serie": "Nº Equipamento",
    "nº serie": "Nº Equipamento",
    "numero serie": "Nº Equipamento",
    "número série": "Nº Equipamento",
    "p/ entrada": "P/ Entrada",
    "p entrada": "P/ Entrada",
    "para entrada": "P/ Entrada",
    "status": "Status",
    "tipo equipamento": "Tipo Equipamento Origem",
    "tipo de equipamento": "Tipo Equipamento Origem",
    "situacao": "Situação",
    "situação": "Situação",
    "tipo": "Tipo",
}


def strip_accents(value: Any) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFKD", str(value or ""))
        if not unicodedata.combining(char)
    )


def canonical_key(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass

    text = str(value).strip().replace("\n", " ").replace("\r", " ")
    text = re.sub(r"\s+", " ", text)
    text = text.replace("º", "o").replace("ª", "a")
    return strip_accents(text).lower()


def normalize_equipment(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass

    if isinstance(value, bool):
        return str(value)

    if isinstance(value, int):
        return str(value)

    if isinstance(value, float) and value.is_integer():
        return str(int(value))

    text = str(value).strip()
    text = re.sub(r"\.0$", "", text)
    return "" if text.lower() in {"nan", "none", "nat"} else text


def _read_raw(file_bytes: bytes, file_name: str) -> pd.DataFrame:
    lower_name = str(file_name or "").lower()

    if lower_name.endswith(".csv"):
        last_error = None
        for encoding in ("utf-8-sig", "utf-8", "latin1"):
            try:
                return pd.read_csv(
                    io.BytesIO(file_bytes),
                    header=None,
                    sep=None,
                    engine="python",
                    encoding=encoding,
                    dtype=object,
                    on_bad_lines="skip",
                )
            except Exception as exc:
                last_error = exc
        raise ValueError(f"Não foi possível ler o CSV: {last_error}")

    if lower_name.endswith(".xls"):
        return pd.read_excel(
            io.BytesIO(file_bytes),
            header=None,
            engine="xlrd",
            dtype=object,
        )

    return pd.read_excel(
        io.BytesIO(file_bytes),
        header=None,
        engine="openpyxl",
        dtype=object,
    )


def find_header_row(raw: pd.DataFrame) -> int | None:
    max_scan = min(80, len(raw))

    for idx in range(max_scan):
        values = [canonical_key(value) for value in raw.iloc[idx].tolist()]
        has_model = "modelo" in values
        has_equipment = any(
            value in {
                "equipamento",
                "n equipamento",
                "no equipamento",
                "numero equipamento",
                "n serie",
                "numero serie",
            }
            for value in values
        )
        if has_model and has_equipment:
            return idx

    return None


def normalize_columns(frame: pd.DataFrame) -> pd.DataFrame:
    rename: dict[Any, str] = {}
    seen: set[str] = set()

    for original in frame.columns:
        raw = str(original or "").strip()
        canonical = COLUMN_ALIASES.get(canonical_key(raw), raw)

        if not canonical or canonical.lower().startswith("unnamed"):
            canonical = f"Coluna_{len(seen) + 1}"

        base = canonical
        suffix = 2
        while canonical in seen:
            canonical = f"{base}_{suffix}"
            suffix += 1

        rename[original] = canonical
        seen.add(canonical)

    return frame.rename(columns=rename)


def parse_inventory_report(
    file_bytes: bytes,
    file_name: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    raw = _read_raw(file_bytes, file_name)
    header_row = find_header_row(raw)

    if header_row is None:
        raise ValueError(
            "Não foi possível encontrar o cabeçalho do estoque. "
            "O arquivo deve conter pelo menos as colunas Modelo e Equipamento."
        )

    frame = raw.iloc[header_row + 1 :].copy()
    frame.columns = [
        "" if pd.isna(value) else str(value).strip()
        for value in raw.iloc[header_row].tolist()
    ]
    frame = normalize_columns(frame)

    required = ["Nº Equipamento", "Modelo"]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(
            "Colunas obrigatórias ausentes: " + ", ".join(missing)
        )

    frame["Nº Equipamento"] = frame["Nº Equipamento"].apply(normalize_equipment)
    frame["Modelo"] = frame["Modelo"].fillna("").astype(str).str.strip()

    frame = frame[
        (frame["Nº Equipamento"] != "")
        & (frame["Modelo"] != "")
        & (frame["Modelo"].str.lower() != "modelo")
    ].copy()

    if frame.empty:
        raise ValueError("Nenhum rastreador válido foi encontrado na planilha.")

    preferred = [
        "Nº Equipamento",
        "Modelo",
        "Gateway",
        "P/ Entrada",
        "Status",
        "Tipo Equipamento Origem",
        "Situação",
        "Tipo",
    ]
    columns = [
        column
        for column in preferred
        if column in frame.columns
    ]
    frame = frame[columns].copy()

    for column in frame.columns:
        if column == "Nº Equipamento":
            continue
        frame[column] = frame[column].apply(
            lambda value: ""
            if pd.isna(value)
            else str(value).strip()
        )

    before_dedup = len(frame)
    frame = frame.drop_duplicates(
        subset=["Nº Equipamento"],
        keep="last",
    ).reset_index(drop=True)

    metadata = {
        "file_name": str(file_name or ""),
        "header_row": int(header_row + 1),
        "rows_read": int(before_dedup),
        "rows_valid": int(len(frame)),
        "duplicates_removed": int(before_dedup - len(frame)),
        "columns": list(frame.columns),
    }
    return frame, metadata


def normalize_system_type(value: Any) -> str:
    text = canonical_key(value).upper()
    if text in {"GPRS", "GSM", "CELULAR"}:
        return "GPRS"
    if text in {"SATELITE", "SATELITAL", "SATELLITE"}:
        return "SATELITE"
    if text in {"CAMERA", "CAMERAS"}:
        return "CAMERA"
    if text in {"RADIO"}:
        return "RADIO"
    return ""


def infer_type_from_model(model: Any) -> str:
    text = strip_accents(str(model or "")).upper().strip()

    if not text:
        return ""

    if any(token in text for token in ("CAMERA", "DVR", "MDVR")):
        return "CAMERA"

    if "RADIO" in text:
        return "RADIO"

    if any(token in text for token in ("SMARTONE", "GLOBALSTAR")):
        return "SATELITE"

    if (
        text.startswith("ST-")
        or text.startswith("ST ")
        or any(
            token in text
            for token in (
                "SUNTECH",
                "RST",
                "FMB",
                "GALILEO",
            )
        )
    ):
        return "GPRS"

    return ""


def build_model_type_mapping(
    frame: pd.DataFrame,
    existing_model_types: dict[str, str] | None = None,
) -> pd.DataFrame:
    existing = {
        str(model or "").strip(): normalize_system_type(type_value)
        for model, type_value in (existing_model_types or {}).items()
    }

    rows: list[dict[str, Any]] = []

    for model in sorted(frame["Modelo"].dropna().astype(str).str.strip().unique()):
        model_rows = frame[frame["Modelo"] == model]

        source_type = ""
        if "Tipo" in model_rows.columns:
            source_values = [
                normalize_system_type(value)
                for value in model_rows["Tipo"].tolist()
            ]
            source_type = next(
                (value for value in source_values if value),
                "",
            )

        source_label = ""
        if "Tipo Equipamento Origem" in model_rows.columns:
            source_label = next(
                (
                    str(value).strip()
                    for value in model_rows["Tipo Equipamento Origem"].tolist()
                    if str(value or "").strip()
                ),
                "",
            )

        current_type = existing.get(model, "")
        inferred_type = infer_type_from_model(model)

        suggested = current_type or source_type or inferred_type

        if current_type:
            origin = "Banco atual"
        elif source_type:
            origin = "Planilha"
        elif inferred_type:
            origin = "Sugestão por modelo"
        else:
            origin = "Revisar"

        rows.append(
            {
                "Modelo": model,
                "Qtd Equipamentos": int(len(model_rows)),
                "Tipo origem": source_label,
                "Tipo": suggested,
                "Origem da sugestão": origin,
            }
        )

    return pd.DataFrame(rows)


def apply_model_type_mapping(
    frame: pd.DataFrame,
    mapping: pd.DataFrame,
) -> pd.DataFrame:
    result = frame.copy()

    model_to_type = {
        str(row["Modelo"]).strip(): normalize_system_type(row.get("Tipo"))
        for _, row in mapping.iterrows()
    }

    result["Tipo"] = result["Modelo"].map(model_to_type).fillna("")
    return result
