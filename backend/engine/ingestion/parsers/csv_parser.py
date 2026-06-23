"""CSV parser for broker transaction statements.

Supports Zerodha, Groww, Upstox, and AngelOne using a heuristic header
identification approach. The parser reads the first 20 lines, locates the
header row that contains a sufficient match for a known broker signature and
then maps the columns to the internal :class:`TransactionCreate` schema.
"""

import csv
import io
import re
from decimal import Decimal
from datetime import datetime
from typing import List, Dict, Tuple

from domain import schemas
from ..base import BaseParser, IngestionValidationError

# ---------------------------------------------------------------------------
# Broker signatures – minimal set of unique column names that identify a broker.
# The keys are broker names; the values are sets of column identifiers expected
# in the header (case‑insensitive).  At least three matches are required to
# accept a header as belonging to that broker.
# ---------------------------------------------------------------------------
BROKER_SIGNATURES: Dict[str, set] = {
    "zerodha": {"trade date", "isin", "name of security", "quantity", "price"},
    "groww": {"stock name", "isin", "symbol", "type", "quantity", "value", "execution date and time"},
    "upstox": {"order date", "isin", "instrument", "filled qty", "average price"},
    "angelone": {"trade timestamp", "isin", "security name", "qty", "price"},
    "fintrace_template": {"ticker", "transaction_type", "quantity", "price_per_unit", "execution_date"},
}

# Mapping from generic internal field names to possible CSV column names per broker.
COLUMN_MAP: Dict[str, Dict[str, str]] = {
    "zerodha": {
        "execution_date": "trade date",
        "ticker": "isin",
        "quantity": "quantity",
        "price_per_unit": "price",
        "brokerage_fees": "brokersage (if any)",  # optional
        "transaction_type": "transaction type",
        "settlement_date": "settlement date",
    },
    "groww": {
        "execution_date": "execution date and time",
        "ticker": "isin",
        "raw_symbol": "symbol",
        "exchange_code": "exchange",
        "quantity": "quantity",
        "total_value": "value",
        "price_per_unit": "price per unit",
        "brokerage_fees": "transaction charges",
        "transaction_type": "type",
    },
    "upstox": {
        "execution_date": "order date",
        "ticker": "isin",
        "quantity": "filled qty",
        "price_per_unit": "average price",
        "brokerage_fees": "brokerage",
        "transaction_type": "side",
        "settlement_date": "settlement date",
    },
    "angelone": {
        "execution_date": "trade timestamp",
        "ticker": "isin",
        "quantity": "qty",
        "price_per_unit": "price",
        "brokerage_fees": "brokerage",
        "transaction_type": "transaction type",
        "settlement_date": "settlement date",
    },
    "fintrace_template": {
        "execution_date": "execution_date",
        "ticker": "ticker",
        "quantity": "quantity",
        "price_per_unit": "price_per_unit",
        "brokerage_fees": "brokerage_fees",
        "transaction_type": "transaction_type",
        "settlement_date": "settlement_date",
    },
}

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _detect_broker(header: List[str]) -> Tuple[str, Dict[str, str]]:
    """Detect the broker based on header tokens.

    Returns the broker key and the column‑to‑field mapping derived from
    ``COLUMN_MAP`` for that broker.  If detection fails a ``ValueError`` is
    raised.
    """
    lowered = [h.strip().lower() for h in header]
    for broker, signatures in BROKER_SIGNATURES.items():
        matches = sum(1 for sig in signatures if any(sig in col for col in lowered))
        if matches >= 3:  # heuristic threshold
            # Build the mapping for this broker
            mapping = {
                field: col
                for field, col in COLUMN_MAP[broker].items()
                if col.lower() in lowered
            }
            return broker, mapping
    raise ValueError("Unable to detect broker from CSV header")


def _parse_date(value: str) -> datetime.date:
    """Parse a date string using common CSV formats.

    Tries ISO, DD‑MM‑YYYY, DD/MM/YYYY and fallback to ``dateutil`` when
    available.
    """
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except Exception:
            continue
    # As a last resort try dateutil (installed in the environment)
    try:
        from dateutil import parser as dparser
        return dparser.parse(value.strip(), dayfirst=True).date()
    except Exception as exc:
        raise ValueError(f"Unparseable date: {value}") from exc


def _coerce_decimal(value: str) -> Decimal:
    """Coerce a numeric string to Decimal, handling commas.
    """
    clean = value.replace(",", "").strip()
    try:
        return Decimal(clean)
    except Exception as exc:
        raise ValueError(f"Invalid numeric value: {value}") from exc


