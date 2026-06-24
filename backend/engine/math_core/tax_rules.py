"""
Indian capital-gains tax rules for listed equity (STT-paid) — Sections 111A & 112A.

Centralises every rate, threshold and date boundary the FIFO engine needs so that a
finance/tax reviewer can audit and tweak the law in one place. All money values use
``decimal.Decimal`` to preserve the zero-float policy of the engine.

Assumptions (documented so they can be challenged):
  * Only listed equity / equity mutual funds on which STT was paid (Sec 111A/112A).
    F&O, debt funds, unlisted shares and intraday speculative income are NOT modelled.
  * Holding period for long-term qualification is "more than 12 months" (calendar
    months, leap-year safe) — not a flat 365-day count.
  * Budget 2024 changed rates and the LTCG exemption with effect from the date of
    transfer 23-Jul-2024; classification here is therefore based on the SELL date.
"""

from __future__ import annotations

import calendar
from datetime import date
from decimal import Decimal
from typing import Tuple

# --- Statutory date boundaries -------------------------------------------------

# Date of transfer on/after which Budget-2024 rates and the higher LTCG exemption
# apply. Sales strictly before this date use the legacy rates.
BUDGET_2024_CUTOFF = date(2024, 7, 23)

# Grandfathering reference date for Sec 112A. Equity acquired on/before this date
# gets the "higher of cost / FMV" cost-step-up benefit.
GRANDFATHERING_DATE = date(2018, 1, 31)

# Listed equity becomes long-term when held for MORE THAN this many months.
LTCG_HOLDING_MONTHS = 12

# --- Rates (as decimal fractions) ----------------------------------------------

STCG_RATE_LEGACY = Decimal("0.15")   # 15% — sales before 23-Jul-2024
STCG_RATE_CURRENT = Decimal("0.20")  # 20% — sales on/after 23-Jul-2024

LTCG_RATE_LEGACY = Decimal("0.10")    # 10% — sales before 23-Jul-2024
LTCG_RATE_CURRENT = Decimal("0.125")  # 12.5% — sales on/after 23-Jul-2024

# --- Per financial-year LTCG exemption -----------------------------------------

LTCG_EXEMPTION_LEGACY = Decimal("100000")   # ₹1,00,000 up to FY 2023-24
LTCG_EXEMPTION_CURRENT = Decimal("125000")  # ₹1,25,000 from FY 2024-25

# First FY (by start year) in which the higher ₹1.25L exemption applies.
EXEMPTION_RAISE_FY_START = 2024


def financial_year(d: date) -> Tuple[int, str]:
    """Return ``(start_year, label)`` for the Indian FY (Apr 1 - Mar 31) holding ``d``.

    >>> financial_year(date(2024, 5, 1))
    (2024, '2024-25')
    >>> financial_year(date(2024, 2, 1))
    (2023, '2023-24')
    """
    start = d.year if d.month >= 4 else d.year - 1
    return start, f"{start}-{str(start + 1)[-2:]}"


def add_months(d: date, months: int) -> date:
    """Add calendar months to a date, clamping the day for shorter months."""
    zero_based = d.month - 1 + months
    year = d.year + zero_based // 12
    month = zero_based % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def is_long_term(buy_date: date, sell_date: date) -> bool:
    """True if a listed-equity holding qualifies as long-term (> 12 months)."""
    return sell_date > add_months(buy_date, LTCG_HOLDING_MONTHS)


def is_current_regime(sell_date: date) -> bool:
    """True if the Budget-2024 rates/exemption apply to this transfer."""
    return sell_date >= BUDGET_2024_CUTOFF


def stcg_rate(sell_date: date) -> Decimal:
    return STCG_RATE_CURRENT if is_current_regime(sell_date) else STCG_RATE_LEGACY


def ltcg_rate(sell_date: date) -> Decimal:
    return LTCG_RATE_CURRENT if is_current_regime(sell_date) else LTCG_RATE_LEGACY


def ltcg_exemption(fy_start_year: int) -> Decimal:
    """Annual LTCG exemption (Sec 112A) for the FY identified by its start year."""
    return (
        LTCG_EXEMPTION_CURRENT
        if fy_start_year >= EXEMPTION_RAISE_FY_START
        else LTCG_EXEMPTION_LEGACY
    )


def grandfathered_cost_per_unit(
    actual_cost_per_unit: Decimal,
    sale_price_per_unit: Decimal,
    fmv_31jan2018_per_unit: Decimal,
) -> Decimal:
    """Sec 112A grandfathered cost of acquisition, per unit.

    CoA = higher of [actual cost] and [lower of (FMV on 31-Jan-2018, sale value)].
    """
    lower_of_fmv_and_sale = min(fmv_31jan2018_per_unit, sale_price_per_unit)
    return max(actual_cost_per_unit, lower_of_fmv_and_sale)
