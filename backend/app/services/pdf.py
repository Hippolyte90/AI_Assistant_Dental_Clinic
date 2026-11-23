"""Renders a treatment plan to PDF with ReportLab."""

from decimal import Decimal
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.config import Settings
from app.models.schemas import Interval, TreatmentPlan

TEAL = colors.HexColor("#1F7A6D")
INK = colors.HexColor("#1B2733")
MUTED = colors.HexColor("#5B6875")
PALE = colors.HexColor("#E8F3F1")
AMBER = colors.HexColor("#FFF6E5")
RULE = colors.HexColor("#CBD5DC")
FOOTER = "Estimate based on the clinic price list. Prices in EUR."


def format_eur(value: Decimal) -> str:
    """Format as '1 234.56 €'."""
    return f"{value:,.2f}".replace(",", " ") + " €"


def format_days(low: int, high: int) -> str:
    """Readable duration."""
    if high == 0:
        return "single stage"
    if low >= 60:
        unit, size = "months", 30
    elif low >= 14:
        unit, size = "weeks", 7
    else:
        unit, size = "days", 1
    first, last = round(low / size), round(high / size)
    return f"about {first} {unit}" if first == last else f"about {first}–{last} {unit}"


def _interval(interval: Interval) -> str:
    text = format_days(interval.min_days, interval.max_days).replace("about ", "")
    suffix = " – assumption, to confirm" if interval.assumed else ""
    return f"Next stage after: {text} ({escape(interval.reason)}){suffix}"


