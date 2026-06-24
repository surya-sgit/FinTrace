# FinTrace — Product & Technical Strategy

> A single source of truth for what FinTrace is today, who it can serve, how the data
> model and ingestion should evolve, what automation is possible, where we're lacking,
> and exactly what is required to monetize it.
>
> Last updated: 2026-06-24. Owner: product + engineering.

---

## 0. TL;DR

FinTrace is a **quantitative portfolio analytics + tax engine for Indian investors**.
The hard, differentiated part — the math (FIFO capital-gains tax across equity and all
mutual-fund types, XIRR, attribution, behavioral analytics, risk metrics) — is built and
tested. The weak parts are the unglamorous-but-mandatory layers around it: **frictionless
data ingestion, deployment/security hardening, billing, and the multi-user/advisor data
model**.

**Recommended wedge:** the **long-term, multi-asset Indian retail investor** (stocks +
mutual funds) who dreads tax season — land them with a *file-ready capital-gains report*
and an *honest performance scorecard*, then expand up-market to **CAs / RIAs (B2B)** who
feel the same pain at 10–100× intensity.

---

## 1. What We Have Today (Current State)

### 1.1 Architecture

```
Frontend (Next.js 16 / React 19 / Tailwind / Recharts)
        │  Axios + JWT (Bearer, localStorage)
        ▼
Backend (FastAPI / Python 3.14 / Uvicorn)
  ├── api/routers        auth, portfolios, transactions, reports, analytics, copilot
  ├── domain             SQLAlchemy models, Pydantic schemas, transaction_service
  ├── engine
  │    ├── math_core     tax_engine (FIFO), tax_rules, xirr_engine, consolidation_engine
  │    ├── analytics     attribution (Brinson-Fachler), behavioral, risk_metrics
  │    ├── market_data   market_service (yfinance), amfi_service (MF NAV), corporate_actions, live_pricing
  │    ├── ingestion     csv_parser, pdf_parser (CAS), factory, ledger_validator, fund_classifier
  │    ├── documents     pdf_generator (+ CSV export)
  │    └── copilot       LangChain text-to-SQL agent
  └── db / alembic       PostgreSQL (prod) / SQLite (tests), migrations
```

### 1.2 Capabilities that exist and are tested

| Domain | What works |
|---|---|
| **Auth** | Register/login, JWT (HS256), bcrypt password hashing, per-user tenant isolation on every query |
| **Portfolios** | Create / list / get / **delete** (cascades ledger + snapshots) |
| **Ingestion** | CSV (Zerodha, Groww stocks, Upstox, AngelOne, FinTrace template, **Groww MF order history**), CAS PDF (NSDL/CDSL), checksum idempotency, ledger integrity validation |
| **Capital-gains tax** | FIFO across **equity (Sec 111A/112A)** with grandfathering (31-Jan-2018), ₹1.25L LTCG exemption, current 12.5%/20% rates, loss set-off + 8-yr carry-forward; **all MF types** — equity-MF (=equity), **debt (Sec 50AA slab)**, **hybrid/other (24-mo / 36-mo, 12.5%)**; slab-taxable gains reported separately |
| **Dividends** | **Auto-derived** from public corporate-action data (`yfinance.dividends` → holdings × per-share), no manual entry |
| **Performance** | XIRR (pyxirr), per-holding valued breakdown, valuation history |
| **Attribution** | Brinson-Fachler (allocation/selection/interaction), sector metadata from yfinance |
| **Behavioral** | Disposition effect, momentum bias, revenge trades, panic sells, endowment trap, churn, win rate |
| **Risk** | Alpha, Beta vs NIFTY, Sharpe, Sortino, max drawdown, volatility |
| **Market data** | yfinance (equities) + Alpha Vantage (fallback) + **AMFI NAV (mutual funds, by ISIN or scheme name)**; scheduled refresh (APScheduler, 15:45 IST) routed by asset class |
| **Consolidation** | Cross-portfolio net worth, blended XIRR, **Equity vs Mutual-Fund split** |
| **Reports** | Tax report JSON + **Schedule-CG-style PDF** + **CSV** export |
| **Copilot** | Natural-language → SQL over the user's own data, GPT-4o-mini, isolated SQLite per query |
| **Reporting UI** | Dashboard with consolidation card, per-portfolio Overview/Short-term/Long-term/Behavioral tabs, market-value asset-allocation tile, per-FY tax table |

