"""ClearTrace — Multi-Format Document Ingestion Engine.

Supports CSV, Excel (XLSX), and text-based PDF table parsing with:
- Strict resource bounds (10 MB size, 100k rows, 15 PDF pages, 30MB uncompressed XLSX).
- Macro rejection (.xlsm / vbaproject.bin).
- No arbitrary spreadsheet formula execution.
- Source provenance tracking (CSV row, Excel sheet+cell/row, PDF page+table+row).
- Fallback encoding detection (UTF-8-SIG, UTF-8, Latin-1, CP1252).
"""

from __future__ import annotations

import csv
import io
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import zipfile
import pandas as pd


MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_UNCOMPRESSED_XLSX_BYTES = 30 * 1024 * 1024  # 30 MB
MAX_ROW_COUNT = 100_000
MAX_COL_COUNT = 200
MAX_PDF_PAGES = 15


class IngestionError(Exception):
    """Raised when document validation or parsing fails."""
    pass


def load_demo_dataset() -> pd.DataFrame:
    """Returns the official ClearTrace demonstration dataset containing known issue classes."""
    return pd.DataFrame(
        [
            {"id": "1", "name": "Anita", "city": " Bengaluru ", "email": "anita@example.test", "joined_date": "2026-01-10", "salary": "52000", "notes": "baseline"},
            {"id": "2", "name": "Vikram", "city": "bengaluru", "email": None, "joined_date": "2026-02-30", "salary": "54000", "notes": "bad date"},
            {"id": "3", "name": "Meera", "city": "Mysuru", "email": "meera@example.test", "joined_date": "2026-03-01", "salary": "unknown", "notes": "bad number"},
            {"id": "4", "name": "Hari", "city": "BENGALURU", "email": "hari@example.test", "joined_date": "2026-04-22", "salary": "51000", "notes": "case variant"},
            {"id": "5", "name": "Leena", "city": "Mysuru", "email": "leena@example.test", "joined_date": "2026-05-20", "salary": "9999999", "notes": "potential outlier"},
            {"id": "6", "name": "Zoya", "city": "Chennai", "email": "zoya@example.test", "joined_date": "2026-06-21", "salary": "55000", "notes": "=2+3"},
            {"id": "6", "name": "Zoya", "city": "Chennai", "email": "zoya@example.test", "joined_date": "2026-06-21", "salary": "55000", "notes": "=2+3"},
        ]
    )


def load_math_demo_dataset(fmt: str = "csv") -> Tuple[pd.DataFrame, dict]:
    """Loads the synthetic invoice math verification dataset in CSV, XLSX, or PDF format."""
    ext = fmt.lower().lstrip(".")
    sample_path = Path(__file__).resolve().parent.parent / "samples" / f"math_errors.{ext}"
    if not sample_path.exists():
        raise IngestionError(f"Math sample file not found: {sample_path.name}")
    return parse_document_bytes(sample_path.read_bytes(), filename=sample_path.name)


def parse_csv_bytes(raw_bytes: bytes, filename: str = "dataset.csv") -> Tuple[pd.DataFrame, dict]:
    """Safely validate and parse uploaded CSV bytes into a clean DataFrame."""
    if not raw_bytes:
        raise IngestionError("The uploaded file is empty (0 bytes).")

    if len(raw_bytes) > MAX_FILE_SIZE_BYTES:
        raise IngestionError(
            f"File size ({len(raw_bytes) / 1024 / 1024:.1f} MB) exceeds maximum allowed limit of {MAX_FILE_SIZE_BYTES / 1024 / 1024:.0f} MB."
        )

    # Decode with fallback
    text: str = ""
    for encoding in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        try:
            text = raw_bytes.decode(encoding)
            break
        except UnicodeDecodeError:
            continue

    if not text:
        raise IngestionError("Could not decode file using UTF-8 or common character encodings.")

    # Detect delimiter
    try:
        sample = text[:4096]
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        sep = dialect.delimiter
    except Exception:
        sep = ","

    # Parse with pandas
    try:
        df = pd.read_csv(io.StringIO(text), sep=sep, dtype=str, keep_default_na=True)
    except Exception as exc:
        raise IngestionError(f"CSV parsing error: {exc}")

    if df.empty:
        raise IngestionError("The CSV contains headers but no data rows.")

    if len(df) > MAX_ROW_COUNT:
        raise IngestionError(f"Row count ({len(df):,}) exceeds maximum session bound of {MAX_ROW_COUNT:,} rows.")

    if len(df.columns) > MAX_COL_COUNT:
        raise IngestionError(f"Column count ({len(df.columns)}) exceeds maximum bound of {MAX_COL_COUNT} columns.")

    # Build provenance mapping
    provenance_map: Dict[int, str] = {}
    for idx in range(len(df)):
        provenance_map[idx] = f"{filename}:row {idx + 2}"

    metadata = {
        "filename": filename,
        "format": "csv",
        "size_bytes": len(raw_bytes),
        "total_rows": len(df),
        "total_columns": len(df.columns),
        "columns": list(df.columns),
        "digest_sha256": sha256(raw_bytes).hexdigest(),
        "warnings": [],
        "provenance_map": provenance_map,
    }

    return df, metadata