class BrokerCSVParser(BaseParser):
    """Concrete parser for broker CSV files.

    The class is deliberately stateless – all configuration is derived from the
    file content itself.
    """

    def parse(self, file_content: bytes, password: Optional[str] = None) -> List[schemas.TransactionCreate]:
        # ``password`` is ignored for CSV files but kept for interface consistency.
        decoded = file_content.decode("utf-8", errors="ignore")
        reader = csv.reader(io.StringIO(decoded))
        rows = list(reader)

        # -------------------------------------------------------------------
        # Header detection – scan up to the first 20 rows.
        # -------------------------------------------------------------------
        header_row_idx = None
        broker_key = None
        column_map = None
        for idx in range(min(20, len(rows))):
            potential_header = rows[idx]
            # consider a row a header if at least 4 non‑empty cells exist
            if sum(1 for cell in potential_header if cell.strip()) < 4:
                continue
            try:
                broker_key, column_map = _detect_broker(potential_header)
                header_row_idx = idx
                break
            except ValueError:
                continue
        if header_row_idx is None:
            raise IngestionValidationError([
                {"row": "header", "errors": ["Unable to locate a valid header for supported brokers"]}
            ])

        header = [h.strip().lower() for h in rows[header_row_idx]]
        # Build a map from CSV column index to internal field name
        index_to_field: Dict[int, str] = {}
        for field, col_name in column_map.items():
            if col_name.lower() in header:
                index_to_field[header.index(col_name.lower())] = field
        # ``brokerage_fees`` may be missing – we will default later.

        transaction_objs: List[schemas.TransactionCreate] = []
        validation_errors: List[dict] = []

        for line_no, row in enumerate(rows[header_row_idx + 1 :], start=header_row_idx + 2):
            if not any(cell.strip() for cell in row):
                # skip completely empty lines (often trailing newlines)
                continue
            try:
                data: dict = {}
                for idx, value in enumerate(row):
                    if idx not in index_to_field:
                        continue
                    field = index_to_field[idx]
                    if field == "execution_date" or field == "settlement_date":
                        data[field] = _parse_date(value)
                    elif field in {"quantity", "price_per_unit", "total_value"}:
                        data[field] = _coerce_decimal(value)
                    elif field == "brokerage_fees":
                        data[field] = _coerce_decimal(value) if value.strip() else Decimal("0.00")
                    elif field == "transaction_type":
                        # Normalise BUY/SELL strings – allow various cases
                        standardized = value.strip().upper()
                        if standardized not in {"BUY", "SELL", "DIVIDEND"}:
                            # Try common abbreviations
                            if standardized.startswith("B"):
                                standardized = "BUY"
                            elif standardized.startswith("S"):
                                standardized = "SELL"
                            else:
                                standardized = "DIVIDEND"
                        data[field] = standardized
                    else:
                        data[field] = value.strip()
                # Compute price_per_unit if total_value is provided instead
                if "total_value" in data and "price_per_unit" not in data:
                    if data.get("quantity", Decimal("0")) > 0:
                        data["price_per_unit"] = data["total_value"] / data["quantity"]
                    else:
                        data["price_per_unit"] = Decimal("0.00")

                # Dynamically construct yfinance ticker if symbol and exchange are present
                if "raw_symbol" in data and "exchange_code" in data:
                    sym = data["raw_symbol"].strip().upper()
                    ex = data["exchange_code"].strip().upper()
                    if ex in {"NSE", "BSE"}:
                        suffix = ".BO" if ex == "BSE" else ".NS"
                        data["ticker"] = f"{sym}{suffix}"

                # Ensure mandatory fields are present; missing brokerage handled later.
                for mandatory in ["ticker", "transaction_type", "quantity", "price_per_unit", "execution_date"]:
                    if mandatory not in data:
                        raise ValueError(f"Missing mandatory column: {mandatory}")
                # Default missing optional fields
                data.setdefault("brokerage_fees", Decimal("0.00"))
                data.setdefault("settlement_date", None)

                # Build Pydantic model – this validates dates, decimals, etc.
                transaction = schemas.TransactionCreate(**data)  # type: ignore[arg-type]
                transaction_objs.append(transaction)
            except Exception as exc:  # ValidationError from pydantic or our own
                validation_errors.append({"row": line_no, "errors": [str(exc)]})

        if validation_errors:
            raise IngestionValidationError(validation_errors)
        return transaction_objs
