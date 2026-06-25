# FinTrace E2E Testing Infrastructure

This document details the test framework configurations, mocking strategies, and integration design for validating the FinTrace Long-Term Value Analytics engine.

---

## 1. Testing Frameworks & Setup

### 1.1 Backend E2E Test Infrastructure
- **Framework**: `pytest`
- **Database**: SQLite in-memory database (`sqlite:///:memory:`). PostgreSQL-specific types such as `JSONB` are dynamically compiled to SQLite `JSON` using SQLAlchemy hooks for fast execution and zero dependency.
- **State Isolation**: Transaction-level isolation using nested database transactions (`session.begin_nested()`). Every test runs in its own transaction sandbox which is automatically rolled back on teardown, preventing cross-test pollution.

### 1.2 Frontend E2E Test Infrastructure
- **Framework**: `Jest` + `ts-jest`
- **Environment**: Node.js environment
- **Mocking**: Custom mock data passed directly to props and pure functions for predictable, offline, fast execution without requiring external dependencies or network traffic.

---

## 2. Infrastructure Architecture & Integration flow

### 2.1 Dynamic Ingestion & Database Caching (R1)
1. **Trigger**: Transaction statements (e.g. CSV ledger) are uploaded.
2. **Resolution**: For each unique stock ticker, the uploader verifies if it has sector metadata cached in the `AssetMetadata` table.
3. **yfinance Mocking**: If not cached, it queries `yfinance` to resolve macroeconomic sector and industry.
4. **Casing Normalization**: Casing is normalized (e.g., `" TECHNOLOGY "` -> `"Technology"`) and stored.
5. **Caching**: Saved in `AssetMetadata` for immediate and future reuse. Subsequent uploads skip the `yfinance` lookup.

### 2.2 Dynamic Brinson-Fachler Decomposition (R2)
1. **Input**: Initial holding values on `start_date`, terminal holding values on `end_date`, and transaction cash flows during the period.
2. **Sector Grouping**: Aggregates holding values dynamically by sector using cached database records.
3. **Benchmark Matching**: Queries weights and returns from the `BenchmarkIndex` table closest to the `end_date`.
4. **Attribution Math**: Computes allocation, selection, and interaction effects for each sector:
   - **Allocation Effect**: $(w_p^s - w_b^s) \times (r_b^s - R_b)$
   - **Selection Effect**: $w_b^s \times (r_p^s - r_b^s)$
   - **Interaction Effect**: $(w_p^s - w_b^s) \times (r_p^s - r_b^s)$
5. **Guardrails**: Zero-initial portfolio value, missing benchmark sectors, and zero benchmark returns are handled gracefully to prevent division by zero or index out of bounds.

### 2.3 Frontend Outlier Filtering & Capping (R3)
- **Data Capping**: Frontend `processMwrSlicing` maps incoming standalone XIRR values, visually capping them at:
  - Upper cap: `10.0` (1000% XIRR)
  - Lower cap: `-1.0` (-100% XIRR)
- **Capped Indicator**: Tooltips show the uncapped original value alongside a `(Capped)` indicator for capped values.
- **Sorting**: Assets are sorted by their original un-capped XIRR values first, preserving chronological performance order even under severe visual distortion.
- **NaN/Null handling**: Skips items with NaN, null, or undefined values gracefully.

---

## 3. Integration Coverage Matrix (4 Tiers)

| Tier | Test Case | Target Checked | Verification |
|---|---|---|---|
| **Tier 1** | `test_r1_dynamic_sector_metadata_ingestion` | yfinance query, DB caching & reuse | Instantiation count & sector resolution |
| **Tier 1** | `test_r2_dynamic_brinson_fachler` | Allocation, Selection, and Interaction effects | Exact match against mathematical expectations |
| **Tier 1** | `TC3.1` (Frontend Normal rendering) | `processMwrSlicing` with normal return | Data untouched, correct sorting |
| **Tier 1** | `TC3.2` / `TC3.3` (Frontend Capping) | Extreme positive / negative values | Values capped at 10.0 and -1.0 |
| **Tier 2** | `test_bf_missing_benchmark_sector` | Missing benchmark sectors | Fallback to 0.0 without crash |
| **Tier 2** | `test_bf_zero_initial_value` | Zero start value (bought mid-period) | Dynamic denominator using cash flows |
| **Tier 2** | `test_bf_zero_benchmark_return` | Zero benchmark return | Perfect subtraction math, no crash |
| **Tier 2** | `test_bf_negative_quantities` | Short positions / negative weights | Weights computed correctly |
| **Tier 2** | `test_bf_missing_sector_mapping` | Asset without DB metadata cached | Falls back to "Unknown" sector attribution |
| **Tier 2** | `TC6.1` (Limit Boundaries) | Boundary exact values (10.0, -1.0) | Retained as-is, not over-capped |
| **Tier 2** | `TC6.3` (Frontend NaN/Null Values) | NaN, null, or undefined values | Filtered out from rendering |
| **Tier 2** | `TC6.4` (Frontend Close to Zero) | Extremely small non-zero returns | Renders correctly without filtering |
| **Tier 2** | `TC6.5` (Frontend All Outliers) | All values > 1000% | All values capped, axes scaled correctly |

---

## 4. How to Execute Tests

### 4.1 Running Backend Tests
Ensure Python dependencies are installed via Poetry:
```bash
poetry run pytest backend/tests/test_e2e_attribution.py
```
To run the full backend test suite:
```bash
poetry run pytest backend/tests
```

### 4.2 Running Frontend Tests
Ensure Frontend dependencies are installed:
```bash
npm run test
```
To run Jest directly:
```bash
npx jest
```