def parse_xlsx_bytes(raw_bytes: bytes, filename: str = "dataset.xlsx") -> Tuple[pd.DataFrame, dict]:
    """Safely parse uploaded Excel XLSX bytes with sheet and cell provenance tracking.
    
    Rejects macros (.xlsm/VBA), enforces ZIP decompression bounds, and treats formulas
    as untrusted text without arbitrary execution.
    """
    if not raw_bytes:
        raise IngestionError("The uploaded file is empty (0 bytes).")

    if len(raw_bytes) > MAX_FILE_SIZE_BYTES:
        raise IngestionError(f"File size exceeds maximum allowable limit of 10 MB.")

    if not raw_bytes.startswith(b"PK"):
        raise IngestionError("The file does not appear to be a valid OOXML (.xlsx) archive.")

    # Inspect zip contents for bomb / macro protection
    try:
        with zipfile.ZipFile(io.BytesIO(raw_bytes)) as z:
            entries = z.infolist()
            if len(entries) > 3000:
                raise IngestionError("Excel archive contains too many internal entries (>3,000).")
            total_uncompressed = sum(e.file_size for e in entries)
            if total_uncompressed > MAX_UNCOMPRESSED_XLSX_BYTES:
                raise IngestionError(f"Excel uncompressed size ({total_uncompressed / 1024 / 1024:.1f} MB) exceeds limit.")
            if any("vbaproject.bin" in e.filename.lower() for e in entries):
                raise IngestionError("Macro-containing Excel workbooks (.xlsm / VBA) are strictly rejected for security.")
    except zipfile.BadZipFile as exc:
        raise IngestionError("Malformed or corrupted XLSX workbook.") from exc

    import openpyxl
    warnings: List[str] = []
    wb = openpyxl.load_workbook(io.BytesIO(raw_bytes), data_only=False, read_only=True, keep_links=False)
    try:
        if len(wb.sheetnames) > 30:
            raise IngestionError("Workbook contains more than 30 sheets; rejected to prevent resource exhaustion.")

        target_ws = None
        for ws in wb.worksheets:
            if ws.max_row is not None and ws.max_row >= 2:
                target_ws = ws
                break
        if target_ws is None:
            target_ws = wb.active

        sheet_title = target_ws.title
        rows_iter = target_ws.iter_rows(values_only=False)
        try:
            header_cells = next(rows_iter)
        except StopIteration:
            raise IngestionError(f"Sheet '{sheet_title}' is completely empty.")

        headers = [str(c.value).strip() if c.value is not None else f"col_{i}" for i, c in enumerate(header_cells)]
        # Filter empty trailing headers
        while headers and not headers[-1]:
            headers.pop()

        data_rows: List[List[Any]] = []
        provenance_map: Dict[int, str] = {}

        for row_idx, cell_row in enumerate(rows_iter, start=2):
            if len(data_rows) >= MAX_ROW_COUNT:
                warnings.append(f"Row limit of {MAX_ROW_COUNT:,} reached. Additional rows truncated.")
                break

            vals = [cell.value for cell in cell_row[:len(headers)]]
            if all(v is None for v in vals):
                continue

            for cell in cell_row[:len(headers)]:
                if getattr(cell, "data_type", None) == "f":
                    warnings.append(f"{sheet_title}!row {row_idx}: formula cell detected; raw formula text preserved without evaluation.")
                    break

            # Convert values to strings while preserving empty as None
            row_str = [str(v) if v is not None else None for v in vals]
            # Pad if short
            while len(row_str) < len(headers):
                row_str.append(None)

            curr_idx = len(data_rows)
            data_rows.append(row_str)
            provenance_map[curr_idx] = f"{filename}:{sheet_title}!row {row_idx}"

    finally:
        wb.close()

    if not data_rows:
        raise IngestionError(f"Sheet '{sheet_title}' contains headers but zero data records.")

    df = pd.DataFrame(data_rows, columns=headers)
    metadata = {
        "filename": filename,
        "format": "xlsx",
        "sheet_selected": sheet_title,
        "size_bytes": len(raw_bytes),
        "total_rows": len(df),
        "total_columns": len(df.columns),
        "columns": list(df.columns),
        "digest_sha256": sha256(raw_bytes).hexdigest(),
        "warnings": list(dict.fromkeys(warnings)),
        "provenance_map": provenance_map,
    }

    return df, metadata


