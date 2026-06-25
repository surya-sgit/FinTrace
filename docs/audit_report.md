# FinTrace Codebase Audit Report: Logical, Mathematical, and Architectural Flaws

**Date**: 2026-06-23  
**Status**: Consolidated Analysis Complete  
**Target Location**: `d:\Project Work\FinTrace\audit_report.md`  

---

## Executive Summary

An in-depth codebase audit of FinTrace was performed to evaluate its logical consistency, mathematical correctness, and architectural integrity. FinTrace is a quantitative retail portfolio analytics platform featuring ingestion pipelines, FIFO tax calculation, XIRR performance solvers, portfolio risk analytics (Sharpe, Drawdown, Alpha, Beta), and a RAG-powered Text-to-SQL Copilot.

This audit reveals **fifteen (15) critical mathematical, logical, and architectural flaws** that compromise the system's correctness, performance, and stability. 

### Core Audit Verdict
Calculations produced by the current codebase are **mathematically invalid and unsafe for financial reporting**. Ingestion rules drop corporate actions on non-transaction dates; the tax engine ignores brokerage fees and treats short positions as zero-cost basis sales; the XIRR engine reports silent -100% returns on API query failures; and the risk metrics engine generates a corrupted NAV series by omitting cash balances. Furthermore, the RAG Copilot is vulnerable to SQLite schema crashes on empty portfolios and type leakages.

---

## Scope & Examined Modules

The audit covered the entire backend engine, schema definitions, and frontend components:
- **Ingestion & Data Flow**: `backend/engine/ingestion/ledger_validator.py`, `backend/engine/ingestion/parsers/csv_parser.py`, `backend/engine/ingestion/parsers/pdf_parser.py`, `backend/engine/live_pricing.py`
- **Market Data & Service Layer**: `backend/engine/market_data/corporate_actions.py`, `backend/engine/market_data/market_service.py`
- **Math Core Engines**: `backend/engine/math_core/tax_engine.py`, `backend/engine/math_core/xirr_engine.py`
- **Database & Services**: `backend/domain/models.py`, `backend/domain/services/transaction_service.py`, `backend/api/routers/reports.py`, `backend/api/routers/copilot.py`
- **Analytics & Risk Engine**: `backend/engine/analytics/attribution.py`, `backend/engine/analytics/long_term_attribution.py`, `backend/engine/analytics/risk_metrics.py`, `backend/engine/analytics/behavioral.py`
- **Copilot Query Engine**: `backend/engine/copilot/agent.py`
- **Frontend & Verification**: `frontend/components/portfolio/LongTermTab.test.ts` (capping and sorting validation)

---

## Part 1: Dropped Financial Data Assumptions across Boundaries

A major source of mathematical inconsistency is the dropping or silent deletion of financial data assumptions as they traverse database, ingestion, core math, and analytics layers:

| Data Assumption | Ingestion Layer | Core Math (Tax/XIRR) | Analytics / Risk Engine | Copilot Layer |
| :--- | :--- | :--- | :--- | :--- |
| **Brokerage Fees** | Extracted from statement by parsers and stored in DB. | **DROPPED**: Ignored in FIFO tax calculation, overstating gains. | **DROPPED**: Ignored in NAV and cash tracking. | **MUTATED**: Cast to `TEXT` in temp database, breaking SQL math. |
| **Bonus Actions** | Ignored by queries. | **DROPPED**: Not factored into portfolio balances or XIRR. | **DROPPED**: Excluded from holdings and performance. | **DROPPED**: Excluded from index mappings. |
| **Stock Splits** | Validated only on transaction dates, dropping ex-date splits. | Applied to transaction history retrospectively. | Applied to daily position holdings calculations. | Excluded from text-to-SQL pricing queries. |
| **Cash Balances** | Tracked via DEPOSIT/WITHDRAWAL records in DB. | **DROPPED**: Excluded from XIRR net deployed capital calculations. | **DROPPED**: Excluded from NAV, corrupting daily returns. | **DROPPED**: Excluded from basic portfolio schemas. |
| **Dividends** | Stored in ledger. | **MUTATED**: Subtracted from capital deployed, distorting XIRR denominator. | Excluded from Daily NAV drift. | Can cause schema lookup failures. |
| **Settlement Date** | Stored in DB but commented as "For CA mapping". | **DROPPED**: Calculations use execution date only. | **DROPPED**: Ignored. | **DROPPED**: Ignored. |

