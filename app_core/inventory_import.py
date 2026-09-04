from __future__ import annotations

import io
import numbers
import re
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Any

import pandas as pd

SUPPORTED_TYPES = ["GPRS", "SATELITE", "CAMERA", "RADIO"]

COLUMN_ALIASES = {
    "modelo": "Modelo",
    "gateway": "Gateway",
    "equipamento": "NÂº Equipamento",
    "n equipamento": "NÂº Equipamento",
    "no equipamento": "NÂº Equipamento",
    "numero equipamento": "NÂº Equipamento",
    "p/ entrada": "P/ Entrada",
    "p entrada": "P/ Entrada",
    "para entrada": "P/ Entrada",
    "status": "Status",
    "tipo equipamento": "Tipo Equipamento Origem",
    "tipo de equipamento": "Tipo Equipamento Origem",
    "situacao": "SituaÃ§Ã£o",
    "tipo": "Tipo",
    "n serie": "NÂº SÃ©rie",
    "no serie": "NÂº SÃ©rie",
    "numero serie": "NÂº SÃ©rie",
}

NULL_TEXT_VALUES = {"", "nan", "none", "nat", "<na>"}
SCIENTIFIC_RE = re.compile(
    r"^[+-]?(?:\d+(?:[.,]\d*)?|[.,]\d+)[eE][+-]?\d+$"
)
PLAIN_INTEGER_FLOAT_RE = re.compile(r"^([+-]?\d+)\.0+$")
MAX_SAFE_FLOAT_INTEGER = 2**53


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
    text = text.replace("Âº", "o").replace("Âª", "a")
    return strip_accents(text).lower()


def _decimal_identifier(value: Decimal) -> str:
    if not value.is_finite():
        return ""
    integral = value.to_integral_value()
    if value != integral:
        text = format(value.normalize(), "f")
        return text.rstrip("0").rstrip(".") if "." in text else text
    return format(integral, "f")


def _scientific_text_info(text: str) -> tuple[str, bool]:
    normalized_text = text.strip().replace(" ", "").replace(",", ".")
    if not SCIENTIFIC_RE.fullmatch(normalized_text):
        return "", False

    try:
        decimal_value = Decimal(normalized_text)
    except InvalidOperation:
        return "", False

    normalized = _decimal_identifier(decimal_value)
    if not normalized:
        return "", False

    mantissa = normalized_text.lower().split("e", 1)[0].lstrip("+-")
    significant = mantissa.replace(".", "").lstrip("0")
    significant_digits = len(significant)

    integer_digits = len(normalized.lstrip("+-").lstrip("0"))
    if normalized in {"0", "-0"}:
        integer_digits = 1

    # Para identificadores, zeros finais tambÃ©m sÃ£o significativos.
    # Se a notaÃ§Ã£o cientÃ­fica traz menos algarismos significativos do que o
    # inteiro resultante, nÃ£o hÃ¡ como reconstruir com seguranÃ§a os dÃ­gitos
    # perdidos pela exportaÃ§Ã£o (ex.: 8,62193E+14).
    lossy = significant_digits < integer_digits
    return normalized, lossy


def normalize_identifier(value: Any) -> tuple[str, bool, bool]:
    """
    Retorna (identificador_normalizado, veio_de_notacao_cientifica, perdeu_precisao).

    NÃºmeros inteiros vindos diretamente de Excel sÃ£o seguros enquanto estiverem
    dentro do limite de inteiros exatos do IEEE-754 (2**53). Texto em notaÃ§Ã£o
    cientÃ­fica Ã© tratado de forma conservadora para evitar criar IMEIs incorretos.
    """
    if value is None:
        return "", False, False

    try:
        if pd.isna(value):
            return "", False, False
    except Exception:
        pass

    if isinstance(value, bool):
        return str(value), False, False

    if isinstance(value, numbers.Integral):
        return str(int(value)), False, False

    if isinstance(value, numbers.Real):
        numeric = float(value)
        if not pd.notna(numeric):
            return "", False, False
        if numeric.is_integer():
            integer = int(numeric)
            lossy = abs(integer) > MAX_SAFE_FLOAT_INTEGER
            return str(integer), False, lossy
        text = format(numeric, ".15g")
        return text, False, True

    text = str(value).strip()
    if text.lower() in NULL_TEXT_VALUES:
        return "", False, False

    scientific_normalized, scientific_lossy = _scientific_text_info(text)
    if scientific_normalized:
        return scientific_normalized, True, scientific_lossy

    match = PLAIN_INTEGER_FLOAT_RE.fullmatch(text)
    if match:
        return match.group(1), False, False

    return text, False, False


def normalize_equipment(value: Any) -> str:
    return normalize_identifier(value)[0]


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
        raise ValueError(f"NÃ£o foi possÃ­vel ler o CSV: {last_error}")

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


def _resolve_inventory_identifier(
    equipment_value: Any,
    serial_value: Any,
) -> tuple[str, bool, bool, str]:
    equipment, equipment_scientific, equipment_lossy = normalize_identifier(
        equipment_value
    )
    serial, serial_scientific, serial_lossy = normalize_identifier(serial_value)

    if equipment and not equipment_lossy:
        return equipment, equipment_scientific, False, "NÂº Equipamento"

    if serial and not serial_lossy:
        return serial, serial_scientific, False, "NÂº SÃ©rie"

    if equipment:
        return equipment, equipment_scientific, equipment_lossy, "NÂº Equipamento"

    if serial:
        return serial, serial_scientific, serial_lossy, "NÂº SÃ©rie"

    return "", False, False, ""