def parse_pdf_bytes(raw_bytes: bytes, filename: str = "dataset.pdf") -> Tuple[pd.DataFrame, dict]:
    """Safely extract tabular data from digital text-based PDF files with page/table/row provenance.
    
    Uses pdfplumber for table extraction. Accurately notes that scanned PDFs require OCR.
    """
    if not raw_bytes:
        raise IngestionError("The uploaded file is empty (0 bytes).")

    if len(raw_bytes) > MAX_FILE_SIZE_BYTES:
        raise IngestionError("PDF exceeds maximum allowed limit of 10 MB.")

    if not raw_bytes.startswith(b"%PDF-"):
        raise IngestionError("The uploaded file does not have a valid PDF header (%PDF-).")

    import pdfplumber
    warnings: List[str] = [
        "PDF table extraction is best-effort. User review of extracted cell values is recommended."
    ]
    extracted_rows: List[List[Any]] = []
    headers: List[str] = []
    provenance_map: Dict[int, str] = {}

    with pdfplumber.open(io.BytesIO(raw_bytes)) as pdf:
        if len(pdf.pages) > MAX_PDF_PAGES:
            raise IngestionError(f"PDF exceeds page limit ({len(pdf.pages)} > {MAX_PDF_PAGES}).")

        for page_num, page in enumerate(pdf.pages, start=1):
            tables = page.extract_tables()
            for table_num, table in enumerate(tables, start=1):
                if not table or len(table) < 2:
                    continue

                if not headers:
                    raw_h = table[0]
                    headers = [str(h).strip().replace("\n", " ") if h is not None else f"col_{i}" for i, h in enumerate(raw_h)]

                for row_num, row_cells in enumerate(table[1:], start=2):
                    if len(extracted_rows) >= MAX_ROW_COUNT:
                        break
                    if not row_cells or all(c is None or not str(c).strip() for c in row_cells):
                        continue

                    # Clean newlines in cells
                    cleaned_cells = [str(c).strip().replace("\n", " ") if c is not None and str(c).strip() else None for c in row_cells]
                    while len(cleaned_cells) < len(headers):
                        cleaned_cells.append(None)

                    curr_idx = len(extracted_rows)
                    extracted_rows.append(cleaned_cells[:len(headers)])
                    provenance_map[curr_idx] = f"{filename}:page {page_num} table {table_num} row {row_num}"

    if not extracted_rows or not headers:
        raise IngestionError(
            "No structured table could be extracted from this PDF. "
            "Please ensure the document contains tabular data. "
            "Scanned raster PDFs require an external OCR workflow."
        )

    df = pd.DataFrame(extracted_rows, columns=headers)
    metadata = {
        "filename": filename,
        "format": "pdf",
        "size_bytes": len(raw_bytes),
        "total_rows": len(df),
        "total_columns": len(df.columns),
        "columns": list(df.columns),
        "digest_sha256": sha256(raw_bytes).hexdigest(),
        "warnings": warnings,
        "provenance_map": provenance_map,
    }

    return df, metadata


def parse_document_bytes(raw_bytes: bytes, filename: str) -> Tuple[pd.DataFrame, dict]:
    """Unified entry point for CSV, TSV, XLSX, and text-based PDF document ingestion."""
    ext = Path(filename).suffix.lower()
    if ext in (".csv", ".tsv"):
        return parse_csv_bytes(raw_bytes, filename=filename)
    elif ext in (".xlsx", ".xlsm"):
        return parse_xlsx_bytes(raw_bytes, filename=filename)
    elif ext == ".pdf":
        return parse_pdf_bytes(raw_bytes, filename=filename)
    elif ext == ".xls":
        raise IngestionError(
            "Legacy Excel 97-2003 format (.xls) is not supported due to security and binary parser deprecation. "
            "Please convert and save your spreadsheet as modern Excel (.xlsx) or CSV (.csv)."
        )
    else:
        raise IngestionError(f"Unsupported file format '{ext}'. ClearTrace supports .csv, .tsv, .xlsx, and .pdf.")