---

## Part 2: In-Depth Flaw Directory & Verification

### Ingestion & Market Data Layer Flaws

#### Flaw 1: Ledger Validator Skips Corporate Actions on Non-Transaction Dates
- **File**: `backend/engine/ingestion/ledger_validator.py` (Lines 68-70)
- **Logical Flaw**: The validator groups transactions by execution date and iterates through them. It checks corporate action ex-dates (splits) *only* if there is a transaction on that exact date. Splits occurring on dates with no buying or selling are completely ignored.
- **Proof of Failure / Impact**:
  Suppose a user holds 10 shares of Stock A bought on Day 1. A 2:1 stock split occurs on Day 5 (no transactions occur). The user sells 15 shares on Day 10.
  - *Actual Quantity*: 20 shares (adjusted for split). Sell of 15 is valid.
  - *Engine calculation*: Day 5 split is skipped because no transactions occurred. Validator sees pre-split balance of 10 shares. On Day 10, selling 15 shares drives the running balance to `-5`. The engine raises a `ValueError` (negative balance), crashing the CSV upload.

#### Flaw 2: Checksum Bypasses Casing Normalization
- **File**: `backend/domain/services/transaction_service.py` (Lines 24-27, 80-84)
- **Logical Flaw**: Checksum generation is case-sensitive and hashes the raw ticker casing from the CSV (`row_data.get('ticker')`). However, the SQLAlchemy model constructor Upper-cases the ticker (`ticker=txn.ticker.upper()`) before database saving.
- **Proof of Failure / Impact**:
  If a file contains two identical transactions, one with ticker `"aapl"` and another with `"AAPL"`:
  - Checksum 1: `hash("aapl_BUY_...")`
  - Checksum 2: `hash("AAPL_BUY_...")`
  Because the hashes are different, both bypass the Pydantic/Service duplicate checker. During database insertion, both are saved with ticker `"AAPL"`. The system now contains duplicate transaction records, doubling the portfolio value.

#### Flaw 3: Direct ISIN Mapping Breaks Market Price Ingestion
- **Files**: `backend/engine/ingestion/parsers/csv_parser.py` (Line 37) and `pdf_parser.py` (Line 149)
- **Logical Flaw**: Standard Indian broker statements (Zerodha, Upstox, etc.) map the ISIN column directly to the transaction ticker (e.g., storing `INE002A01018` in the database). Yahoo Finance cannot resolve ISIN codes, resulting in failed market price lookups.
- **Proof of Failure / Impact**:
  A user imports a Zerodha ledger. Ticker is saved as `INE002A01018` instead of `RELIANCE.NS`. The pricing engine queries yfinance for `INE002A01018`, which returns no data. The XIRR and risk metrics engine fall back to `0.00`, reporting a fake -100% return on the asset.

#### Flaw 4: Bonus Shares Excluded from Ingestion queries
- **File**: `backend/engine/ingestion/ledger_validator.py` (Lines 54-57), `tax_engine.py`, `xirr_engine.py`
- **Logical Flaw**: The systems query `CorporateActionEvent` filtering strictly for `action_type == "SPLIT"`. Corporate actions of type `"BONUS"` are completely ignored.
- **Proof of Failure / Impact**:
  A 1:1 bonus issue doubles the holdings of an asset. Since the engines ignore `"BONUS"`, a subsequent sell transaction will trigger a negative balance exception in the validator, or calculate a vastly incorrect cost basis in the tax engine by ignoring the bonus lot.

#### Flaw 5: Synchronous `yfinance` Calls Block the FastAPI Event Loop
- **File**: `backend/engine/live_pricing.py` (Line 32)
- **Logical Flaw**: Sequential pricing queries retrieve prices using `stock.fast_info.get('last_price')`. This synchronous network call is executed inside `async def fetch_tier3_yfinance` without thread offloading.
- **Proof of Failure / Impact**:
  When a background pricing loop executes, uvicorn's single event loop thread blocks entirely while waiting for Yahoo Finance network responses. During this time, the FastAPI server cannot reply to simple incoming REST requests, leading to temporary gateway timeouts.