def parse_inventory_report(
    file_bytes: bytes,
    file_name: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    raw = _read_raw(file_bytes, file_name)
    header_row = find_header_row(raw)

    if header_row is None:
        raise ValueError(
            "NÃ£o foi possÃ­vel encontrar o cabeÃ§alho do estoque. "
            "O arquivo deve conter pelo menos as colunas Modelo e Equipamento."
        )

    frame = raw.iloc[header_row + 1 :].copy()
    frame.columns = [
        "" if pd.isna(value) else str(value).strip()
        for value in raw.iloc[header_row].tolist()
    ]
    frame = normalize_columns(frame)

    required = ["NÂº Equipamento", "Modelo"]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(
            "Colunas obrigatÃ³rias ausentes: " + ", ".join(missing)
        )

    serial_column = (
        frame["NÂº SÃ©rie"]
        if "NÂº SÃ©rie" in frame.columns
        else pd.Series([""] * len(frame), index=frame.index, dtype=object)
    )

    original_equipment_values = [
        "" if pd.isna(value) else str(value).strip()
        for value in frame["NÂº Equipamento"].tolist()
    ]

    resolved = [
        _resolve_inventory_identifier(equipment, serial)
        for equipment, serial in zip(
            frame["NÂº Equipamento"].tolist(),
            serial_column.tolist(),
        )
    ]

    frame["_ID_Original"] = original_equipment_values
    frame["_ID_Resolvido"] = [item[0] for item in resolved]
    frame["_ID_Cientifico"] = [bool(item[1]) for item in resolved]
    frame["_ID_Impreciso"] = [bool(item[2]) for item in resolved]
    frame["_ID_Origem"] = [item[3] for item in resolved]

    frame["NÂº Equipamento"] = frame["_ID_Resolvido"]
    frame["Modelo"] = frame["Modelo"].fillna("").astype(str).str.strip()

    if "NÂº SÃ©rie" in frame.columns:
        frame["NÂº SÃ©rie"] = frame["NÂº SÃ©rie"].apply(normalize_equipment)

    frame = frame[
        (frame["NÂº Equipamento"] != "")
        & (frame["Modelo"] != "")
        & (frame["Modelo"].str.lower() != "modelo")
    ].copy()

    if frame.empty:
        raise ValueError("Nenhum rastreador vÃ¡lido foi encontrado na planilha.")

    lossy_rows = frame[frame["_ID_Impreciso"]].copy()
    if not lossy_rows.empty:
        examples = (
            lossy_rows[["Modelo", "_ID_Original"]]
            .head(5)
            .astype(str)
            .apply(lambda row: f"{row['Modelo']}: {row['_ID_Original']}", axis=1)
            .tolist()
        )
        examples_text = "; ".join(examples)

        raise ValueError(
            f"Foram encontrados {len(lossy_rows)} equipamento(s) com identificador "
            "abreviado/sem precisÃ£o suficiente, normalmente causado por exportaÃ§Ã£o "
            "em notaÃ§Ã£o cientÃ­fica (ex.: 8,62193E+14). Esses dÃ­gitos jÃ¡ foram "
            "perdidos no arquivo e nÃ£o podem ser reconstruÃ­dos com seguranÃ§a. "
            "Use o XLS/XLSX original do sistema, sem converter os IMEIs para "
            "notaÃ§Ã£o cientÃ­fica, ou exporte essas colunas como texto. "
            f"Exemplos detectados: {examples_text}"
        )

    preferred = [
        "NÂº Equipamento",
        "NÂº SÃ©rie",
        "Modelo",
        "Gateway",
        "P/ Entrada",
        "Status",
        "Tipo Equipamento Origem",
        "SituaÃ§Ã£o",
        "Tipo",
    ]
    columns = [
        column
        for column in preferred
        if column in frame.columns
    ]
    frame = frame[columns].copy()

    for column in frame.columns:
        if column in {"NÂº Equipamento", "NÂº SÃ©rie"}:
            continue
        frame[column] = frame[column].apply(
            lambda value: ""
            if pd.isna(value)
            else str(value).strip()
        )

    before_dedup = len(frame)
    duplicate_mask = frame.duplicated(
        subset=["NÂº Equipamento"],
        keep=False,
    )
    duplicate_identifiers = sorted(
        frame.loc[duplicate_mask, "NÂº Equipamento"].astype(str).unique().tolist()
    )

    frame = frame.drop_duplicates(
        subset=["NÂº Equipamento"],
        keep="last",
    ).reset_index(drop=True)

    metadata = {
        "file_name": str(file_name or ""),
        "header_row": int(header_row + 1),
        "rows_read": int(before_dedup),
        "rows_valid": int(len(frame)),
        "duplicates_removed": int(before_dedup - len(frame)),
        "duplicate_identifiers": duplicate_identifiers,
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
            origin = "SugestÃ£o por modelo"
        else:
            origin = "Revisar"

        rows.append(
            {
                "Modelo": model,
                "Qtd Equipamentos": int(len(model_rows)),
                "Tipo origem": source_label,
                "Tipo": suggested,
                "Origem da sugestÃ£o": origin,
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