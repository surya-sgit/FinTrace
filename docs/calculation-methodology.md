# FinTrace Calculation Methodology

FinTrace strives for mathematical correctness and auditability. The following rules dictate how complex financial calculations are performed.

## 1. Capital Gains (FIFO)
Indian tax law mandates the **First-In, First-Out (FIFO)** accounting method for delivery equities and mutual funds.

- FinTrace sequentially applies sell quantities against the earliest available buy quantities.
- Intraday trades (buy and sell on the exact same date for the exact same equity) are isolated and excluded from delivery capital gains calculations.
- Short-sells (selling before buying) trigger validation warnings and halt the valuation to prevent corrupted tax baselines.

## 2. XIRR (Extended Internal Rate of Return)
Performance is calculated using XIRR, which accounts for the timing of cash flows.

- **Cash Outflows**: Buy transactions (price * quantity + fees).
- **Cash Inflows**: Sell transactions (price * quantity - fees) and Dividends.
- **Terminal Value**: The current valuation of remaining holdings is treated as a final inflow.
- **Fallback**: If market prices fail to resolve (missing ticker data), the terminal value falls back to the original Cost Basis, effectively yielding a 0% XIRR for the unresolved portion, rather than artificially inflating or deflating performance.

## 3. Corporate Actions (Splits and Bonuses)
Corporate actions fundamentally alter the identity and quantity of historical tax lots.

- When a split or bonus occurs, FinTrace iterates through the historical FIFO queue.
- Unsold quantities prior to the ex-date are multiplied by the split ratio.
- The original purchase price is proportionally diluted.
- The execution date of the original lot remains unchanged for long-term/short-term capital gains tax bucketing.

## 4. Sequence Numbering
Because many trades can happen on the same date (and broker CSVs often lack millisecond timestamps), FinTrace assigns a deterministic `sequence_number` to every transaction based on its row order in the imported statement. This guarantees that tie-breakers in FIFO matching are consistent across multiple recalculations.
