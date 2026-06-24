import csv
import io
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet


def _fmt(value) -> str:
    """Format a numeric/Decimal value as a 2-dp string with thousands separators."""
    return f"{float(value):,.2f}"


def create_tax_pdf(tax_data: dict, user_email: str) -> io.BytesIO:
    """
    Generate a CA-ready capital-gains PDF aligned to Schedule CG sections.

    Expects the dict returned by ``FIFOTaxEngine.compute_tax_report`` (with graceful
    fallback to the legacy ``compute_realized_gains`` shape).
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()

    # 1. Header
    elements.append(Paragraph("FinTrace Capital Gains Report", styles["Title"]))
    elements.append(Spacer(1, 12))
    elements.append(Paragraph(f"Prepared for: {user_email}", styles["Normal"]))
    elements.append(Paragraph("Accounting Method: Strict FIFO (Sec 111A / 112A, listed equity)", styles["Normal"]))
    elements.append(Spacer(1, 24))

    financial_years = tax_data.get("financial_years", [])

    # 2. Per-financial-year tax summary (Schedule CG style)
    if financial_years:
        elements.append(Paragraph("Capital Gains by Financial Year", styles["Heading2"]))
        elements.append(Spacer(1, 12))

        fy_header = [
            "FY", "STCG", "LTCG", "112A Exempt.", "STCG Tax", "LTCG Tax", "Total Tax",
        ]
        fy_rows = [fy_header]
        for fy in financial_years:
            fy_rows.append([
                fy["financial_year"],
                _fmt(fy["gross_stcg"]),
                _fmt(fy["gross_ltcg"]),
                _fmt(fy["ltcg_exemption_applied"]),
                _fmt(fy["stcg_tax"]),
                _fmt(fy["ltcg_tax"]),
                _fmt(fy["total_tax"]),
            ])
        fy_rows.append([
            "TOTAL", "", "", "", "", "", _fmt(tax_data.get("total_tax_payable", 0)),
        ])

        fy_table = Table(fy_rows, colWidths=[60, 75, 75, 75, 70, 70, 70])
        fy_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.darkblue),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 10),
            ("BACKGROUND", (0, -1), (-1, -1), colors.lightgrey),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ]))
        elements.append(fy_table)
        elements.append(Spacer(1, 24))
    else:
        # Legacy fallback (raw realized gains only).
        elements.append(Paragraph("Realized Capital Gains", styles["Heading2"]))
        elements.append(Spacer(1, 12))
        summary_data = [
            ["Tax Bracket", "Realized Profit (INR)"],
            ["Short-Term (STCG)", _fmt(tax_data.get("realized_stcg", 0))],
            ["Long-Term (LTCG)", _fmt(tax_data.get("realized_ltcg", 0))],
        ]
        summary_table = Table(summary_data, colWidths=[300, 150])
        summary_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.darkblue),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 1, colors.black),
        ]))
        elements.append(summary_table)
        elements.append(Spacer(1, 24))

    # 3. Lot-level realized detail
    lots = tax_data.get("realized_events", [])
    if lots:
        elements.append(Paragraph("Realized Lots (FIFO matched)", styles["Heading2"]))
        elements.append(Spacer(1, 12))
        lot_rows = [["Ticker", "Buy", "Sell", "Qty", "Cost", "Proceeds", "Gain", "Term"]]
        for e in lots:
            lot_rows.append([
                e["ticker"],
                str(e["buy_date"]),
                str(e["sell_date"]),
                f"{float(e['quantity']):,.2f}",
                _fmt(e["cost_basis"]),
                _fmt(e["proceeds"]),
                _fmt(e["gain"]),
                "LT" if e["is_long_term"] else "ST",
            ])
        lot_table = Table(lot_rows, colWidths=[70, 65, 65, 45, 70, 70, 70, 30])
        lot_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ]))
        elements.append(lot_table)
        elements.append(Spacer(1, 24))

    # 4. Unsold holdings
    elements.append(Paragraph("Current Unsold Holdings", styles["Heading2"]))
    elements.append(Spacer(1, 12))
    holdings_data = [["Asset Ticker", "Remaining Quantity"]]
    for ticker, qty in tax_data.get("current_holdings", {}).items():
        holdings_data.append([ticker, f"{float(qty):.4f}"])
    holdings_table = Table(holdings_data, colWidths=[250, 200])
    holdings_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 1, colors.black),
    ]))
    elements.append(holdings_table)

    elements.append(Spacer(1, 24))
    elements.append(Paragraph(
        "Disclaimer: Computed on listed-equity (STT-paid) assumptions under Sec 111A/112A. "
        "Verify with a tax professional before filing.",
        styles["Italic"],
    ))

    doc.build(elements)
    buffer.seek(0)
    return buffer


def create_tax_csv(tax_data: dict) -> io.BytesIO:
    """Export lot-level realized-gain rows as CSV for a CA / Schedule CG working."""
    text_buffer = io.StringIO()
    writer = csv.writer(text_buffer)
    writer.writerow([
        "Ticker", "Buy Date", "Sell Date", "Quantity", "Cost Basis (incl. fees)",
        "Net Proceeds", "Gain/Loss", "Term", "Grandfathered", "Financial Year",
    ])
    for e in tax_data.get("realized_events", []):
        writer.writerow([
            e["ticker"],
            e["buy_date"],
            e["sell_date"],
            f"{float(e['quantity']):.4f}",
            f"{float(e['cost_basis']):.2f}",
            f"{float(e['proceeds']):.2f}",
            f"{float(e['gain']):.2f}",
            "LT" if e["is_long_term"] else "ST",
            "Yes" if e.get("grandfathered") else "No",
            e.get("fy_label", ""),
        ])

    byte_buffer = io.BytesIO(text_buffer.getvalue().encode("utf-8"))
    byte_buffer.seek(0)
    return byte_buffer
