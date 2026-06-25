# Final understanding of FinTrace

FinTrace has the potential to become a very strong GitHub project and a useful Indian portfolio-tax product. But the correct sequence is:

```text
Strong public engineering project
        ↓
Invite-only beta using known statement formats
        ↓
CA-reviewed tax working papers
        ↓
Public launch
        ↓
Monetization and advisor features
```

The product should be positioned as:

> **An auditable portfolio accounting and tax-analysis platform for Indian investors that converts broker statements into reconciled holdings, capital-gains working papers, performance analytics, and explainable reports.**

The most important word here is **auditable**. The AI Copilot, behavioural insights and attractive charts are secondary. Your real differentiation is proving exactly how every number was obtained.

I reviewed the current `main` branch and test/source files through GitHub. I could not execute the complete test suite in this environment, so the findings below are based on direct code inspection rather than a fresh local test run.

---

# 8. Two-day GitHub sprint

I am assuming roughly **24–30 combined developer-hours** for this sprint.

The objective is not to fix the whole financial platform. It is to make the repository:

* Honest
* Presentable
* Reproducible
* Technically credible
* Clearly scoped

## Day 1 — Correctness guardrails

### Developer 1: backend and financial integrity

#### Task 1: fix transaction identity and ordering

* Add `sequence_number`
* Populate it from source row order
* Sort tax/XIRR/validation by date plus sequence
* Normalize ticker before any fingerprint
* Remove the checksum design that rejects legitimate identical trades
* Add `import_batch_id` or a minimal equivalent

#### Task 2: fix validation chronology

* Build validator dates from the union of:

  * Transaction dates
  * Split dates
  * Bonus dates
* Reject unsupported corporate actions with explicit warnings rather than silently ignoring them

#### Task 3: short-sale guardrail

* Detect sell-before-buy
* Classify intraday short separately
* Exclude it from the capital-gains report
* Return a warning instead of producing an incorrect gain

#### Task 4: add six golden regression tests

1. Brokerage included in buy and sell
2. Split on a date without a transaction
3. `reliance.ns` and `RELIANCE.NS`
4. Two legitimate identical trades
5. Sell-before-buy ordering
6. Missing price produces a warning, not a fake valuation

### Developer 2: visible project quality

#### Task 1: remove obvious inconsistencies

* Fix the XIRR cap implementation/test mismatch
* Remove duplicated SQLAlchemy models
* Replace placeholder package descriptions
* Make frontend API base URL environment-driven
* Remove committed development secrets and unsafe fallbacks

#### Task 2: create basic CI

One GitHub Actions workflow:

```text
Backend:
- install
- lint
- pytest

Frontend:
- npm ci
- npm test
- npm run build
```

CI is currently absent from the public repository. ([GitHub][16])

---

## Day 2 — GitHub showcase release

### Developer 1

* Add a sanitized demo portfolio
* Generate one sample JSON report
* Generate one sample PDF/CSV tax working paper
* Add supported/unsupported transaction warnings to reports
* Add `calculation_version`
* Add `tax_rule_version`
* Add valuation timestamp and unresolved-price warnings
* Run and document all backend tests locally

### Developer 2

Create a strong root README containing:

1. Product screenshot/banner
2. One-line problem statement
3. Demo GIF or 60–90 second video
4. Features with status:

   * Stable
   * Beta
   * Experimental
5. Architecture diagram
6. Import flow
7. Financial-calculation flow
8. Supported broker formats
9. Local setup
10. Docker setup
11. Test commands
12. Sample API calls
13. Screenshots of tax report, dashboard and Copilot
14. Known limitations
15. Security and privacy notes
16. Roadmap
17. Disclaimer
18. Contribution guide

Also add:

* `CONTRIBUTING.md`
* `SECURITY.md`
* `LICENSE`
* `docs/architecture.md`
* `docs/calculation-methodology.md`
* `docs/supported-imports.md`
* Issue templates
* Pull-request template
* Repository description and topics

## Two-day release label

Use:

> **FinTrace v0.1 — Engineering Preview**

Do not call it filing-ready.

Recommended status table:

| Feature                  | Status            |
| ------------------------ | ----------------- |
| Delivery-equity FIFO     | Beta              |
| Equity ETF support       | Beta              |
| Mutual funds             | Experimental      |
| Intraday/short detection | Beta              |
| Short-sales tax report   | Not yet supported |
| XIRR                     | Beta              |
| Risk analytics           | Experimental      |
| Attribution              | Experimental      |
| Copilot                  | Experimental      |
| Tax PDF/CSV              | CA-review draft   |

---