#### Flaw 6: Hardcoded Indexing Swaps Quantity and Price in PDF Parser
- **File**: `backend/engine/ingestion/parsers/pdf_parser.py` (Lines 129-130)
- **Logical Flaw**: The parser handles rows based on static indexes: `row[4] if len(row) > 4 else row[3]` for quantity, and `row[5] if len(row) > 5 else row[4]` for price.
- **Proof of Failure / Impact**:
  In a standard NSDL/CDSL CAS PDF statement containing 6 columns (e.g., Ticker, Date, Type, Quantity, Price, Brokerage), `len(row)` is 6. Under these conditions, the parser maps:
  - Quantity = `row[4]` (which is actually the unit price).
  - Price = `row[5]` (which is actually the brokerage fee).
  This swaps the transaction unit price and quantity, resulting in massive mathematical distortions in database records.

---

### Tax Calculation & XIRR Math Engine Flaws

#### Flaw 7: Non-Deterministic Same-Day Transaction Sorting
- **File**: `backend/engine/math_core/tax_engine.py` (Lines 31-36), `xirr_engine.py` (Lines 24-26)
- **Logical Flaw**: The query filters by portfolio ID and sorts by `execution_date` ascending and `transaction_type` ascending. Since `"BUY"` precedes `"SELL"` alphabetically, the engine forces all same-day BUYs to execute before SELLs.
- **Proof of Failure / Impact**:
  For an intraday short position (where a user sells at 10:00 AM and buys back at 3:00 PM):
  - *Actual Order*: SELL $\rightarrow$ BUY.
  - *Engine Order*: BUY $\rightarrow$ SELL.
  The engine processes the BUY first. This masks the short transaction as a long liquidation. Furthermore, if a user makes multiple BUYs on the same day at different prices, the absence of a secondary sort key (such as auto-incremented database ID or creation timestamp) causes non-deterministic FIFO lot matching.

#### Flaw 8: Zero-Cost Basis Assumption for Short Positions
- **File**: `backend/engine/math_core/tax_engine.py` (Lines 124-126)
- **Logical Flaw**: If a transaction's sell quantity exceeds the total available buys in the FIFO lot queue, the engine assumes the remaining shares sold have a cost basis of zero, adding the entire sale value to Short-Term Capital Gains (`total_stcg`).
- **Mathematical Proof of Distortion**:
  Suppose a user opens a short position on Day 1 by selling 10 shares of RELIANCE at ₹2,500, and covers it on Day 2 by buying 10 shares at ₹2,400.
  $$\text{Actual Capital Gain} = 10 \times (2,500 - 2,400) = \text{₹1,000}$$
  *Engine Math*:
  - Day 1: Queue is empty. Remaining sell quantity = 10. `total_stcg += 10 * 2,500 = ₹25,000`.
  - Day 2: Buy lot of 10 shares at ₹2,400 goes into the queue and remains there indefinitely.
  - *Resulting Error*: Realized gains are reported as ₹25,000, over-reporting capital gains tax liability by ₹24,000.

#### Flaw 9: Disregard of Transaction Fees in Tax Math
- **File**: `backend/engine/math_core/tax_engine.py`
- **Logical Flaw**: The tax engine calculates realized profit as `sell_value - buy_value` based purely on unit prices, completely ignoring the `brokerage_fees` column.
- **Mathematical Proof of Distortion**:
  Under Section 48 of the Indian Income Tax Act, transaction fees are deductible transfer expenses.
  $$\text{Correct Cost of Acquisition} = (\text{Quantity} \times \text{Buy Price}) + \text{Buy Brokerage}$$
  $$\text{Correct Net Sale Proceeds} = (\text{Quantity} \times \text{Sell Price}) - \text{Sell Brokerage}$$
  By ignoring these fees, the engine artificially inflates the capital gains tax liability.

#### Flaw 10: Silent XIRR Distortion on Missing Price Data
- **File**: `backend/engine/math_core/xirr_engine.py` (Lines 184-192)
- **Logical Flaw**: When querying Yahoo Finance fails to return a terminal EOD price, the engine catches a `ValueError` and falls back to a price of `0.00`, appending `0.00` to the XIRR cash flows today.
- **Mathematical Proof of Distortion**:
  Setting the terminal asset value to 0.00 is mathematically equivalent to a total loss of the asset.
  Suppose a user invested ₹100,000 in TCS, which is now worth ₹150,000. If the API lookup fails:
  $$\text{Cash Flows Array} = [(-100,000, \text{2025-06-23}), (0.00, \text{2026-06-23})]$$
  $$\text{Computed XIRR} = -100.0\%$$
  The portfolio return metric drops to -100%, reporting a complete loss of capital when the actual return is +50%.

