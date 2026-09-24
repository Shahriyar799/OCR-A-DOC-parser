import io
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from .schemas import CertificateData


def _font_path(filename: str) -> Path:
    candidates = [
        Path(__file__).resolve().parent / "fonts" / filename,
        Path("/usr/share/fonts/truetype/dejavu") / filename,
        Path("C:/Windows/Fonts")
        / ("arialbd.ttf" if "Bold" in filename else "arial.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise RuntimeError(
        "Azərbaycan hərflərini dəstəkləyən DejaVu Sans/Arial şrifti tapılmadı."
    )


def _register_fonts() -> None:
    if "CertificateSans" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(
            TTFont("CertificateSans", str(_font_path("DejaVuSans.ttf")))
        )
        pdfmetrics.registerFont(
            TTFont("CertificateSans-Bold", str(_font_path("DejaVuSans-Bold.ttf")))
        )


def _text(value: str) -> str:
    return escape(value.strip()) if value and value.strip() else "-"


def _footer(canvas, document) -> None:
    canvas.saveState()
    canvas.setFont("CertificateSans", 8)
    canvas.setFillColor(colors.HexColor("#666666"))
    canvas.drawCentredString(A4[0] / 2, 11 * mm, f"Səhifə {document.page}")
    canvas.restoreState()


def build_certificate_pdf(data: CertificateData) -> bytes:
    _register_fonts()
    output = io.BytesIO()
    document = BaseDocTemplate(
        output,
        pagesize=A4,
        leftMargin=24 * mm,
        rightMargin=24 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        title=f"Arayış - {data.full_name or 'əcnəbi'}",
        author="Sənəd Məlumat Çıxarışı",
    )
    frame = Frame(
        document.leftMargin,
        document.bottomMargin,
        document.width,
        document.height,
        id="certificate",
    )
    document.addPageTemplates(PageTemplate(id="main", frames=[frame], onPage=_footer))

    styles = getSampleStyleSheet()
    body = ParagraphStyle(
        "BodyAZ",
        parent=styles["BodyText"],
        fontName="CertificateSans",
        fontSize=10.5,
        leading=14,
        textColor=colors.HexColor("#111111"),
        spaceAfter=5,
    )
    bold = ParagraphStyle("BoldAZ", parent=body, fontName="CertificateSans-Bold")
    title = ParagraphStyle(
        "TitleAZ",
        parent=bold,
        fontSize=16,
        leading=19,
        alignment=TA_CENTER,
        spaceAfter=18,
    )
    section = ParagraphStyle(
        "SectionAZ",
        parent=bold,
        fontSize=11,
        leading=14,
        alignment=TA_CENTER,
        spaceBefore=11,
        spaceAfter=8,
    )
    recipient = ParagraphStyle(
        "RecipientAZ",
        parent=body,
        alignment=TA_RIGHT,
        leftIndent=70 * mm,
        spaceAfter=26,
    )
    conclusion = ParagraphStyle(
        "ConclusionAZ",
        parent=body,
        fontSize=11.5,
        leading=16,
        alignment=TA_LEFT,
        spaceAfter=24,
    )

    def line(label: str, value: str, indent: int = 0) -> Paragraph:
        return Paragraph(
            f'<font name="CertificateSans-Bold">{escape(label)}:</font> {_text(value)}',
            ParagraphStyle(
                f"line-{label}-{indent}", parent=body, leftIndent=indent * mm
            ),
        )

    story = []
    if data.recipient.strip():
        story.append(Paragraph(_text(data.recipient), recipient))
    else:
        story.append(Spacer(1, 18 * mm))

    story.extend(
        [
            Paragraph("ARAYIŞ", title),
            Paragraph(
                _text(data.full_name),
                ParagraphStyle("NameAZ", parent=bold, fontSize=11.5),
            ),
            line("Müraciət etdiyi tarix", data.application_date),
            line("Vətəndaşlığı", data.citizenship),
            line("Cinsi", data.sex),
            Spacer(1, 3 * mm),
            Paragraph("Pasport məlumatları", bold),
            line("Seriya və nömrəsi", data.passport_number, 22),
            line("Verən orqan", data.passport_issuer, 22),
            line("Verildiyi tarix", data.passport_issue_date, 22),
            line("Etibarlılıq tarixi", data.passport_expiry, 22),
            line(
                "Doğum tarixi, doğulduğu yer",
                ", ".join(
                    part
                    for part in [data.date_of_birth.strip(), data.birth_place.strip()]
                    if part
                ),
                22,
            ),
            Paragraph("Müvəqqəti yaşamaq üçün icazə verilməsinə əsaslar", section),
            line("Vəsatətin əsası", data.permit_basis),
            line("Vəsatətin əsası haqqında qeyd", data.basis_note),
            Spacer(1, 5 * mm),
            line("Xüsusi qeyd", data.special_note),
            Paragraph(
                "Müvəqqəti yaşamaq üçün icazənin müddətinin uzadılmasına əsas olmuş hallar",
                section,
            ),
            Paragraph("Şəxsin MYİ ilə bağlı müraciəti", bold),
            Paragraph(_text(data.temporary_permit_history), body),
            Spacer(1, 3 * mm),
            Paragraph("Şəxsin DYİ ilə bağlı müraciəti", bold),
            Paragraph(_text(data.permanent_permit_history), body),
            PageBreak(),
            Paragraph("NƏTİCƏ", title),
            Paragraph(_text(data.conclusion), conclusion),
        ]
    )

    signature = Table(
        [
            [
                Paragraph(_text(data.manager_title), body),
                Paragraph(_text(data.manager_name), bold),
            ]
        ],
        colWidths=[70 * mm, 70 * mm],
        hAlign="LEFT",
    )
    signature.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4 * mm),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.append(signature)
    document.build(story)
    return output.getvalue()
