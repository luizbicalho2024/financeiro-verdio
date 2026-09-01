from __future__ import annotations

import io
from typing import Literal

import pandas as pd

OLE_SIGNATURE = b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1"
ZIP_SIGNATURES = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")


def detect_spreadsheet_kind(file_bytes: bytes, file_name: str = "") -> Literal["csv", "xls", "xlsx"]:
    """Detecta o formato real priorizando a assinatura binária sobre a extensão."""
    lower_name = (file_name or "").strip().lower()
    prefix = bytes(file_bytes[:8] or b"")

    if lower_name.endswith(".csv"):
        return "csv"
    if prefix.startswith(OLE_SIGNATURE):
        return "xls"
    if any(prefix.startswith(signature) for signature in ZIP_SIGNATURES):
        return "xlsx"
    if lower_name.endswith(".xls"):
        return "xls"
    return "xlsx"


def _read_csv(file_bytes: bytes) -> pd.DataFrame:
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "utf-8", "latin1"):
        try:
            return pd.read_csv(
                io.BytesIO(file_bytes),
                header=None,
                sep=None,
                engine="python",
                encoding=encoding,
                on_bad_lines="skip",
            )
        except Exception as exc:
            last_error = exc

    try:
        return pd.read_csv(
            io.BytesIO(file_bytes),
            header=None,
            encoding="latin1",
            on_bad_lines="skip",
        )
    except Exception as exc:
        raise ValueError(f"Não foi possível ler o arquivo CSV: {exc}") from (last_error or exc)


def _read_legacy_xls(file_bytes: bytes) -> pd.DataFrame:
    """
    Lê XLS/BIFF em modo tolerante.

    Alguns ERPs geram OLE Compound Documents estruturalmente inconsistentes
    que o Excel abre normalmente, mas o xlrd rejeita por padrão com
    ``Workbook corruption: seen[...] == ...``. O xlrd 2.x oferece
    ``ignore_workbook_corruption=True`` especificamente para esse caso.
    """
    try:
        return pd.read_excel(
            io.BytesIO(file_bytes),
            header=None,
            engine="xlrd",
            engine_kwargs={"ignore_workbook_corruption": True},
        )
    except TypeError:
        try:
            import xlrd

            book = xlrd.open_workbook(
                file_contents=file_bytes,
                ignore_workbook_corruption=True,
                on_demand=True,
            )
            if book.nsheets < 1:
                raise ValueError("O arquivo XLS não possui planilhas.")

            sheet = book.sheet_by_index(0)
            rows = [sheet.row_values(index) for index in range(sheet.nrows)]
            return pd.DataFrame(rows)
        except Exception as exc:
            raise ValueError(
                "Falha ao ler XLS legado em modo tolerante: "
                f"{type(exc).__name__}: {exc}"
            ) from exc
    except Exception as exc:
        raise ValueError(
            "Falha ao ler XLS legado em modo tolerante: "
            f"{type(exc).__name__}: {exc}"
        ) from exc


def read_raw_spreadsheet(file_bytes: bytes, file_name: str = "") -> pd.DataFrame:
    """Lê CSV/XLS/XLSX para DataFrame bruto com header=None."""
    if not file_bytes:
        raise ValueError("O arquivo enviado está vazio.")

    kind = detect_spreadsheet_kind(file_bytes, file_name)

    if kind == "csv":
        return _read_csv(file_bytes)
    if kind == "xls":
        return _read_legacy_xls(file_bytes)

    try:
        return pd.read_excel(
            io.BytesIO(file_bytes),
            header=None,
            engine="openpyxl",
        )
    except Exception as exc:
        raise ValueError(
            "Falha ao ler planilha XLSX: "
            f"{type(exc).__name__}: {exc}"
        ) from exc
