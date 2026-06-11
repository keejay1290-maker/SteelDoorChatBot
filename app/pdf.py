"""PDF quote generation for Steel Door Company.

Uses reportlab (pure Python, no system deps — works on Vercel).
Produces a branded A4 estimate with itemised lines, VAT, lead time,
and a disclaimer footer.
"""
from __future__ import annotations

import io
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .models import QuoteResponse

# Brand palette
_GOLD = colors.HexColor("#C9A84C")
_DARK = colors.HexColor("#111111")
_LIGHT_GREY = colors.HexColor("#F5F5F5")
_MID_GREY = colors.HexColor("#CCCCCC")
_TEXT = colors.HexColor("#222222")

_PAGE_W, _PAGE_H = A4
_L_MARGIN = 18 * mm
_R_MARGIN = 18 * mm


def build_quote_pdf(quote: QuoteResponse) -> bytes:
    """Render a QuoteResponse to a branded A4 PDF and return the bytes."""
    buf = io.BytesIO()

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=_L_MARGIN,
        rightMargin=_R_MARGIN,
        topMargin=12 * mm,
        bottomMargin=20 * mm,
    )

    styles = getSampleStyleSheet()
    story = []

    def _style(name, parent="Normal", **kw) -> ParagraphStyle:
        return ParagraphStyle(name, parent=styles[parent], **kw)

    company_style = _style("Company", fontSize=18, textColor=_GOLD,
                           fontName="Helvetica-Bold", spaceAfter=1 * mm)
    tagline_style = _style("Tagline", fontSize=8, textColor=_MID_GREY,
                           fontName="Helvetica", spaceAfter=4 * mm)
    title_style = _style("Title", fontSize=13, textColor=_DARK,
                         fontName="Helvetica-Bold", spaceAfter=2 * mm)
    ref_style = _style("Ref", fontSize=9, textColor=colors.grey,
                       fontName="Helvetica", spaceAfter=6 * mm)
    section_hdr = _style("SectionHdr", fontSize=9, textColor=_GOLD,
                         fontName="Helvetica-Bold", spaceBefore=4 * mm, spaceAfter=1 * mm)
    body_style = _style("Body", fontSize=9, textColor=_TEXT, fontName="Helvetica",
                        spaceAfter=1.5 * mm)
    small_style = _style("Small", fontSize=7.5, textColor=colors.grey,
                         fontName="Helvetica", leading=10)

    # ── Header ────────────────────────────────────────────────────────────────
    story.append(Paragraph("STEEL DOOR COMPANY", company_style))
    story.append(Paragraph("The UK's Leading Installer of Bespoke Steel Doors", tagline_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=_GOLD, spaceAfter=4 * mm))

    story.append(Paragraph("INDICATIVE ESTIMATE", title_style))
    date_str = datetime.now(timezone.utc).strftime("%d %B %Y")
    story.append(Paragraph(
        f"Reference: <b>{quote.reference}</b> &nbsp;&nbsp;|&nbsp;&nbsp; Date: {date_str}",
        ref_style,
    ))

    # ── Product summary ───────────────────────────────────────────────────────
    story.append(Paragraph("PRODUCT", section_hdr))
    story.append(Paragraph(quote.product_name, _style("Prod", fontSize=10, textColor=_DARK,
                                                       fontName="Helvetica-Bold")))
    if quote.quantity > 1:
        story.append(Paragraph(f"Quantity: {quote.quantity}", body_style))
    story.append(Paragraph(f"Lead time: {quote.lead_time}", body_style))

    # ── Itemised lines ────────────────────────────────────────────────────────
    story.append(Paragraph("PRICE BREAKDOWN", section_hdr))

    table_data = [
        [Paragraph("<b>Item</b>", body_style), Paragraph("<b>Amount</b>", _style("TH_R", fontSize=9, textColor=_TEXT, fontName="Helvetica-Bold", alignment=TA_RIGHT))],
    ]
    for ln in quote.lines:
        table_data.append([
            Paragraph(ln.label, body_style),
            Paragraph(f"£{ln.amount:,.2f}", _style(f"amt_{id(ln)}", fontSize=9, textColor=_TEXT, fontName="Helvetica", alignment=TA_RIGHT)),
        ])
    if quote.quantity > 1:
        table_data.append([
            Paragraph(f"Subtotal × {quote.quantity} doors", body_style),
            Paragraph(f"£{quote.unit_price * quote.quantity:,.2f}", _style("stq", fontSize=9, textColor=_TEXT, fontName="Helvetica", alignment=TA_RIGHT)),
        ])
    if quote.sale_discount:
        table_data.append([
            Paragraph("Summer Sale (10% off, capped £1,000)", _style("disc", fontSize=9, textColor=colors.HexColor("#22c55e"), fontName="Helvetica")),
            Paragraph(f"-£{quote.sale_discount:,.2f}", _style("disca", fontSize=9, textColor=colors.HexColor("#22c55e"), fontName="Helvetica", alignment=TA_RIGHT)),
        ])

    col_w = _PAGE_W - _L_MARGIN - _R_MARGIN
    tbl = Table(table_data, colWidths=[col_w * 0.72, col_w * 0.28])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), _LIGHT_GREY),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, _MID_GREY),
        ("LINEBELOW", (0, -1), (-1, -1), 0.5, _MID_GREY),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (0, -1), 4),
        ("RIGHTPADDING", (-1, 0), (-1, -1), 4),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(tbl)

    # ── Totals ────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 3 * mm))
    totals_data = [
        ["Subtotal (exc. VAT)", f"£{quote.subtotal:,.2f}"],
        ["VAT (20%)", f"£{quote.vat:,.2f}"],
        ["TOTAL INC. VAT", f"£{quote.total:,.2f}"],
    ]
    totals_tbl = Table(totals_data, colWidths=[col_w * 0.72, col_w * 0.28])
    totals_tbl.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -2), "Helvetica"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -2), 9),
        ("FONTSIZE", (0, -1), (-1, -1), 11),
        ("TEXTCOLOR", (0, -1), (-1, -1), _DARK),
        ("BACKGROUND", (0, -1), (-1, -1), _LIGHT_GREY),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("LINEABOVE", (0, -1), (-1, -1), 1.5, _GOLD),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (0, -1), 4),
        ("RIGHTPADDING", (-1, 0), (-1, -1), 4),
    ]))
    story.append(totals_tbl)

    # ── Notes ─────────────────────────────────────────────────────────────────
    if quote.notes:
        story.append(Spacer(1, 5 * mm))
        story.append(HRFlowable(width="100%", thickness=0.5, color=_MID_GREY))
        story.append(Spacer(1, 2 * mm))
        for note in quote.notes:
            story.append(Paragraph(f"• {note}", small_style))

    # ── Disclaimer ────────────────────────────────────────────────────────────
    story.append(Spacer(1, 5 * mm))
    story.append(Paragraph(
        "This is an <b>indicative estimate only</b> and does not constitute a formal quotation. "
        "All prices are based on standard published rates and are subject to confirmation following "
        "a free site survey. Prices exclude delivery, unless otherwise stated.",
        small_style,
    ))

    # ── Footer ────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 8 * mm))
    story.append(HRFlowable(width="100%", thickness=1, color=_GOLD))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(
        "Steel Door Company &nbsp;|&nbsp; Unit C, Scarlet Court, Stafford ST16 1YJ &nbsp;|&nbsp; "
        "01785 526016 &nbsp;|&nbsp; sales@steeldoorcompany.co.uk &nbsp;|&nbsp; steeldoorcompany.co.uk",
        _style("Footer", fontSize=7.5, textColor=colors.grey, fontName="Helvetica", alignment=TA_CENTER),
    ))

    doc.build(story)
    return buf.getvalue()