### 1.3 Honest tech-debt / known issues

- `domain/models.py` contains **two stacked copies** of the model definitions (the second `Base`/class set shadows the first). Works, but must be de-duplicated.
- **Security defaults are unsafe** (see §7): fallback `SECRET_KEY`, DB password in `docker-compose.yml`, demo API keys, JWT in `localStorage`.
- **No backend Dockerfile, no CI, no observability.**
- APScheduler runs **in-process** (won't survive multiple workers cleanly).
- AMFI name→NAV matching is **heuristic** (no ISIN captured from Groww MF exports yet).
- One pre-existing failing test (`test_startup.py`, async config) unrelated to features.

---

## 2. Target Users (Personas) & Fit

| Persona | Who | Pain | Fit today | Effort to win |
|---|---|---|---|---|
| **P1 — Long-term equity investor** | Buy-and-hold stock investors | Tax computation, "am I any good?" | **Strong** | Low (done) |
| **P2 — Multi-asset retail** | Stocks **+ mutual funds** (most retail) | Consolidated view, MF tax, manual entry | **Good** (this session) | Medium (broker auto-sync, NAV polish) |
| **P3 — Active / F&O / intraday traders** | High-frequency, derivatives | Real-time P&L, business-income tax, journaling | **Poor** | High (realtime data + different tax + journal) — separate product |
| **P4 — CAs / RIAs / wealth managers (B2B)** | Manage many client portfolios | Bulk tax reports, white-label, client mgmt | **Weak** (no multi-tenant) | Medium-High, **highest ARPU** |
| **P5 — HNIs / family offices** | Large, multi-account, multi-entity | Consolidation across entities, audit, bespoke reports | **Weak** | High |

**Strategy:** **P1 → P2 (front door, B2C)**, then **P4 (profit engine, B2B)**. Defer P3
(distinct product) and P5 (after B2B proven). Design the schema now so P4/P5 are
additive, not a rewrite (see §3).

### 2.1 Per-persona feature design

**P1 — Long-term equity investor**
- ✅ File-ready capital-gains PDF/CSV (Schedule CG), XIRR vs benchmark, behavioral nudges.
- ➕ ITR-ready export mapped to actual ITR schedules; tax-loss-harvesting suggestions; LTCG-threshold alerts.

**P2 — Multi-asset retail**
- ✅ MF tax (all types), consolidation, Equity/MF split, Groww MF import.
- ➕ Broker/AMC **auto-sync** (the #1 conversion driver), goal & SIP tracking, asset-allocation drift alerts, net-worth trend over time.

**P3 — Active/F&O traders** (separate track)
- F&O & intraday P&L, speculative/business-income tax (not capital gains), turnover & tax-audit thresholds (44AB), trade journal, real-time/intraday data, R-multiple & win-rate analytics.

**P4 — CAs / RIAs (B2B)**
- Organization accounts, **manage-many-clients dashboard**, bulk import, **white-labeled** branded reports, client-shareable **read-only** links, bulk tax-season report generation, role-based access (admin/staff/read-only), audit trail per client.

**P5 — HNIs / family offices**
- Multi-entity consolidation (self + HUF + family), custom asset classes (real estate, PMS, AIF, bonds, FDs), document vault, accountant collaboration, bespoke periodic reports.

---

## 3. User-Based Schema Design

Today: `User → Portfolio → TransactionLedger (+ snapshots)`. Single flat user. To support
tiers, advisors, and orgs **without rework**, evolve to:

### 3.1 Target entity model

```
Organization (id, name, type[INDIVIDUAL|ADVISORY|FAMILY_OFFICE], created_at)
   └── Membership (org_id, user_id, role[OWNER|ADMIN|STAFF|READ_ONLY], status)
User (id, email, hashed_password, full_name, phone, pan_hash, created_at,
      email_verified, mfa_enabled, marginal_tax_slab?, default_org_id)
Subscription (id, org_id, plan[FREE|PRO|ADVISOR|ENTERPRISE], status,
              billing_cycle, current_period_end, seats, provider_customer_id,
              provider_subscription_id)
UsageCounter (id, org_id, metric[COPILOT_QUERIES|PORTFOLIOS|REPORTS], period, count)
Client (id, org_id, display_name, pan_hash, owner_user_id)   # advisor's client
Portfolio (id, owner_type[USER|CLIENT], owner_id, org_id, name, tax_jurisdiction, ...)
TransactionLedger (… existing … + asset_class, source[CSV|PDF|API|AA|MANUAL], source_ref)
AuditLog (id, org_id, actor_user_id, action, target, diff, created_at, ip, user_agent)
FeatureFlag / Entitlement (plan → capability map; or computed from Subscription.plan)
```

### 3.2 Key design decisions

- **Org as the tenant boundary**, not user. A solo retail user silently gets a personal
  org of one. An advisor's org has many members + many `Client`s. Every query filters by
  `org_id` (+ role check) instead of `user_id`. This is the single most important change
  to enable B2B later without a migration.
- **`Portfolio.owner_type/owner_id`** lets a portfolio belong to a `User` (B2C) or a
  `Client` (advisor-managed) uniformly — engines don't change.
- **Entitlements derived from `Subscription.plan`** gate features centrally (a FastAPI
  dependency `require_entitlement("mf_tax")`), so paywalls live in one place.
- **PII minimization**: store **PAN as a salted hash** (for dedup/matching), never plain;
  encrypt-at-rest for any retained raw statements (DPDP Act, §10).
- **`source` on every ledger row** for provenance (manual vs API vs AA) — critical for
  trust, reconciliation, and "why is this number what it is?".

### 3.3 Migration path (non-breaking, staged)

1. Add `Organization`, `Membership`, auto-create a personal org per existing user; add
   `org_id` (nullable → backfill → not-null) to `Portfolio`.
2. Add `Subscription` (everyone starts FREE), `UsageCounter`, `Entitlement` checks.
3. Add `Client` + `Portfolio.owner_type/owner_id` when B2B work starts.
4. De-duplicate `models.py`; add `source`/`source_ref` to `TransactionLedger`.

---

## 4. Data Ingestion — Options, Gaps, Implementation

Ingestion friction is the **#1 driver of activation and conversion**. Manual CSV upload is
the biggest drop-off.

### 4.1 What exists

- **CSV**: Zerodha, Groww (stocks), Upstox, AngelOne, FinTrace template, **Groww MF order
  history** (preamble-aware, PURCHASE/REDEEM mapping, scheme-name identifiers).
- **CAS PDF**: NSDL/CDSL consolidated account statement (equities + MFs by ISIN).
- Idempotency via SHA-256 checksum; ledger integrity validation (no negative EOD holdings).

### 4.2 The full option space (best UX → most effort)

| Source | Coverage | Effort | Notes / risk |
|---|---|---|---|
| **Account Aggregator (AA) framework** | Bank + depository + MF, RBI-sanctioned, consent-based | High (regulated, needs FIU/TSP partner) | The strategically correct long-term answer in India; auto, fresh, legal |
| **CAS via email auto-fetch** | All holdings monthly (CDSL/NSDL/CAMS-KFintech) | Medium | Parse the CAS PDF users already receive; "forward your CAS" or IMAP integration |
| **CAMS / KFintech MF statements** | All MFs across AMCs | Medium | Official mailback/portal; ISIN + scheme code + transactions |
| **Broker APIs** (Zerodha Kite, Upstox, Angel SmartAPI, Groww) | Per-broker trades/holdings | Medium per broker | OAuth per broker; rate limits; trade vs holding endpoints differ |
| **Improved CSV/Excel mapping UI** | Anything | Low | Column-mapping wizard for unknown formats; preview before commit |
| **Manual entry / quick-add** | Anything | Low | Already implied; needs a clean UI form |

### 4.3 Where we're lacking & how to fix

- **No broker auto-sync** → build official-API connectors (start: Zerodha Kite + Upstox).
  Store `source=API`, schedule incremental pulls.
- **Groww MF gives scheme name, not ISIN** → today resolved heuristically to NAV. Fix:
  also capture ISIN when present; build a persistent **scheme master** table
  (ISIN ↔ scheme code ↔ name ↔ category from AMFI) and fuzzy-match once, then cache the
  mapping so it's deterministic thereafter.
- **No mapping UI for unknown CSVs** → a generic column-mapper would let users import any
  broker without us hard-coding it.
- **CAS coverage not validated end-to-end** → add golden-file tests for real NSDL/CDSL
  layouts; handle locked PDFs (password) robustly.
- **No reconciliation** → after import, reconcile computed holdings vs the statement's
  stated holdings and flag mismatches (huge trust win).

### 4.4 Recommended ingestion roadmap

1. **Scheme master table + ISIN capture** (deterministic MF identity & pricing).
2. **CAS-by-email** ("forward your statement") — broadest coverage, low integration cost.
3. **Generic CSV mapping wizard** + import preview + reconciliation report.
4. **Broker APIs** (Kite, Upstox) for power users.
5. **Account Aggregator** once a regulated partner is in place (long-term moat).

---

## 5. Automation

Automation is what turns a "calculator you visit" into a "service that works for you".

### 5.1 What exists
- Scheduled **market-data / NAV refresh** (APScheduler, Mon–Fri 15:45 IST), routed
  equities→yfinance, MFs→AMFI.
- **Auto corporate actions** (splits) and **auto dividends** on upload.
- Background behavioral-analytics computation after upload.

### 5.2 What should be automated next

| Automation | Value | Notes |
|---|---|---|
| **Daily NAV/price + holdings snapshot** | Net-worth trend, fresh dashboards | Move scheduler **out of process** (Celery/RQ/Arq + Redis beat) before scaling workers |
| **Corporate-action sweep** (bonus, rights, mergers) | Correct cost basis | Extend `corporate_actions` beyond splits/dividends |
| **Tax-season report generation** (bulk, for advisors) | Core B2B value | Queue per-client PDF/CSV generation |
| **Alerts/notifications** | Retention + daily actives | LTCG-threshold crossings, tax-harvesting windows, behavioral nudges, large drawdowns, SIP due |
| **Scheduled email digests** | Re-engagement | Weekly/monthly performance + tax-liability-to-date |
| **Reconciliation jobs** | Trust | Compare computed vs statement holdings, flag drift |
| **Data-freshness monitors** | Reliability | Alert when yfinance/AMFI feeds break (they will) |

### 5.3 Required platform change
Replace **in-process APScheduler + FastAPI BackgroundTasks** with a **real task queue**
(Celery/RQ/Arq + Redis). Current background work silently swallows errors and won't
survive multiple workers — unacceptable once paying users rely on it.

---

## 6. Where We're Lacking (Gap Register)

| Area | Gap | Severity |
|---|---|---|
| **Security** | Fallback `SECRET_KEY`; DB password & demo API keys in repo; JWT in `localStorage` (XSS); no rate limiting; no upload size/type limits; no token refresh; copilot prompt-injection surface | **Critical** |
| **Deployability** | No backend Dockerfile; no reverse proxy/TLS; no CI/CD; secrets not externalized | High |
| **Observability** | No structured logging, error tracking (Sentry), metrics, or audit of feed health | High |
| **Reliability** | In-process scheduler; background errors swallowed; yfinance scraping fragility (single point of failure) | High |
| **Data integrity** | `models.py` duplication; heuristic MF name matching; no reconciliation; no scheme master | Medium |
| **Tax completeness** | Pre-2024 debt indexation (CII) out of scope; no F&O/intraday/other-income; cross-head loss set-off simplified | Medium |
| **Multi-user** | No roles, orgs, advisor mode, or entitlements | Medium (blocks B2B) |
| **Compliance/legal** | No T&C/privacy policy; "not investment advice" disclaimers; DPDP Act handling; SEBI RIA boundaries; GST invoicing | **Critical for monetization** |
| **Testing** | Thin frontend tests; no E2E; tax math needs property-based coverage | Medium |
| **UX** | No onboarding flow; manual-upload friction; no empty/error states polish | Medium |

---

## 7. Production-Readiness Checklist (must-do before paid users)

**Security**
- [ ] Fail-fast on missing `SECRET_KEY`/`DATABASE_URL`; remove all hardcoded fallbacks/keys.
- [ ] Secrets via env/secret manager; rotate the committed DB password & API keys.
- [ ] Move JWT to **httpOnly + SameSite cookie** (or strict CSP) + **refresh tokens**.
- [ ] **Rate limiting** (slowapi) on auth, upload, copilot; **upload size/type limits**.
- [ ] Copilot: enforce **read-only SQL**, validate output, cap rows, per-user quota.
- [ ] HTTPS/TLS termination; security headers; CORS allowlist by env.

**Reliability & Ops**
- [ ] Backend **Dockerfile** + full `docker-compose` (api + frontend + db + redis + proxy).
- [ ] **CI** (run pytest + jest + lint on PRs); fix the async `test_startup`.
- [ ] **Sentry** + structured logging; health/readiness probes.
- [ ] **External task queue** (Celery/RQ/Arq + Redis) for jobs & schedules.
- [ ] DB backups + migration runbook; resilient market-data with cached fallback.

**Correctness / Trust**
- [ ] Property-based + golden tests for tax/XIRR (splits, bonus, multi-broker, grandfathering).
- [ ] Post-import **reconciliation** vs statement holdings.
- [ ] De-duplicate `models.py`.

**Legal / Compliance (India)**
- [ ] Terms of Service, Privacy Policy, **"not investment/tax advice"** disclaimer everywhere numbers appear.
- [ ] **DPDP Act 2023** compliance: consent, data minimization, encryption at rest, deletion/export (data-principal rights), breach process.
- [ ] PAN/PII handling: store hashed, encrypt raw statements, retention policy.
- [ ] Clarify **SEBI RIA** boundary — analytics/reporting is fine; *recommendations* (buy/sell, harvesting advice) may trigger RIA registration. Keep features descriptive, not prescriptive, until cleared.
- [ ] **GST-compliant invoicing**; refund policy.

---

## 8. Monetization — What Strictly Needs to Be Done

### 8.1 Packaging & pricing (illustrative, INR)

| Plan | Target | Price | Includes |
|---|---|---|---|
| **Free** | P1/P2 acquisition | ₹0 | 1 portfolio, manual/CSV import, XIRR + basic tax summary |
| **Pro** | P1/P2 | ₹499–999/mo or ₹2,999–4,999/yr | Unlimited portfolios, full MF + equity tax, attribution + behavioral + risk, PDF/CSV tax reports, copilot (quota), consolidation, alerts |
| **Tax-Season Pass** | P1/P2 seasonal | one-time (Dec–Jul) | Full tax reports for the filing window; upsell to annual |
| **Advisor** | P4 | ₹3k–15k/mo (per-seat or per-client tier) | Multi-client dashboard, bulk import, white-label branded reports, client read-only links, priority data |
| **Enterprise / Family Office** | P5 | custom | Multi-entity, custom asset classes, SSO, SLA, bespoke reports |

**Usage-metered add-ons:** copilot LLM queries (protects margin — LLM calls cost real
money), premium/real-time data, extra seats/clients.

### 8.2 What must be built to charge money

1. **Subscription & entitlement system** (§3): plans, status, seats, `require_entitlement`
   dependency gating every paid feature server-side (never trust the client).
2. **Billing integration**: **Razorpay** (India-first; UPI/cards/netbanking, subscriptions,
   GST invoices) — Stripe for international later. Webhooks → update `Subscription`.
3. **Usage metering**: `UsageCounter` for copilot queries / portfolios / reports; enforce
   limits and overage.
4. **Paywall UX**: upgrade prompts, plan comparison, in-app checkout, billing portal,
   dunning (failed-payment recovery).
5. **Feature flags** to ship/gate progressively and run pricing experiments.
6. **The conversion-driving features themselves** (otherwise nothing is worth paying for):
   - **Broker/CAS auto-sync** (kills the onboarding cliff) — gate richer sync behind Pro.
   - **Branded, ITR/Schedule-CG-ready PDF** — the thing people pay for Mar–Jul.
   - **Consolidation + alerts** — daily-active retention.
   - **Advisor multi-client mode** — the high-ARPU B2B unlock.
7. **Legal/compliance prerequisites** from §7 (you cannot bill without ToS, privacy, GST,
   and the "not advice" disclaimer).

### 8.3 Funnel & metrics to instrument
- Activation: % who import ≥1 portfolio; time-to-first-tax-report.
- Conversion: free→paid, tax-season-pass→annual.
- Retention: monthly active, alert-driven returns, churn.
- Margin: LLM cost per active user (copilot), data-feed cost.
- B2B: clients-per-advisor, reports generated per season.

---

## 9. Phased Roadmap

| Phase | Theme | Outcome |
|---|---|---|
| **0** | **Production hardening** (§7 security/ops) | Safe to put real users on it |
| **1** | **Trust the math** (property/golden tax tests, reconciliation, de-dup models) | Numbers people can file with |
| **2** | **Kill ingestion friction** (scheme master + ISIN, CAS-by-email, CSV wizard, then broker APIs) | High activation |
| **3** | **Monetization plumbing** (orgs/roles, subscriptions, Razorpay, metering, paywalls, legal) | Revenue on |
| **4** | **Stickiness** (alerts, digests, consolidation trends, branded reports) | Retention |
| **5** | **B2B advisor mode** (clients, white-label, read-only links, bulk reports) | High ARPU |
| **6** | **Scale & reliability** (task queue, resilient feeds, observability at depth) | Durable |
| **Later** | Account Aggregator; F&O/trader product; US/multi-jurisdiction; family office | Expansion |

---

## 10. Compliance & Risk Notes (India)

- **Not advice:** Position FinTrace as *analytics & tax reporting*, not investment advice,
  to stay clear of SEBI **RIA** registration. Any "harvest this loss / sell this" feature
  needs legal review first.
- **DPDP Act 2023:** consent, purpose limitation, data minimization, security safeguards,
  data-principal rights (access/correction/erasure), breach notification.
- **Financial data sensitivity:** encrypt raw statements at rest; hash PAN; strict access
  logging (`AuditLog`); least-privilege.
- **Tax-figure liability:** prominent disclaimers; "verify with a CA"; versioned
  `CalculationEngine` for auditability (already modeled).
- **Account Aggregator:** if pursued, requires partnering with a licensed AA/FIU-TSP and
  following ReBIT specs.

---

## 11. Appendix

### 11.1 Current API surface (v1)
`/auth/register`, `/auth/login` · `/portfolios` (POST/GET/GET{id}/**DELETE{id}**/**GET consolidated**) ·
`/portfolios/{id}/upload` · `/portfolios/{id}/tax-report` (+ `/pdf`, `/csv`) ·
`/portfolios/{id}/xirr-report` · `/analytics/{id}/{attribution|long-term-attribution|behavioral|risk-metrics}` ·
`/copilot/chat` · `/health`

### 11.2 Tax rules implemented (see `engine/math_core/tax_rules.py`)
- Equity & equity-MF: STCG 15%/20% (cutoff 23-Jul-2024), LTCG 10%/12.5% over ₹1L/₹1.25L,
  >12-month long-term, Sec 112A grandfathering (FMV 31-Jan-2018).
- Debt MF ≥1-Apr-2023: Sec 50AA slab (reported, not rupee-computed).
- Debt MF pre-2023: LTCG (>36 mo) @12.5%.
- Hybrid/other: >24 mo (post-2023) / >36 mo (legacy) @12.5%, else slab.
- Loss set-off + 8-year carry-forward (equity and non-equity pools kept separate — a
  documented simplification).

### 11.3 Decisions already taken this cycle
- Market: **Indian retail first (P1→P2), B2B advisor next (P4)**.
- MF scope: **all fund types**; slab gains **reported, not rupee-computed**.
- MF data: **AMFI** (NAV + scheme category), name-matched for Groww.
- Asset allocation: **by market value** (not units).

### 11.4 Immediate next actions (recommended)
1. Phase 0 security/ops hardening (highest risk, blocks everything).
2. Scheme master + ISIN capture (deterministic MF identity/pricing).
3. Org/Subscription schema + Razorpay + entitlements (turn revenue on).
