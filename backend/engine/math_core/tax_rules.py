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


# --- Non-equity mutual funds (debt / hybrid / other) — Budget 2024 framework ------
#
# Indian MF taxation depends on the fund's equity allocation:
#   * Equity-oriented (>=65% equity)  -> taxed exactly like listed equity (111A/112A).
#     These are classified upstream as EQUITY_MF and use the equity helpers above.
#   * Specified funds / debt (<35% eq) acquired on/after 01-Apr-2023 -> Sec 50AA:
#     the entire gain is taxed at the investor's SLAB rate, regardless of holding
#     period. We cannot compute a rupee figure (slab depends on total income), so we
#     report the slab-taxable gain amount instead.
#   * Other / hybrid (35-65% eq) acquired on/after 01-Apr-2023 -> long-term (12.5%,
#     no indexation) if held > 24 months, else slab.
#   * Anything acquired before 01-Apr-2023 -> long-term if held > 36 months.
#
# Assumption: LTCG on non-equity is the current 12.5% no-indexation rate (transfers
# on/after 23-Jul-2024). Pre-2024 transfers (20% with indexation) are out of scope and
# would need the CII tables; today's date makes these rare.

SPECIFIED_FUND_CUTOFF = date(2023, 4, 1)
NONEQ_LTCG_RATE = Decimal("0.125")
NONEQ_LT_MONTHS_POST_2023 = 24   # hybrid/other acquired on/after 01-Apr-2023
NONEQ_LT_MONTHS_LEGACY = 36      # any non-equity acquired before 01-Apr-2023

EQUITY_TAX_CLASSES = {"EQUITY", "EQUITY_MF"}
NONEQ_TAX_CLASSES = {"DEBT_MF", "HYBRID_MF", "OTHER_MF"}


def noneq_tax_treatment(asset_class: str, buy_date: date, sell_date: date) -> Tuple[str, Decimal]:
    """Tax treatment for a realised NON-equity MF lot.

    Returns ``("LTCG", rate)`` for a long-term-eligible gain taxed at a fixed rate, or
    ``("SLAB", Decimal("0"))`` for a gain taxed at the investor's slab (reported, not
    rupee-computed). Debt funds acquired on/after 01-Apr-2023 are always SLAB (Sec 50AA).
    """
    if asset_class == "DEBT_MF":
        if buy_date >= SPECIFIED_FUND_CUTOFF:
            return ("SLAB", Decimal("0"))
        if sell_date > add_months(buy_date, NONEQ_LT_MONTHS_LEGACY):
            return ("LTCG", NONEQ_LTCG_RATE)
        return ("SLAB", Decimal("0"))

    # HYBRID_MF / OTHER_MF
    months = NONEQ_LT_MONTHS_POST_2023 if buy_date >= SPECIFIED_FUND_CUTOFF else NONEQ_LT_MONTHS_LEGACY
    if sell_date > add_months(buy_date, months):
        return ("LTCG", NONEQ_LTCG_RATE)
    return ("SLAB", Decimal("0"))


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