class _NumberedCanvas(canvas.Canvas):
    """Canvas that knows the page count, for 'Page x of y'."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._pages: list[dict] = []

    def showPage(self) -> None:
        self._pages.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        """Write every page with its footer numbering."""
        total = len(self._pages)
        for state in self._pages:
            self.__dict__.update(state)
            self.setFont("Helvetica", 8)
            self.setFillColor(MUTED)
            self.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {self._pageNumber} of {total}")
            super().showPage()
        super().save()


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()["BodyText"]
    body = ParagraphStyle("body", parent=base, fontSize=9, leading=12, textColor=INK)
    return {
        "body": body,
        "small": ParagraphStyle("small", parent=body, fontSize=8, leading=10, textColor=MUTED),
        "cell": ParagraphStyle("cell", parent=body, fontSize=8.5, leading=11),
        "right": ParagraphStyle("right", parent=body, fontSize=8.5, leading=11, alignment=TA_RIGHT),
        "head": ParagraphStyle(
            "head",
            parent=body,
            fontName="Helvetica-Bold",
            fontSize=8,
            textColor=colors.white,
        ),
        "head_r": ParagraphStyle(
            "head_r",
            parent=body,
            fontName="Helvetica-Bold",
            fontSize=8,
            textColor=colors.white,
            alignment=TA_RIGHT,
        ),
        "title": ParagraphStyle(
            "title",
            parent=body,
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=22,
            textColor=INK,
        ),
        "h2": ParagraphStyle(
            "h2",
            parent=body,
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            textColor=TEAL,
            spaceBefore=2,
        ),
    }


def render_plan_pdf(
    plan: TreatmentPlan, path: Path, settings: Settings, patient_label: str = ""
) -> Path:
    """Write the PDF and return its path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    styles = _styles()
    width = A4[0] - 36 * mm
    story: list = []
    is_final = plan.status == "FINAL"

    clinic = f"<b>{escape(settings.clinic_name)}</b>"
    if settings.clinic_address:
        clinic += f"<br/>{escape(settings.clinic_address)}"
    if settings.dentist_name:
        clinic += f"<br/>Dentist: {escape(settings.dentist_name)}"
    badge = "FINAL – confirmed" if is_final else "DRAFT – pending answers"
    meta = (
        f"<b>{badge}</b><br/>Version {plan.version}<br/>"
        f"Date: {plan.created_at:%d %B %Y}<br/>Patient: {escape(patient_label) or '—'}"
    )
    header = Table(
        [[Paragraph(clinic, styles["body"]), Paragraph(meta, styles["right"])]],
        colWidths=[width * 0.55, width * 0.45],
    )
    header.setStyle(
        TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (0, 0), 0)])
    )
    story += [
        header,
        Spacer(1, 5 * mm),
        Paragraph("Treatment plan", styles["title"]),
        Spacer(1, 3 * mm),
    ]

    low, high = plan.estimated_duration_days
    summary = Table(
        [
            [
                Paragraph(f"Stages<br/><b>{len(plan.stages)}</b>", styles["body"]),
                Paragraph(
                    f"Estimated duration<br/><b>{format_days(low, high)}</b>",
                    styles["body"],
                ),
                Paragraph(f"Total<br/><b>{format_eur(plan.total_eur)}</b>", styles["body"]),
            ]
        ],
        colWidths=[width * 0.2, width * 0.45, width * 0.35],
    )
    summary.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), PALE),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story += [summary, Spacer(1, 5 * mm)]

    col = [width * f for f in (0.09, 0.42, 0.11, 0.07, 0.15, 0.16)]
    for stage in plan.stages:
        rows = [
            [
                Paragraph("Code", styles["head"]),
                Paragraph("Service", styles["head"]),
                Paragraph("Teeth", styles["head"]),
                Paragraph("Qty", styles["head_r"]),
                Paragraph("Unit price", styles["head_r"]),
                Paragraph("Total", styles["head_r"]),
            ]
        ]
        for item in stage.items:
            name = escape(item.name) + (" <i>(provisional)</i>" if item.provisional else "")
            rows.append(
                [
                    Paragraph(escape(item.code or "—"), styles["cell"]),
                    Paragraph(name, styles["cell"]),
                    Paragraph(", ".join(str(t) for t in item.teeth) or "—", styles["cell"]),
                    Paragraph(str(item.quantity), styles["right"]),
                    Paragraph(format_eur(item.unit_price), styles["right"]),
                    Paragraph(format_eur(item.line_total), styles["right"]),
                ]
            )
        rows.append(
            ["", Paragraph("<b>Stage subtotal</b>", styles["cell"]), "", "", "",
             Paragraph(f"<b>{format_eur(stage.subtotal)}</b>", styles["right"])]
        )  # fmt: skip
        table = Table(rows, colWidths=col, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), TEAL),
                    ("LINEBELOW", (0, 1), (-1, -2), 0.25, RULE),
                    ("BACKGROUND", (0, -1), (-1, -1), PALE),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        block = [
            Paragraph(f"Stage {stage.number}: {escape(stage.title)}", styles["h2"]),
            Paragraph(escape(stage.goal), styles["small"]),
            Spacer(1, 1.5 * mm),
            table,
        ]
        if stage.interval_after:
            block += [
                Spacer(1, 1.5 * mm),
                Paragraph(_interval(stage.interval_after), styles["small"]),
            ]
        story += [KeepTogether(block), Spacer(1, 4 * mm)]

    if len(plan.stages) > 1:
        timeline: list[str] = []
        for stage in plan.stages:
            timeline.append(f"<b>{stage.number}.</b> {escape(stage.title)}")
            if stage.interval_after:
                gap = stage.interval_after
                timeline.append(format_days(gap.min_days, gap.max_days).replace("about ", "→ "))
        story += [
            KeepTogether(
                [
                    Paragraph("Timeline", styles["h2"]),
                    Paragraph("  ".join(timeline), styles["body"]),
                    Spacer(1, 4 * mm),
                ]
            )
        ]

    if not is_final and plan.questions:
        text = "<br/>".join(f"• {escape(q.text)}" for q in plan.questions)
        story += [_box("Open questions", text, styles, width), Spacer(1, 3 * mm)]
    if plan.assumptions:
        text = "<br/>".join(f"• {escape(a)}" for a in plan.assumptions)
        story += [_box("Assumptions", text, styles, width), Spacer(1, 3 * mm)]
    if plan.unmapped_mentions:
        text = "<br/>".join(f"• {escape(m)}" for m in plan.unmapped_mentions)
        story += [_box("Mentioned but not in the price list (not priced)", text, styles, width)]

    if is_final:
        signature = Table(
            [
                ["", "", ""],
                ["Dentist signature and date", "", "Patient signature and date"],
            ],
            colWidths=[width * 0.45, width * 0.1, width * 0.45],
            rowHeights=[16 * mm, 6 * mm],
        )
        signature.setStyle(
            TableStyle(
                [
                    ("LINEBELOW", (0, 0), (0, 0), 0.7, INK),
                    ("LINEBELOW", (2, 0), (2, 0), 0.7, INK),
                    ("FONTSIZE", (0, 1), (-1, 1), 8),
                    ("TEXTCOLOR", (0, 1), (-1, 1), MUTED),
                ]
            )
        )
        story += [Spacer(1, 4 * mm), KeepTogether([signature])]

    def decorate(pdf: canvas.Canvas, _doc) -> None:
        pdf.saveState()
        if not is_final:
            pdf.setFillColor(colors.Color(0.6, 0.6, 0.6, alpha=0.16))
            pdf.setFont("Helvetica-Bold", 96)
            pdf.translate(A4[0] / 2, A4[1] / 2)
            pdf.rotate(45)
            pdf.drawCentredString(0, -30, "DRAFT")
            pdf.rotate(-45)
            pdf.translate(-A4[0] / 2, -A4[1] / 2)
        pdf.setFont("Helvetica", 8)
        pdf.setFillColor(MUTED)
        pdf.drawString(18 * mm, 10 * mm, FOOTER)
        pdf.restoreState()

    document = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=18 * mm,
        title=f"Treatment plan v{plan.version}",
    )
    document.build(story, onFirstPage=decorate, onLaterPages=decorate, canvasmaker=_NumberedCanvas)
    return path


def _box(title: str, text: str, styles: dict, width: float) -> KeepTogether:
    table = Table(
        [
            [Paragraph(f"<b>{escape(title)}</b>", styles["body"])],
            [Paragraph(text, styles["cell"])],
        ],
        colWidths=[width],
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), AMBER),
                ("BOX", (0, 0), (-1, -1), 0.4, RULE),
            ]
        )
    )
    return KeepTogether([table])