#### Flaw 11: Mismatched Schema and Deployed Capital Formula
- **Files**: `backend/engine/math_core/xirr_engine.py` (Lines 61, 104, 117, 209), `backend/api/routers/reports.py` (Lines 72-76)
- **Logical Flaws**:
  1. `xirr_engine.py` calculates `net_deployed_capital` by tracking buys and sells, but fails to return it. Instead, it returns `net_cash_flow` which includes received dividends. If dividends received exceed net invested capital, net deployed capital is reported as `0.00`.
  2. In `reports.py`, the response schema field `total_invested_capital` maps to `current_cost_basis` (which only tracks the cost basis of remaining unsold holdings). If a user invested ₹500,000, sold ₹450,000, and holds ₹50,000, the API returns `total_invested_capital = 50,000`, hiding the cumulative deployed capital.

#### Flaw 12: Unique Checksum Constraints Block legitimate Same-Day Trades
- **File**: `backend/domain/services/transaction_service.py` (Lines 24-27), `backend/domain/models.py` (Line 58)
- **Logical Flaw**: The unique transaction checksum is generated from `portfolio_id`, `ticker`, `type`, `quantity`, `price`, and `execution_date`.
- **Proof of Failure / Impact**:
  If an active trader executes two identical trades (e.g., buying 100 shares of RELIANCE at ₹2,500 in the morning, and another 100 shares at ₹2,500 in the afternoon), both records generate the exact same checksum hash. The database unique constraint triggers an `IntegrityError` and rejects the second trade as a duplicate, making it impossible to upload statements containing same-day identical trades.

---

### Portfolio Performance & Analytics Engine Flaws

#### Flaw 13: RiskMetricsEngine Corrupts Returns series by Omitting Cash Balance
- **File**: `backend/engine/analytics/risk_metrics.py` (Lines 106-171)
- **Logical Flaw**: Daily NAV is computed strictly as the sum of the market values of active stock holdings. It completely ignores cash transactions (deposits, withdrawals, and stock sale cash proceeds).
- **Mathematical Proof of Distortion**:
  Suppose a user deposits ₹100,000 cash.
  - **Day 1**: Buys ₹10,000 of Stock A. Running Positions: `{Stock A: 10,000}`. Daily NAV = ₹10,000.
  - **Day 2**: Buys ₹40,000 of Stock B. Running Positions: `{Stock A: 10,000, Stock B: 40,000}`. Daily NAV = ₹50,000.
    $$\text{Day 2 Daily Return} = \frac{50,000 - 10,000}{10,000} = +400.0\% \quad \text{(Fake return spike)}$$
  - **Day 3**: Sells all of Stock A for ₹11,000. Running Positions: `{Stock B: 40,000}`. Daily NAV = ₹40,000.
    $$\text{Day 3 Daily Return} = \frac{40,000 - 50,000}{50,000} = -20.0\% \quad \text{(Fake return drop)}$$
  - **Day 4**: Sells all of Stock B for ₹40,000. Running Positions: `{}`. Daily NAV = 0.0.
    $$\text{Day 4 Daily Return} = \frac{0 - 40,000}{40,000} = -100.0\% \quad \text{(Fake -100% returns crash)}$$
  *Mathematical Impact*: Sharpe, Sortino, Alpha, Beta, and Max Drawdown calculations are mathematically invalid because they are calculated using these garbage daily returns.

#### Flaw 14: Risk Engine Regresses Unaligned Date Arrays
- **File**: `backend/engine/analytics/risk_metrics.py` (Lines 218-219)
- **Logical Flaw**: Alpha and Beta regression arrays are paired by list slice indices:
  ```python
  x = nifty_returns[:n]
  y = portfolio_returns[:n]
  ```
  The dates of the portfolio daily returns are not aligned with index calendar dates.
- **Proof of Failure / Impact**:
  If the portfolio returns array contains dates where the index was closed (or vice versa), the list slicing aligns mismatched dates. The regression calculates the correlation between Stock A on a Monday and Nifty Index on a Tuesday, producing incorrect Alpha and Beta metrics.

