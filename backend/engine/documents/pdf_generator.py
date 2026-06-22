import io
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

def create_tax_pdf(tax_data: dict, user_email: str) -> io.BytesIO:
    """
    Generates a formatted PDF report in-memory using ReportLab.
    """
    # Create an in-memory byte buffer instead of writing to disk
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()

    # 1. Document Header
    elements.append(Paragraph("FinTrace Tax Liability Report", styles['Title']))
    elements.append(Spacer(1, 12))
    elements.append(Paragraph(f"Prepared for: {user_email}", styles['Normal']))
    elements.append(Paragraph("Accounting Method: Strict FIFO", styles['Normal']))
    elements.append(Spacer(1, 24))

    # 2. Capital Gains Summary Table
    elements.append(Paragraph("Realized Capital Gains", styles['Heading2']))
    elements.append(Spacer(1, 12))

    summary_data = [
        ["Tax Bracket", "Realized Profit (INR)"],
        ["Short-Term (STCG) < 365 Days", f"{tax_data['realized_stcg']:,.2f}"],
        ["Long-Term (LTCG) >= 365 Days", f"{tax_data['realized_ltcg']:,.2f}"]
    ]

    summary_table = Table(summary_data, colWidths=[300, 150])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.darkblue),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('ALIGN', (1,0), (1,-1), 'RIGHT'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0,0), (-1,0), 12),
        ('BACKGROUND', (0,1), (-1,-1), colors.whitesmoke),
        ('GRID', (0,0), (-1,-1), 1, colors.black)
    ]))

    elements.append(summary_table)
    elements.append(Spacer(1, 24))

    # 3. Unsold Inventory Table
    elements.append(Paragraph("Current Unsold Holdings", styles['Heading2']))
    elements.append(Spacer(1, 12))

    holdings_data = [["Asset Ticker", "Remaining Quantity"]]
    for ticker, qty in tax_data['current_holdings'].items():
        holdings_data.append([ticker, f"{qty:.4f}"])

    holdings_table = Table(holdings_data, colWidths=[250, 200])
    holdings_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.grey),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('ALIGN', (1,0), (1,-1), 'RIGHT'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0,0), (-1,0), 12),
        ('GRID', (0,0), (-1,-1), 1, colors.black)
    ]))

    elements.append(holdings_table)

    # 4. Build and return the buffer
    doc.build(elements)
    buffer.seek(0)
    return buffer
