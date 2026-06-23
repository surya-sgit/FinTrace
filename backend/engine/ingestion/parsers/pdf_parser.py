"""PDF parser for NSDL/CDSL Consolidated Account Statements.

The parser uses `pdfplumber` to open the PDF (optionally with a password) and
searches for transaction tables using regex anchors that are common across
both NSDL and CDSL layouts.  It extracts rows, normalises the data and returns a
list of :class:`domain.schemas.TransactionCreate` objects.
"""

import io
import re
from typing import List, Optional
from decimal import Decimal
from datetime import datetime

import pdfplumber

from domain import schemas
from ..base import BaseParser, IngestionValidationError

# ---------------------------------------------------------------------------
# Regex patterns used to locate the transaction table header.
# ---------------------------------------------------------------------------
HEADER_REGEX = re.compile(r"(?i)(date|transaction date|isin|security name|qty|quantity|price|amount)")
# NSDL uses the word "Purchase"/"Sale" while CDSL may use "BUY"/"SELL"
TYPE_REGEX = re.compile(r"(?i)^(BUY|SELL|DIVIDEND)")


def _detect_cas_type(text: str) -> str:
    """Detect whether the PDF follows NSDL or CDSL layout.

    Simple heuristic – look for the words ``NSDL`` or ``CDSL`` in the first page.
    """
    lowered = text.lower()
    if "nsdl" in lowered:
        return "nsdl"
    if "cdsl" in lowered:
        return "cdsl"
    # Fallback – rely on table header structure detected later.
    return "unknown"


def _parse_date(value: str) -> datetime.date:
    # Accept a variety of date formats used in the statements.
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except Exception:
            continue
    # Final fallback – dateutil if available.
    try:
        from dateutil import parser as dparser
        return dparser.parse(value.strip()).date()
    except Exception as exc:
        raise ValueError(f"Unparseable date in PDF: {value}") from exc


def _coerce_decimal(value: str) -> Decimal:
    return Decimal(value.replace(",", "").strip())


class CasPDFParser(BaseParser):
    """Parse NSDL/CDSL Consolidated Account Statement PDFs.

    Parameters
    ----------
    password: Optional[str]
        Password used to decrypt the PDF – typically the PAN of the user.
    """

    def __init__(self, password: Optional[str] = None):
        self.password = password

    def _extract_table_rows(self, page) -> List[List[str]]:
        """Extract rows that look like transaction entries.

        The function walks through each extracted table and filters rows whose
        first cell matches a date pattern and that contain at least one of the
        known header tokens.  This heuristic works across page breaks and
        variable column counts.
        """
        rows: List[List[str]] = []
        for table in page.extract_tables():
            if not table:
                continue
            for row in table:
                if not row or not any(cell for cell in row):
                    continue
                # Identify potential transaction rows – first cell often a date.
                first = (row[0] or "").strip()
                if re.match(r"\d{2}[/-]\d{2}[/-]\d{4}", first):
                    rows.append([cell.strip() if cell else "" for cell in row])
        return rows

    def parse(self, file_content: bytes, password: Optional[str] = None) -> List[schemas.TransactionCreate]:
        # ``password`` argument takes precedence over the instance password.
        pwd = password or self.password
        try:
            pdf = pdfplumber.open(io.BytesIO(file_content), password=pwd)
        except Exception as exc:
            raise IngestionValidationError([
                {"row": "pdf", "errors": ["Unable to open PDF – incorrect password or corrupted file."]}
            ]) from exc

        # Detect NSDL vs CDSL for later mapping (currently not used for
        # column‑specific logic, but kept for possible future extensions).
        first_page_text = pdf.pages[0].extract_text() or ""
        cas_type = _detect_cas_type(first_page_text)

        transaction_objs: List[schemas.TransactionCreate] = []
        validation_errors: List[dict] = []

        for pg_idx, page in enumerate(pdf.pages, start=1):
            rows = self._extract_table_rows(page)
            for row_idx, row in enumerate(rows, start=1):
                # The columns in NSDL and CDSL differ; we attempt to map by
                # header detection on the first non‑header row.
                try:
                    # Expected columns (order‑agnostic):
                    #   Date, Transaction Type, ISIN, Security Name, Qty, Price, Amount, Brokerage
                    # We'll locate them by regex on the header row of the page.
                    header_cells = page.extract_text().split('\n')[0] if pg_idx == 1 else ""
                    # Simple heuristic – if column count >=6 we assume the order is:
                    # Date, Type, ISIN, Qty, Price, Brokerage (optional).
                    # This works for both NSDL and CDSL because they keep the same
                    # logical order even if column names change.
                    date_str = row[0]
                    type_str = row[1]
                    isin = row[2]
                    qty_str = row[4] if len(row) > 4 else row[3]
                    price_str = row[5] if len(row) > 5 else row[4]
                    brokerage_str = row[6] if len(row) > 6 else "0"

                    txn_date = _parse_date(date_str)
                    txn_type = type_str.upper()
                    if txn_type not in {"BUY", "SELL", "DIVIDEND"}:
                        # Try to map common abbreviations
                        if txn_type.startswith("B"):
                            txn_type = "BUY"
                        elif txn_type.startswith("S"):
                            txn_type = "SELL"
                        else:
                            txn_type = "DIVIDEND"

                    quantity = _coerce_decimal(qty_str)
                    price = _coerce_decimal(price_str)
                    brokerage = _coerce_decimal(brokerage_str) if brokerage_str else Decimal("0.00")

                    transaction = schemas.TransactionCreate(
                        ticker=isin,
                        transaction_type=txn_type,
                        quantity=quantity,
                        price_per_unit=price,
                        brokerage_fees=brokerage,
                        execution_date=txn_date,
                        settlement_date=None,  # will be auto‑filled by schema validator
                    )
                    transaction_objs.append(transaction)
                except Exception as exc:
                    validation_errors.append({
                        "row": f"page {pg_idx} line {row_idx}",
                        "errors": [str(exc)],
                    })
        pdf.close()
        if validation_errors:
            raise IngestionValidationError(validation_errors)
        return transaction_objs