#### Flaw 15: Brinson-Fachler Return Exploded on Mid-Period Transactions
- **File**: `backend/engine/analytics/long_term_attribution.py` (Lines 238-245)
- **Logical Flaw**: The sector return $r_p^s$ is calculated by dividing `net_contrib` (the net daily sector value change) by `init_val` (the sector value at the beginning of the period).
- **Mathematical Proof of Distortion**:
  Suppose a user starts with 0.1 shares of Stock A valued at ₹200. On Day 5, the user buys ₹50,000 of Stock A. On Day 10, the value of Stock A increases to ₹51,000.
  $$\text{Sector Initial Value } (init\_val) = ₹200$$
  $$\text{Net Contribution } (net\_contrib) = ₹800$$
  $$\text{Calculated Sector Return } (r_p^s) = \frac{800}{200} = 4.0 = +400.0\%$$
  The sector return is reported as +400.0% instead of its actual return of ~2%. This breaks the Brinson Selection and Interaction effect equations, which scale with sector returns.

#### Flaw 16: Mismatch in Outlier Capping Constant Between Frontend UI Component and Unit Tests / Attestation
- **Files**: `frontend/components/portfolio/LongTermTab.tsx` (Lines 28-29) vs `frontend/components/portfolio/LongTermTab.test.ts` (Lines 36, 82, 124) vs `d:\Project Work\FinTrace\TEST_READY.md` (Lines 28-29, 34, 56)
- **Logical Flaw**: The frontend component `LongTermTab.tsx` caps positive returns at `2.0` (200% return), whereas the test cases in `LongTermTab.test.ts` and the documentation in `TEST_READY.md` expect and claim that positive returns are capped at `10.0` (1000% return).
- **Proof of Failure / Impact**:
  Because of this capping constant discrepancy, running `npm run test` fails 3 unit test cases (`TC3.2`, `TC6.1`, `TC6.5`), and the attestation that the test suite is fully passing in `TEST_READY.md` is false.

#### Flaw 17: Copilot Schema Mismatch on Empty Portfolio State
- **File**: `backend/engine/copilot/agent.py` (Lines 63-64)
- **Logical Flaw**: When a user's transaction ledger is empty, the Copilot engine fallback function `get_isolated_db` initializes the transaction database with a subset of columns, omitting crucial fields such as `execution_date` and `brokerage_fees`.
- **Proof of Failure / Impact**:
  Any natural language SQL query generated by the AI Copilot that references dates or fees will crash with database schema errors when executed against empty portfolios.

---

## Part 3: Actionable Recommendations & Proposed Fixes

### 1. Same-Day Transaction Sorting & Determinism
- **Fix**: Add a microsecond `created_at` timestamp or a sequential auto-incrementing ID to the transaction model schema. In `tax_engine.py` and `xirr_engine.py`, sort ledger queries by execution date first, then by creation date/ID:
  ```python
  transactions = self.db.query(TransactionLedger).filter(...).order_by(
      asc(TransactionLedger.execution_date),
      asc(TransactionLedger.created_at)
  ).all()
  ```

### 2. Transaction Checksum Normalization
- **Fix**: Normalize inputs to the hash function by converting the ticker to uppercase before checksum calculations:
  ```python
  def _generate_row_checksum(self, portfolio_id: str, row_data: dict) -> str:
      ticker = str(row_data.get('ticker', '')).strip().upper()
      raw_string = f"{portfolio_id}_{ticker}_{row_data.get('transaction_type')}_{row_data.get('quantity')}_{row_data.get('price_per_unit')}_{row_data.get('execution_date')}"
      return hashlib.sha256(raw_string.encode('utf-8')).hexdigest()
  ```

### 3. Support ISIN-to-Ticker Resolvers
- **Fix**: Introduce an `IsinTickerMap` database table and mapping service. During ledger ingestion, resolve statement ISIN codes (e.g., `INE002A01018`) to their corresponding ticker symbols (e.g., `RELIANCE.NS`) before persisting the transactions.

### 4. Support Bonus Corporate Actions
- **Fix**: Modify `LedgerValidator`, `FIFOTaxEngine`, and `XIRREngine` SQL queries to query corporate actions filtering for `action_type.in_(["SPLIT", "BONUS"])`. Adjust the multiplication logic: splits multiply quantity and divide price, while bonuses multiply quantity and leave price unchanged.

