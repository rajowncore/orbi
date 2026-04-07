"""
Orbi — Invoice PDF Generation

Uses Jinja2 to render an HTML invoice template,
then WeasyPrint to convert it to PDF.
Falls back gracefully if WeasyPrint is not installed.
"""
from __future__ import annotations
import os
import uuid
from datetime import datetime
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import Invoice, InvoiceLineItem, Customer

# PDF output directory
PDF_DIR = Path(__file__).parent.parent.parent / "pdfs"
PDF_DIR.mkdir(exist_ok=True)

# HTML template (inline — no separate file needed for MVP)
INVOICE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: Arial, sans-serif; font-size: 13px; color: #1E293B; padding: 40px; }
  .header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 40px; }
  .logo { font-size: 24px; font-weight: 700; color: #1B4FD8; }
  .logo-sub { font-size: 11px; color: #94A3B8; text-transform: uppercase; letter-spacing: 0.1em; margin-top: 2px; }
  .inv-meta { text-align: right; }
  .inv-number { font-size: 20px; font-weight: 700; color: #1E293B; }
  .inv-label { font-size: 10px; color: #94A3B8; text-transform: uppercase; letter-spacing: 0.08em; }
  .inv-value { font-size: 13px; color: #475569; margin-top: 2px; }
  .divider { border: none; border-top: 2px solid #1B4FD8; margin: 24px 0; }
  .parties { display: flex; justify-content: space-between; margin-bottom: 32px; }
  .party-label { font-size: 10px; color: #94A3B8; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 6px; }
  .party-name { font-size: 15px; font-weight: 600; color: #1E293B; }
  .party-detail { font-size: 12px; color: #475569; line-height: 1.6; margin-top: 4px; }
  table { width: 100%; border-collapse: collapse; margin-bottom: 24px; }
  thead tr { background: #1E3A5F; color: white; }
  thead th { padding: 10px 14px; text-align: left; font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em; font-weight: 600; }
  tbody tr:nth-child(even) { background: #F8FAFC; }
  tbody td { padding: 11px 14px; border-bottom: 1px solid #E2E8F0; font-size: 13px; }
  .amount { text-align: right; font-family: monospace; }
  .totals { margin-left: auto; width: 260px; }
  .totals-row { display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #E2E8F0; font-size: 13px; }
  .totals-row.total { font-weight: 700; font-size: 16px; color: #1B4FD8; border-bottom: none; padding-top: 12px; }
  .footer { margin-top: 48px; padding-top: 16px; border-top: 1px solid #E2E8F0; font-size: 11px; color: #94A3B8; text-align: center; }
  .status-badge { display: inline-block; padding: 3px 10px; border-radius: 12px; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; }
  .status-draft     { background: #EFF6FF; color: #1D4ED8; }
  .status-finalised { background: #F0FDF4; color: #166534; }
  .status-sent      { background: #FFFBEB; color: #92400E; }
  .status-paid      { background: #ECFDF5; color: #065F46; }
</style>
</head>
<body>
  <div class="header">
    <div>
      <div class="logo">Orbi</div>
      <div class="logo-sub">Billing Platform</div>
    </div>
    <div class="inv-meta">
      <div class="inv-number">{{ invoice.invoice_number }}</div>
      <div style="margin-top:8px">
        <div class="inv-label">Status</div>
        <span class="status-badge status-{{ invoice.status.value }}">{{ invoice.status.value }}</span>
      </div>
      <div style="margin-top:8px">
        <div class="inv-label">Invoice Date</div>
        <div class="inv-value">{{ invoice.created_at.strftime('%d %b %Y') if invoice.created_at else '—' }}</div>
      </div>
      <div style="margin-top:8px">
        <div class="inv-label">Due Date</div>
        <div class="inv-value">{{ invoice.due_date.strftime('%d %b %Y') if invoice.due_date else '—' }}</div>
      </div>
    </div>
  </div>

  <hr class="divider"/>

  <div class="parties">
    <div>
      <div class="party-label">From</div>
      <div class="party-name">Orbi Billing Ltd</div>
      <div class="party-detail">billing@orbi.io<br/>United Kingdom</div>
    </div>
    <div>
      <div class="party-label">Bill To</div>
      <div class="party-name">{{ customer.name }}</div>
      <div class="party-detail">
        {{ customer.email }}<br/>
        {% if customer.phone %}{{ customer.phone }}<br/>{% endif %}
        {% if customer.address %}{{ customer.address }}{% endif %}
      </div>
    </div>
    <div>
      <div class="party-label">Billing Period</div>
      <div class="party-detail" style="font-size:14px;font-weight:600;color:#1E293B">
        {{ invoice.period_start.strftime('%d %b %Y') if invoice.period_start else '—' }}<br/>
        to {{ invoice.period_end.strftime('%d %b %Y') if invoice.period_end else '—' }}
      </div>
    </div>
  </div>

  <table>
    <thead>
      <tr>
        <th style="width:55%">Description</th>
        <th style="width:15%;text-align:center">Qty</th>
        <th style="width:15%;text-align:right">Unit Price</th>
        <th style="width:15%;text-align:right">Amount</th>
      </tr>
    </thead>
    <tbody>
      {% for item in line_items %}
      <tr>
        <td>{{ item.description }}</td>
        <td style="text-align:center">{{ item.quantity }}</td>
        <td class="amount">{{ format_money(item.unit_price, invoice.currency) }}</td>
        <td class="amount">{{ format_money(item.amount, invoice.currency) }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>

  <div class="totals">
    <div class="totals-row">
      <span>Subtotal</span>
      <span>{{ format_money(invoice.subtotal, invoice.currency) }}</span>
    </div>
    <div class="totals-row">
      <span>Tax (0%)</span>
      <span>{{ format_money(0, invoice.currency) }}</span>
    </div>
    <div class="totals-row total">
      <span>Total Due</span>
      <span>{{ format_money(invoice.total, invoice.currency) }}</span>
    </div>
  </div>

  <div class="footer">
    {{ invoice.invoice_number }} · Generated by Orbi Billing ·
    {{ generated_at }} · Thank you for your business.
  </div>
</body>
</html>
"""


def format_money(cents: int, currency: str = "GBP") -> str:
    """Format cents as currency string."""
    symbols = {"GBP": "£", "EUR": "€", "USD": "$"}
    symbol = symbols.get(currency, currency + " ")
    return f"{symbol}{cents / 100:.2f}"


async def generate_invoice_pdf(invoice: Invoice, db: AsyncSession) -> str | None:
    """
    Render invoice to PDF and save to disk.
    Returns the file path, or None if generation failed.
    """
    try:
        from jinja2 import Environment
        env = Environment()
        env.globals["format_money"] = format_money
        template = env.from_string(INVOICE_TEMPLATE)
    except ImportError:
        print(f"DEBUG: Jinja2 Import Failed: {e}")
        return None

    # Load customer
    cust_r = await db.execute(select(Customer).where(Customer.id == invoice.customer_id))
    customer = cust_r.scalar_one_or_none()

    # Load line items
    li_r = await db.execute(
        select(InvoiceLineItem).where(InvoiceLineItem.invoice_id == invoice.id)
    )
    line_items = li_r.scalars().all()

    # Render HTML
    html = template.render(
        invoice=invoice,
        customer=customer,
        line_items=line_items,
        generated_at=datetime.utcnow().strftime("%d %b %Y %H:%M UTC"),
    )

    # Generate PDF
    pdf_filename = f"{invoice.invoice_number}.pdf"
    pdf_path = PDF_DIR / pdf_filename

    try:
        from weasyprint import HTML
        HTML(string=html).write_pdf(str(pdf_path))
        return f"/pdfs/{pdf_filename}"
    except ImportError as e:
        # WeasyPrint not installed — save HTML instead as fallback
        print(f"DEBUG: WeasyPrint Import Failed: {e}")
        html_path = PDF_DIR / f"{invoice.invoice_number}.html"
        html_path.write_text(html)
        return f"/pdfs/{invoice.invoice_number}.html"
    except Exception as e:
        print(f"DEBUG: PDF Generation Failed: {e}")
        return None


async def get_invoice_pdf_path(invoice_number: str) -> Path | None:
    """Get the path to a generated invoice PDF."""
    for ext in [".pdf", ".html"]:
        path = PDF_DIR / f"{invoice_number}{ext}"
        if path.exists():
            return path
    return None
