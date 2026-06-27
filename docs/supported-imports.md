# Supported Data Imports

FinTrace's ingestion engine is designed to parse tabular transaction logs from major Indian brokerages.

## 1. Zerodha (Console)
We support the Zerodha "Tradebook" CSV format.

**How to export**:
1. Log into Zerodha Console.
2. Navigate to Reports -> Tradebook.
3. Select the desired date range and download the CSV.

**Caveats**:
- Zerodha often aggregates intraday trades. FinTrace detects these and marks them with an `intraday` tag.
- Brokerage fees are included natively in the row data.

## 2. Groww
We support the Groww "Transactions" PDF and CSV formats via `pdfplumber` and `pandas`.

**How to export**:
1. Log into Groww Web.
2. Navigate to your profile -> Reports.
3. Request the "Stocks Transaction Report".

## 3. Standard Custom CSV
For other brokers, you can manually format your trades into the FinTrace Standard CSV format.

**Required Columns**:
- `date`: Execution date (YYYY-MM-DD)
- `transaction_type`: `BUY` or `SELL`
- `ticker`: NSE/BSE ticker symbol (e.g., `RELIANCE.NS`)
- `quantity`: Number of shares
- `price`: Execution price per share

**Optional Columns**:
- `brokerage_fees`: Associated transaction costs
- `settlement_date`: Trade settlement date (defaults to T+1)