### 5. Asynchronous yfinance Thread Offloading
- **Fix**: Wrap synchronous yfinance network and info calls with `asyncio.to_thread` or FastAPI's `run_in_threadpool` to prevent blocking the event loop:
  ```python
  current_price = await run_in_threadpool(stock.fast_info.get, 'last_price')
  ```

### 6. Dynamic NSDL/CDSL CAS Column Headers Detection
- **Fix**: Instead of using static row length indexes in `pdf_parser.py`, scan row arrays for key headers (e.g., `"qty"`, `"price"`, `"brokerage"`) and map column indexes dynamically during parser execution.

### 7. Support Short Position Matching in the Tax Engine
- **Fix**: Implement a separate short position queue. If a sell transaction has no matching buy queue lots, place it in a `short_sell_queue`. Match future buy transactions (buys-to-cover) against these short lots. Ensure that the cost basis is set to the cover price to compute realized gains correctly.

### 8. Include Brokerage Fees in Tax Calculations
- **Fix**: Incorporate transaction costs into cost-basis math under Section 48 guidelines:
  $$\text{Adjusted Buy Price} = \text{Price} + \frac{\text{Brokerage Fee}}{\text{Quantity}}$$
  $$\text{Adjusted Sell Price} = \text{Price} - \frac{\text{Brokerage Fee}}{\text{Quantity}}$$

### 9. Mathematically Sound XIRR Price Fallbacks
- **Fix**: If fetching the latest price for an asset fails, fall back to the asset's FIFO cost basis or its last known historical price rather than defaulting to 0.0:
  ```python
  except ValueError:
      latest_price = last_known_price or cost_basis_per_unit
  ```

### 10. Correct NAV Calculation using Daily Cash Tracking
- **Fix**: Maintain a running daily cash balance alongside equity positions. Daily NAV must equal the sum of market value holdings plus the cash balance.
  ```python
  # Initial Cash Balance = 0.0
  # On DEPOSIT: Cash Balance += Amount
  # On WITHDRAWAL: Cash Balance -= Amount
  # On BUY: Cash Balance -= (Quantity * Price) + Brokerage
  # On SELL: Cash Balance += (Quantity * Price) - Brokerage
  # On DIVIDEND: Cash Balance += Amount
  # Daily NAV = Sum(Quantity * Current Price) + Cash Balance
  ```

### 11. Calendar Alignment for Regression Metrics
- **Fix**: Match portfolio daily returns and benchmark index returns by date using a pandas outer join, rather than using list slicing. Compute Alpha and Beta regressions using aligned calendar-date returns.

### 12. Correct Brinson-Fachler Mid-Period Returns
- **Fix**: Use Time-Weighted Return (TWR) daily linking or calculate a daily weighted average capital denominator (Dietz or Modified Dietz method) to handle mid-period additions and withdrawals without return inflation.

### 13. Align Frontend Outlier Capping Threshold
- **Fix**: Modify the capping condition in `LongTermTab.tsx` to match the intended design specification of 10.0 (1000% return):
  ```typescript
  if (displayXirr > 10.0) { displayXirr = 10.0; isCapped = true; }
  ```
  This resolves the capping mismatch, makes the Jest unit tests pass successfully, and validates the attestation claims in `TEST_READY.md`.

### 14. Define Explicit SQLite Schema Columns for Empty Portfolio Copilot State
- **Fix**: In `backend/engine/copilot/agent.py` line 64, initialize the SQLite fallback DataFrame with all required transaction database columns:
  ```python
  pd.DataFrame(columns=['id', 'portfolio_id', 'ticker', 'transaction_type', 'quantity', 'price_per_unit', 'execution_date', 'brokerage_fees', 'settlement_date', 'checksum']).to_sql('transactions', temp_engine, index=False)
  ```
  This guarantees that natural language queries referencing dates or transaction costs do not crash on empty portfolios.

---

### Conclusion

FinTrace contains critical logical and mathematical vulnerabilities that make its core analytics unreliable. Addressing these flaws via the recommended fixes will stabilize the ingestion pipelines, ensure accurate tax and performance reports, and secure the SQL copilot.
