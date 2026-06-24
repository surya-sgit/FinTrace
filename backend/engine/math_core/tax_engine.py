from decimal import Decimal, ROUND_HALF_UP
from collections import deque, defaultdict
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import asc

from domain.models import TransactionLedger
from engine.math_core import tax_rules

CENTS = Decimal("0.01")
ZERO = Decimal("0.0000")


def _money(value: Decimal) -> Decimal:
    """Round a Decimal to 2 places (paise) using half-up, the convention for tax."""
    return value.quantize(CENTS, rounding=ROUND_HALF_UP)


class FIFOTaxEngine:
    """
    Deterministic FIFO computation engine for Indian listed-equity capital gains.

    Strictly adheres to a zero-float policy using ``decimal.Decimal``. The engine:
      * matches sells to the oldest buys (FIFO), split-adjusting open lots;
      * folds brokerage into cost basis (buys) and net proceeds (sells);
      * classifies each realised lot as short/long term on a "> 12 months" rule;
      * applies Sec 112A grandfathering for pre-31-Jan-2018 acquisitions;
      * computes per-financial-year tax with current rates, the annual LTCG
        exemption, and intra/inter-year capital-loss set-off & 8-year carry-forward.

    See ``tax_rules`` for every statutory constant and the documented assumptions.
    """

    def __init__(
        self,
        db_session: Session,
        portfolio_id: str,
        fmv_overrides: Optional[Dict[str, Decimal]] = None,
    ):
        self.db = db_session
        self.portfolio_id = portfolio_id
        # Optional injection of FMV-as-on-31-Jan-2018 per ticker (used by tests and
        # callers that don't have AssetPrices populated for that date).
        self._fmv_overrides = fmv_overrides or {}

    # ------------------------------------------------------------------ helpers

    def _load_fmv_map(self, tickers: set) -> Dict[str, Decimal]:
        """FMV (per unit) on 31-Jan-2018, sourced from cached AssetPrices.

        Falls back to any explicit overrides passed to the constructor. Tickers
        without a known FMV simply receive no grandfathering benefit.
        """
        fmv_map: Dict[str, Decimal] = {}
        try:
            from domain.models import AssetPrices

            rows = (
                self.db.query(AssetPrices)
                .filter(
                    AssetPrices.ticker.in_(tickers),
                    AssetPrices.price_date == tax_rules.GRANDFATHERING_DATE,
                )
                .all()
            )
            for r in rows:
                price = r.adjusted_close if r.adjusted_close is not None else r.close_price
                if price is not None:
                    fmv_map[r.ticker] = Decimal(str(price))
        except Exception:
            # AssetPrices missing / unmapped — grandfathering just won't apply.
            pass

        fmv_map.update(self._fmv_overrides)
        return fmv_map

    # ----------------------------------------------------- realised-lot engine

    def compute_realized_gains(self) -> Dict[str, Any]:
        """
        Replay the immutable ledger chronologically and produce realised lots.

        Returns a dict with:
          * ``realized_stcg`` / ``realized_ltcg`` — signed net realised gains
            (kept for backward compatibility with existing callers/UI);
          * ``current_holdings`` — remaining unsold quantity per ticker;
          * ``realized_events`` — lot-level realised rows (the basis for tax);
          * ``dividends`` — dividend income grouped by financial year.
        """
        from domain.models import CorporateActionEvent

        transactions = (
            self.db.query(TransactionLedger)
            .filter(TransactionLedger.portfolio_id == self.portfolio_id)
            .order_by(
                asc(TransactionLedger.execution_date),
                asc(TransactionLedger.transaction_type),
            )
            .all()
        )

        unique_tickers = {tx.ticker for tx in transactions}
        fmv_map = self._load_fmv_map(unique_tickers)

        # Per-ticker tax routing class (EQUITY / EQUITY_MF / DEBT_MF / HYBRID_MF / OTHER_MF).
        asset_class_map = {
            tx.ticker: (getattr(tx, "asset_class", None) or "EQUITY") for tx in transactions
        }

        # Pre-fetch splits
        all_splits = (
            self.db.query(CorporateActionEvent)
            .filter(
                CorporateActionEvent.ticker.in_(unique_tickers),
                CorporateActionEvent.action_type == "SPLIT",
            )
            .order_by(CorporateActionEvent.ex_date.asc())
            .all()
        )
        splits_map: Dict[str, Dict] = {}
        for sp in all_splits:
            splits_map.setdefault(sp.ticker, {})[sp.ex_date] = Decimal(str(sp.adjustment_factor))

        # Pre-fetch auto-synced dividends (per-share, keyed by ex-date). Income is
        # derived from shares held on the ex-date, so users never enter dividends.
        all_dividend_events = (
            self.db.query(CorporateActionEvent)
            .filter(
                CorporateActionEvent.ticker.in_(unique_tickers),
                CorporateActionEvent.action_type == "DIVIDEND",
            )
            .order_by(CorporateActionEvent.ex_date.asc())
            .all()
        )
        dividend_map: Dict[str, Dict] = {}
        for dv in all_dividend_events:
            dividend_map.setdefault(dv.ticker, {})[dv.ex_date] = Decimal(str(dv.adjustment_factor))

        # Group ledgers by ticker
        ledgers_by_ticker: Dict[str, List] = defaultdict(list)
        dividends_by_fy: Dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
        # (ticker, date) pairs with a manually-entered dividend row — used to avoid
        # double-counting against auto-synced dividend events on the same day.
        manual_dividend_keys = set()
        for tx in transactions:
            if tx.transaction_type == "DIVIDEND":
                # Manually-entered dividend: amount = per-share payout * shares.
                amount = Decimal(str(tx.quantity)) * Decimal(str(tx.price_per_unit))
                _, fy_label = tax_rules.financial_year(tx.execution_date)
                dividends_by_fy[fy_label] += amount
                manual_dividend_keys.add((tx.ticker, tx.execution_date))
                continue
            ledgers_by_ticker[tx.ticker].append(tx)

        total_stcg = ZERO
        total_ltcg = ZERO
        unsold_inventory: Dict[str, Decimal] = {}
        realized_events: List[Dict[str, Any]] = []

        for ticker, ledger in ledgers_by_ticker.items():
            buy_queue: deque = deque()

            tx_by_date: Dict = defaultdict(list)
            for tx in ledger:
                tx_by_date[tx.execution_date].append(tx)

            ticker_splits = splits_map.get(ticker, {})
            ticker_dividends = dividend_map.get(ticker, {})
            ticker_fmv = fmv_map.get(ticker)
            ticker_asset_class = asset_class_map.get(ticker, "EQUITY")
            ticker_is_equity = ticker_asset_class in tax_rules.EQUITY_TAX_CLASSES

            all_dates = set(tx_by_date.keys()) | set(ticker_splits.keys()) | set(ticker_dividends.keys())
            for current_date in sorted(all_dates):
                # Apply splits before the day's trades.
                if current_date in ticker_splits:
                    factor = ticker_splits[current_date]
                    for lot in buy_queue:
                        lot["remaining_quantity"] *= factor
                        lot["cost_per_unit"] /= factor
                        lot["fee_per_unit"] /= factor

                # Auto dividend: income = shares held on the ex-date (after splits,
                # before same-day trades) x per-share payout. Skip if the user already
                # recorded a manual dividend for this ticker on this date.
                if current_date in ticker_dividends and (ticker, current_date) not in manual_dividend_keys:
                    held_qty = sum((lot["remaining_quantity"] for lot in buy_queue), ZERO)
                    if held_qty > ZERO:
                        amount = held_qty * ticker_dividends[current_date]
                        _, fy_label = tax_rules.financial_year(current_date)
                        dividends_by_fy[fy_label] += amount

                for tx in tx_by_date.get(current_date, []):
                    if tx.transaction_type == "BUY":
                        qty = Decimal(str(tx.quantity))
                        fees = Decimal(str(tx.brokerage_fees or 0))
                        buy_queue.append(
                            {
                                "execution_date": tx.execution_date,
                                "remaining_quantity": qty,
                                "cost_per_unit": Decimal(str(tx.price_per_unit)),
                                "fee_per_unit": (fees / qty) if qty else ZERO,
                            }
                        )

                    elif tx.transaction_type == "SELL":
                        sell_qty = Decimal(str(tx.quantity))
                        sell_price = Decimal(str(tx.price_per_unit))
                        sell_fees = Decimal(str(tx.brokerage_fees or 0))
                        sell_fee_per_unit = (sell_fees / sell_qty) if sell_qty else ZERO

                        sell_qty_remaining = sell_qty
                        while sell_qty_remaining > ZERO and buy_queue:
                            oldest = buy_queue[0]
                            matched = min(sell_qty_remaining, oldest["remaining_quantity"])

                            # Net proceeds: sale value minus this slice of sell fees.
                            proceeds = matched * sell_price - matched * sell_fee_per_unit

                            cost_per_unit = oldest["cost_per_unit"]
                            grandfathered = False
                            fmv_used = None

                            if ticker_is_equity:
                                # Listed equity / equity-oriented MF: Sec 111A/112A.
                                long_term = tax_rules.is_long_term(
                                    oldest["execution_date"], tx.execution_date
                                )
                                treatment = "EQUITY_LT" if long_term else "EQUITY_ST"
                                # Sec 112A grandfathering for LT lots bought <= 31-Jan-2018.
                                if (
                                    long_term
                                    and ticker_fmv is not None
                                    and oldest["execution_date"] <= tax_rules.GRANDFATHERING_DATE
                                ):
                                    cost_per_unit = tax_rules.grandfathered_cost_per_unit(
                                        actual_cost_per_unit=oldest["cost_per_unit"],
                                        sale_price_per_unit=sell_price,
                                        fmv_31jan2018_per_unit=ticker_fmv,
                                    )
                                    grandfathered = cost_per_unit != oldest["cost_per_unit"]
                                    fmv_used = ticker_fmv
                            else:
                                # Non-equity MF (debt/hybrid/other): no grandfathering,
                                # no 112A exemption. Either fixed-rate LTCG or slab.
                                kind, _rate = tax_rules.noneq_tax_treatment(
                                    ticker_asset_class, oldest["execution_date"], tx.execution_date
                                )
                                treatment = "NONEQ_LTCG" if kind == "LTCG" else "SLAB"
                                long_term = treatment == "NONEQ_LTCG"

                            cost_basis = matched * cost_per_unit + matched * oldest["fee_per_unit"]
                            gain = proceeds - cost_basis

                            fy_start, fy_label = tax_rules.financial_year(tx.execution_date)
                            realized_events.append(
                                {
                                    "ticker": ticker,
                                    "asset_class": ticker_asset_class,
                                    "treatment": treatment,
                                    "buy_date": oldest["execution_date"],
                                    "sell_date": tx.execution_date,
                                    "quantity": matched,
                                    "cost_basis": cost_basis,
                                    "proceeds": proceeds,
                                    "gain": gain,
                                    "is_long_term": long_term,
                                    "grandfathered": grandfathered,
                                    "fmv_used": fmv_used,
                                    "fy_start": fy_start,
                                    "fy_label": fy_label,
                                    "current_regime": tax_rules.is_current_regime(
                                        tx.execution_date
                                    ),
                                }
                            )

                            # Backward-compatible aggregates reflect EQUITY only; the
                            # non-equity section is reported separately.
                            if ticker_is_equity:
                                if long_term:
                                    total_ltcg += gain
                                else:
                                    total_stcg += gain

                            sell_qty_remaining -= matched
                            oldest["remaining_quantity"] -= matched
                            if oldest["remaining_quantity"] <= ZERO:
                                buy_queue.popleft()

                        if sell_qty_remaining > ZERO:
                            # Ledger integrity violation: selling shares never bought.
                            # Never fabricate a 100%-profit phantom gain (old bug).
                            raise ValueError(
                                f"Ledger integrity error: SELL of {sell_qty} {ticker} on "
                                f"{tx.execution_date} exceeds available holdings by "
                                f"{sell_qty_remaining}."
                            )

            remaining = sum((lot["remaining_quantity"] for lot in buy_queue), ZERO)
            if remaining > ZERO:
                unsold_inventory[ticker] = remaining

        return {
            "realized_stcg": total_stcg,
            "realized_ltcg": total_ltcg,
            "current_holdings": unsold_inventory,
            "realized_events": realized_events,
            "dividends": dict(dividends_by_fy),
        }

    # -------------------------------------------------------- tax computation

    def compute_tax_report(self) -> Dict[str, Any]:
        """Full file-ready report: per-FY tax with set-off, exemption and carry-forward."""
        base = self.compute_realized_gains()
        events = base["realized_events"]
        dividends = base["dividends"]

        events_by_fy: Dict[int, List[Dict]] = defaultdict(list)
        for e in events:
            events_by_fy[e["fy_start"]].append(e)

        # Brought-forward loss pools: each entry {"origin": fy_start, "amount": Decimal}.
        st_carry: List[Dict] = []
        lt_carry: List[Dict] = []
        # Non-equity pools are kept separate from equity (a documented simplification:
        # we don't cross-set-off equity vs non-equity LT, though the law permits it).
        noneq_lt_carry: List[Dict] = []
        slab_carry: List[Dict] = []

        financial_years: List[Dict[str, Any]] = []
        total_tax = Decimal("0.00")
        total_slab_gain = Decimal("0.00")

        for fy_start in sorted(events_by_fy.keys()):
            evs = events_by_fy[fy_start]
            _, fy_label = tax_rules.financial_year(evs[0]["sell_date"])

            # Expire carry-forward losses older than 8 assessment years.
            st_carry = [c for c in st_carry if c["amount"] > 0 and c["origin"] + 8 >= fy_start]
            lt_carry = [c for c in lt_carry if c["amount"] > 0 and c["origin"] + 8 >= fy_start]
            noneq_lt_carry = [c for c in noneq_lt_carry if c["amount"] > 0 and c["origin"] + 8 >= fy_start]
            slab_carry = [c for c in slab_carry if c["amount"] > 0 and c["origin"] + 8 >= fy_start]

            # Bucket gains by tax treatment; aggregate current-year losses.
            st_gains = {"pre": ZERO, "post": ZERO}     # equity STCG (111A)
            lt_gains = {"pre": ZERO, "post": ZERO}     # equity LTCG (112A)
            cy_st_loss = ZERO
            cy_lt_loss = ZERO
            noneq_lt_gain = ZERO                        # non-equity LTCG @12.5%
            noneq_lt_loss = ZERO
            slab_gain = ZERO                            # non-equity slab-taxed gain
            slab_loss = ZERO
            for e in evs:
                reg = "post" if e["current_regime"] else "pre"
                treatment = e.get("treatment", "EQUITY_LT" if e["is_long_term"] else "EQUITY_ST")
                if treatment == "NONEQ_LTCG":
                    if e["gain"] >= 0:
                        noneq_lt_gain += e["gain"]
                    else:
                        noneq_lt_loss += -e["gain"]
                elif treatment == "SLAB":
                    if e["gain"] >= 0:
                        slab_gain += e["gain"]
                    else:
                        slab_loss += -e["gain"]
                elif treatment == "EQUITY_LT":
                    if e["gain"] >= 0:
                        lt_gains[reg] += e["gain"]
                    else:
                        cy_lt_loss += -e["gain"]
                else:  # EQUITY_ST
                    if e["gain"] >= 0:
                        st_gains[reg] += e["gain"]
                    else:
                        cy_st_loss += -e["gain"]

            # Signed net realised gain for the FY (gains minus losses), captured
            # before set-off mutates the buckets.
            gross_st_gain = st_gains["pre"] + st_gains["post"] - cy_st_loss
            gross_lt_gain = lt_gains["pre"] + lt_gains["post"] - cy_lt_loss

            # --- Set-off (reduce higher-rate "post" buckets first — taxpayer favourable)
            cy_lt_loss = self._apply_loss(cy_lt_loss, lt_gains)          # LT loss -> LT gain
            cy_st_loss = self._apply_loss(cy_st_loss, st_gains)          # ST loss -> ST gain
            cy_st_loss = self._apply_loss(cy_st_loss, lt_gains)          # ST loss -> LT gain
            self._apply_carry(lt_carry, [lt_gains])                     # b/f LT -> LT gain
            self._apply_carry(st_carry, [st_gains, lt_gains])           # b/f ST -> ST then LT

            # Unabsorbed current-year losses carry forward.
            if cy_lt_loss > 0:
                lt_carry.append({"origin": fy_start, "amount": cy_lt_loss})
            if cy_st_loss > 0:
                st_carry.append({"origin": fy_start, "amount": cy_st_loss})

            # --- LTCG annual exemption against remaining LT gains (post first).
            exemption = tax_rules.ltcg_exemption(fy_start)
            exemption_used = self._apply_loss(exemption, lt_gains)
            exemption_applied = exemption - exemption_used

            # --- Non-equity LTCG (12.5%, no exemption): own set-off + carry pool.
            noneq_lt_gain, noneq_lt_loss = self._net_and_carry(
                noneq_lt_gain, noneq_lt_loss, noneq_lt_carry, fy_start
            )
            noneq_lt_tax = noneq_lt_gain * tax_rules.NONEQ_LTCG_RATE

            # --- Slab-taxed non-equity (Sec 50AA / short-term): netted & reported, not
            # rupee-taxed (slab depends on the investor's total income).
            slab_gain, slab_loss = self._net_and_carry(
                slab_gain, slab_loss, slab_carry, fy_start
            )
            total_slab_gain += slab_gain

            # --- Tax at the bucket rates.
            tax_st = (
                st_gains["pre"] * tax_rules.STCG_RATE_LEGACY
                + st_gains["post"] * tax_rules.STCG_RATE_CURRENT
            )
            tax_lt = (
                lt_gains["pre"] * tax_rules.LTCG_RATE_LEGACY
                + lt_gains["post"] * tax_rules.LTCG_RATE_CURRENT
            )
            fy_tax = _money(tax_st + tax_lt + noneq_lt_tax)
            total_tax += fy_tax

            financial_years.append(
                {
                    "financial_year": fy_label,
                    "gross_stcg": _money(gross_st_gain),
                    "gross_ltcg": _money(gross_lt_gain),
                    "taxable_stcg": _money(st_gains["pre"] + st_gains["post"]),
                    "taxable_ltcg": _money(lt_gains["pre"] + lt_gains["post"]),
                    "ltcg_exemption_applied": _money(exemption_applied),
                    "stcg_tax": _money(tax_st),
                    "ltcg_tax": _money(tax_lt),
                    "noneq_ltcg_gain": _money(noneq_lt_gain),
                    "noneq_ltcg_tax": _money(noneq_lt_tax),
                    "slab_taxable_gain": _money(slab_gain),
                    "total_tax": fy_tax,
                    "dividend_income": _money(dividends.get(fy_label, Decimal("0.00"))),
                    "stcg_loss_carried_forward": _money(
                        sum((c["amount"] for c in st_carry if c["origin"] == fy_start), ZERO)
                    ),
                    "ltcg_loss_carried_forward": _money(
                        sum((c["amount"] for c in lt_carry if c["origin"] == fy_start), ZERO)
                    ),
                }
            )

        return {
            # Backward-compatible aggregate fields (EQUITY only).
            "realized_stcg": base["realized_stcg"],
            "realized_ltcg": base["realized_ltcg"],
            "current_holdings": base["current_holdings"],
            # New file-ready detail.
            "financial_years": financial_years,
            "total_tax_payable": _money(total_tax),
            "slab_taxable_gain": _money(total_slab_gain),
            "realized_events": events,
            "dividends": dividends,
        }

    # ------------------------------------------------------------ set-off math

    @staticmethod
    def _apply_loss(loss: Decimal, gains: Dict[str, Decimal]) -> Decimal:
        """Consume ``loss`` against ``gains`` (post bucket first). Returns remaining loss."""
        for reg in ("post", "pre"):
            if loss <= 0:
                break
            take = min(loss, gains[reg])
            gains[reg] -= take
            loss -= take
        return loss

    @staticmethod
    def _net_and_carry(gain: Decimal, loss: Decimal, carry: List[Dict], fy_start: int):
        """Single-rate set-off: net current-year loss, then brought-forward losses
        (oldest first), then carry any unabsorbed current-year loss forward. Returns
        the remaining (gain, loss)."""
        offset = min(loss, gain)
        gain -= offset
        loss -= offset
        for entry in sorted(carry, key=lambda c: c["origin"]):
            if gain <= 0:
                break
            take = min(entry["amount"], gain)
            entry["amount"] -= take
            gain -= take
        if loss > 0:
            carry.append({"origin": fy_start, "amount": loss})
        return gain, loss

    @staticmethod
    def _apply_carry(carry: List[Dict], gain_buckets: List[Dict[str, Decimal]]) -> None:
        """Consume brought-forward losses (oldest first) against the given gain buckets."""
        for entry in sorted(carry, key=lambda c: c["origin"]):
            for gains in gain_buckets:
                for reg in ("post", "pre"):
                    if entry["amount"] <= 0:
                        break
                    take = min(entry["amount"], gains[reg])
                    gains[reg] -= take
                    entry["amount"] -= take
