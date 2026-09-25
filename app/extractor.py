import base64
import io
import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pymupdf
from PIL import Image

from .schemas import (
    CrossCheck,
    DocumentSummary,
    ExtractedField,
    ExtractionResponse,
    PersonData,
)

FIELD_LABELS = {
    "full_name": r"^(?:soyad[ıi]?\s*,?\s*ad[ıi]?\s*,?\s*ata\s*ad[ıi]?|ad[ıi]?\s*,?\s*soyad[ıi]?\s*,?\s*ata\s*ad[ıi]?|full\s*name|name|ad[ıi]?\b|фамилия.*имя)[ \t]*[:\-]?[ \t]*([^\n]{3,100})",
    "application_date": r"^(?:müraciət\s*(?:etdiyi\s*)?tarix|application\s*date|дата\s*обращения)[ \t]*[:\-]?[ \t]*([^\n]{3,60})",
    "date_of_birth": r"^(?:doğum\s*tarixi|date\s*of\s*birth|дата\s*рождения)[ \t]*[:\-]?[ \t]*([^,\n]{3,60})",
    "birth_place": r"^(?:doğulduğu\s*yer|place\s*of\s*birth|место\s*рождения)[ \t]*[:\-]?[ \t]*([^\n]{3,100})",
    "citizenship": r"^(?:vətəndaşlığ[ıi]?|vətəndaşlıq|citizenship|гражданств[оа])[ \t]*[:\-]?[ \t]*([^\n]{3,60})",
    "personal_id": r"^(?:f[iİ]n\s*(?:kod)?|personal\s*(?:id|number)|персонал(?:ьный)?\s*(?:код|номер))\s*[:\-]?\s*([A-Z0-9\-]{5,20})",
    "passport_number": r"^(?:seriya\s*və\s*nömrəsi|passport\s*(?:no|number)?|pasport\s*(?:№|no|number)?|паспорт\s*(?:№|номер)?)\s*[:\-]?\s*([A-Z0-9]{5,16})",
    "passport_issuer": r"^(?:verən\s*orqan|issued\s*by|кем\s*выдан)[ \t]*[:\-]?[ \t]*([^\n]{2,100})",
    "passport_issue_date": r"^(?:verildiyi\s*tarix|date\s*of\s*issue|дата\s*выдачи)[ \t]*[:\-]?[ \t]*([^\n]{3,60})",
    "passport_expiry": r"^(?:expiry|valid\s*until|bitmə\s*tarixi|etibarlıdır|действителен\s*до)\s*[:\-]?\s*([0-3]?\d[.\-/][01]?\d[.\-/](?:19|20)\d{2})",
    "visa_number": r"^(?:visa\s*(?:no|number)?|viza\s*(?:№|no|number)?|виза\s*(?:№|номер)?)\s*[:\-]?\s*([A-Z0-9\-]{5,20})",
    "entry_date": r"^(?:entry\s*date|giriş\s*tarixi|дата\s*въезда)\s*[:\-]?\s*([0-3]?\d[.\-/][01]?\d[.\-/](?:19|20)\d{2})",
    "phone": r"(?:telefon|phone|tel\.?|моб(?:ильный)?)[ \t]*[:\-]?[ \t]*(\+?[0-9()\- \t]{7,25})",
    "email": r"\b([A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,})\b",
    "address": r"^(?:yaşayış\s*ünvanı|ünvan|address|адрес)[ \t]*[:\-]?[ \t]*([^\n]{5,180})",
    "application_type": r"^(?:müraciət(?:in)?\s*növü|application\s*type|вид\s*заявления)[ \t]*[:\-]?[ \t]*([^\n]{3,100})",
    "permit_basis": r"^(?:vəsatətin\s*əsası|icazə\s*üçün\s*əsas|permit\s*basis)[ \t]*[:\-]?[ \t]*([^\n]{3,180})",
    "basis_note": r"^(?:vəsatətin\s*əsası\s*haqqında\s*qeyd|əsas\s*haqqında\s*qeyd)[ \t]*[:\-]?[ \t]*([^\n]{3,500})",
    "special_note": r"^(?:xüsusi\s*qeyd|special\s*note)[ \t]*[:\-]?[ \t]*([^\n]{3,500})",
    "temporary_permit_history": r"^(?:şəxsin\s*myi\s*ilə\s*bağlı\s*müraciəti|myi\s*tarixçəsi)[ \t]*[:\-]?[ \t]*([^\n]{3,500})",
    "permanent_permit_history": r"^(?:şəxsin\s*dyi\s*ilə\s*bağlı\s*müraciəti|dyi\s*tarixçəsi)[ \t]*[:\-]?[ \t]*([^\n]{3,500})",
    "conclusion": r"^(?:nəticə|rəy|conclusion)[ \t]*[:\-]?[ \t]*([^\n]{3,500})",
}


FIELD_NAMES = tuple(PersonData.model_fields)
DOCUMENT_TYPES = (
    "passport",
    "application_form",
    "birth_certificate",
    "medical_certificate",
    "school_certificate",
    "notarized_application",
    "property_document",
    "residence_permit",
    "reference_letter",
    "other",
)

VISION_FIELD_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "value": {"type": "string"},
        "confidence": {
            "type": "string",
            "enum": ["high", "medium", "low", "not_found"],
        },
        "source_page": {"type": "integer", "minimum": 0},
    },
    "required": ["value", "confidence", "source_page"],
}

VISION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "document_type": {"type": "string", "enum": list(DOCUMENT_TYPES)},
        "fields": {
            "type": "object",
            "additionalProperties": False,
            "properties": {name: VISION_FIELD_SCHEMA for name in FIELD_NAMES},
            "required": list(FIELD_NAMES),
        },
    },
    "required": ["document_type", "fields"],
}


@dataclass(frozen=True)
class PageContent:
    image: bytes
    page_number: int
    text: str


@dataclass(frozen=True)
class DocumentResult:
    name: str
    document_type: str
    pages: list[PageContent]
    fields: PersonData
    method: str


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" :;,-")


def _normalize_text(value: str) -> str:
    """Normalize spacing without removing field boundaries between lines."""
    value = value.translate(
        {
            ord("ә"): "ə",
            ord("Ә"): "Ə",
            ord("\u00ad"): "-",
            ord("\u00a0"): " ",
        }
    )
    lines = (
        _clean(line)
        for line in value.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    )
    return "\n".join(line for line in lines if line)


def normalize_image(content: bytes) -> bytes:
    """Validate an uploaded image and convert it to the PNG format sent to vision."""
    try:
        with Image.open(io.BytesIO(content)) as image:
            image.load()
            converted = image.convert("RGB")
            output = io.BytesIO()
            converted.save(output, format="PNG")
            return output.getvalue()
    except (OSError, ValueError) as error:
        raise ValueError("Şəkil faylı zədəlidir və ya dəstəklənmir.") from error


def _render_pdf_with_poppler(content: bytes, page_count: int) -> list[bytes]:
    """Render every PDF page at OCR quality with Poppler when it is available."""
    max_pages = min(page_count, int(os.getenv("MAX_PDF_PAGES", "13")))
    with tempfile.TemporaryDirectory(prefix="document-intake-") as folder:
        folder_path = Path(folder)
        pdf_path = folder_path / "source.pdf"
        output_prefix = folder_path / "page"
        pdf_path.write_bytes(content)
        try:
            completed = subprocess.run(
                [
                    "pdftoppm",
                    "-png",
                    "-r",
                    os.getenv("PDF_RENDER_DPI", "220"),
                    "-f",
                    "1",
                    "-l",
                    str(max_pages),
                    str(pdf_path),
                    str(output_prefix),
                ],
                check=False,
                capture_output=True,
                timeout=120,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return []
        if completed.returncode != 0:
            return []
        files = sorted(
            folder_path.glob("page-*.png"),
            key=lambda path: int(path.stem.rsplit("-", maxsplit=1)[1]),
        )
        return [path.read_bytes() for path in files]


def extract_pdf_pages(content: bytes) -> list[PageContent]:
    document = pymupdf.open(stream=content, filetype="pdf")
    page_count = min(document.page_count, int(os.getenv("MAX_PDF_PAGES", "13")))
    rendered = _render_pdf_with_poppler(content, page_count)
    pages: list[PageContent] = []
    for index in range(page_count):
        page = document[index]
        if index < len(rendered):
            image = rendered[index]
        else:
            pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
            image = pix.tobytes("png")
        text = page.get_text("text")
        if len(_clean(text)) < 30:
            text = f"{text}\n{_ocr_image(image)}"
        pages.append(PageContent(image=image, page_number=index + 1, text=text))
    document.close()
    return pages


def _ocr_image(image: bytes) -> str:
    """Use local OCR for scanned pages before sending visual input to the LLM."""
    try:
        import pytesseract

        with Image.open(io.BytesIO(image)) as page:
            return pytesseract.image_to_string(
                page,
                lang=os.getenv("OCR_LANGUAGES", "aze+rus+eng"),
                config="--oem 1 --psm 6",
            )
    except Exception:  # noqa: BLE001 - visual extraction remains available
        return ""


def extract_text_from_pdf(content: bytes) -> tuple[str, list[bytes]]:
    """Backward-compatible text/image helper used by existing integrations."""
    pages = extract_pdf_pages(content)
    return "\n".join(page.text for page in pages), [page.image for page in pages]


def local_extract(
    text: str, *, source: str = "PDF/OCR mətni", source_page: int | None = None
) -> PersonData:
    normalized = _normalize_text(text)
    values: dict[str, ExtractedField] = {}
    for key, pattern in FIELD_LABELS.items():
        match = re.search(pattern, normalized, re.IGNORECASE | re.MULTILINE)
        value = _clean(match.group(1)) if match else ""
        values[key] = ExtractedField(
            value=value,
            confidence="medium" if value else "not_found",
            source=source if value else "",
            source_page=source_page if value else None,
        )
    sex_match = re.search(
        r"^(?:cins[ıi]?|sex|gender|пол)[ \t]*[:\-]?[ \t]*(qadın|kişi|female|male|f|m|жен|муж)[^\n]*",
        normalized,
        re.IGNORECASE | re.MULTILINE,
    )
    values["sex"] = ExtractedField(
        value=_clean(sex_match.group(1)) if sex_match else "",
        confidence="medium" if sex_match else "not_found",
        source=source if sex_match else "",
        source_page=source_page if sex_match else None,
    )

    combined_birth = re.search(
        r"^doğum\s*tarixi\s*,\s*doğulduğu\s*yer[ \t]*:[ \t]*([^,\n]+),[ \t]*(.+)$",
        normalized,
        re.IGNORECASE | re.MULTILINE,
    )
    if combined_birth:
        values["date_of_birth"] = ExtractedField(
            value=_clean(combined_birth.group(1)),
            confidence="medium",
            source=source,
            source_page=source_page,
        )
        values["birth_place"] = ExtractedField(
            value=_clean(combined_birth.group(2)),
            confidence="medium",
            source=source,
            source_page=source_page,
        )

    heading_name = re.search(
        r"^ARAYIŞ[ \t]*\n([^\n]{3,100})\nMüraciət",
        normalized,
        re.IGNORECASE | re.MULTILINE,
    )
    if heading_name and not values["full_name"].value:
        values["full_name"] = ExtractedField(
            value=_clean(heading_name.group(1)),
            confidence="medium",
            source=source,
            source_page=source_page,
        )

    combined_passport_dates = re.search(
        r"^verildiyi\s*tarix\s*-\s*etibarlılıdır[ \t]*:[ \t]*(.+?)[ \t]+ildən\s*-[ \t]*(.+?)[ \t]+ilədək$",
        normalized,
        re.IGNORECASE | re.MULTILINE,
    )
    if combined_passport_dates:
        values["passport_issue_date"] = ExtractedField(
            value=f"{_clean(combined_passport_dates.group(1))} il",
            confidence="medium",
            source=source,
            source_page=source_page,
        )
        values["passport_expiry"] = ExtractedField(
            value=f"{_clean(combined_passport_dates.group(2))} il",
            confidence="medium",
            source=source,
            source_page=source_page,
        )

    for key, start_label, end_label in [
        ("basis_note", "Vəsatətin əsası haqqında qeyd", "Xüsusi qeyd"),
        (
            "special_note",
            "Xüsusi qeyd",
            "Müvəqqəti yaşamaq üçün icazənin müddətinin uzadılmasına əsas olmuş hallar",
        ),
        ("conclusion", "NƏTİCƏ", "idarə rəisi"),
    ]:
        block = re.search(
            rf"^{start_label}[ \t]*:?[ \t]*(.*?)(?=^{end_label})",
            normalized,
            re.IGNORECASE | re.MULTILINE | re.DOTALL,
        )
        if block and _clean(block.group(1)):
            values[key] = ExtractedField(
                value=_clean(block.group(1)),
                confidence="medium",
                source=source,
                source_page=source_page,
            )
    return PersonData(**values)


def _image_part(image_bytes: bytes) -> dict:
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return {
        "type": "input_image",
        "image_url": f"data:image/png;base64,{encoded}",
        "detail": "high",
    }


def vision_extract(pages: list[PageContent], document_name: str) -> tuple[str, PersonData]:
    from openai import OpenAI

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    prompt = (
        "Sən miqrasiya sənədlərini vizual oxuyan dəqiq sənəd-analitika köməkçisisən. "
        "Bu bir sənədə aid səhifələrdir. Sənədin növünü tanı: passport, application_form, "
        "birth_certificate, medical_certificate, school_certificate, notarized_application, "
        "property_document, residence_permit, reference_letter və ya other. Çap mətnini, "
        "cədvəl/xana başlıqlarını, pasportdakı MRZ sətrini və oxuna bilən əlyazmanı birlikdə "
        "dəyərləndir. Yalnız aydın görünən məlumatı yaz, təxmin etmə və hüquqi nəticə uydurma. "
        "Hər dolu sahə üçün həmin məlumatın göründüyü source_page nömrəsini qaytar; tapılmadıqda "
        "value boş, confidence not_found, source_page 0 yaz. Tarixləri sənəddəki formada saxla."
    )
    content: list[dict] = [{"type": "input_text", "text": prompt}]
    for page in pages:
        content.extend(
            [
                {
                    "type": "input_text",
                    "text": f"Sənəd: {document_name}; bu, source_page {page.page_number}-dir.",
                },
                _image_part(page.image),
            ]
        )
    response = client.responses.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        input=[
            {
                "role": "user",
                "content": content,
            }
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "document_fields",
                "strict": True,
                "schema": VISION_SCHEMA,
            }
        },
    )
    raw = json.loads(response.output_text)
    document_type = raw["document_type"]
    fields = raw["fields"]
    return document_type, PersonData(
        **{
            key: ExtractedField(
                value=_clean(value["value"]),
                confidence=value["confidence"] if _clean(value["value"]) else "not_found",
                source=f"{document_name} · Vision ({document_type})"
                if _clean(value["value"])
                else "",
                source_page=value["source_page"] or None,
            )
            for key, value in fields.items()
        }
    )


def merge_extractions(local_fields: PersonData, vision_fields: PersonData) -> PersonData:
    """Keep machine-readable PDF text when vision has no value for a field.

    Some PDFs contain both a selectable text layer and rendered pages.  Vision is
    useful for scanned forms, but a blank vision response must never erase values
    already found in the text layer.
    """
    merged: dict[str, ExtractedField] = {}
    for field_name in PersonData.model_fields:
        vision_value = getattr(vision_fields, field_name)
        local_value = getattr(local_fields, field_name)
        merged[field_name] = vision_value if vision_value.value else local_value
    return PersonData(**merged)


def _merge_field_sets(field_sets: list[PersonData]) -> PersonData:
    merged: dict[str, ExtractedField] = {}
    for field_name in FIELD_NAMES:
        merged[field_name] = next(
            (
                getattr(fields, field_name)
                for fields in field_sets
                if getattr(fields, field_name).value
            ),
            ExtractedField(),
        )
    return PersonData(**merged)


def _classify_document_from_text(text: str) -> str:
    normalized = _normalize_text(text).lower()
    if "arayış" in normalized or "reference" in normalized:
        return "reference_letter"
    if "passport" in normalized or "pasport" in normalized or "p<" in normalized:
        return "passport"
    if "doğum şəhadətnaməsi" in normalized or "birth certificate" in normalized:
        return "birth_certificate"
    if "tibbi" in normalized or "medical" in normalized:
        return "medical_certificate"
    if "məktəb" in normalized or "school" in normalized:
        return "school_certificate"
    if "notarial" in normalized or "notary" in normalized:
        return "notarized_application"
    if "daşınmaz" in normalized or "əmlak" in normalized or "property" in normalized:
        return "property_document"
    if "ərizə" in normalized or "anket" in normalized or "application" in normalized:
        return "application_form"
    return "other"


def _analyze_single_document(
    content: bytes, content_type: str, document_name: str
) -> DocumentResult:
    if content_type == "application/pdf":
        pages = extract_pdf_pages(content)
    elif content_type.startswith("image/"):
        image = normalize_image(content)
        pages = [PageContent(image=image, page_number=1, text=_ocr_image(image))]
    else:
        raise ValueError("Yalnız PDF, JPG və PNG faylları qəbul edilir.")

    local_by_page = [
        local_extract(
            page.text,
            source=f"{document_name} · PDF/OCR mətni",
            source_page=page.page_number,
        )
        for page in pages
    ]
    full_document_text = "\n".join(page.text for page in pages)
    local_fields = _merge_field_sets(
        [*local_by_page, local_extract(full_document_text, source=f"{document_name} · PDF/OCR mətni")]
    )
    document_type = _classify_document_from_text(full_document_text)

    if os.getenv("OPENAI_API_KEY"):
        try:
            vision_type, vision_fields = vision_extract(pages, document_name)
        except Exception:  # noqa: BLE001 - retain OCR/PDF data when vision is unavailable
            return DocumentResult(
                name=document_name,
                document_type=document_type,
                pages=pages,
                fields=local_fields,
                method="ocr" if any(page.text for page in pages) else "pdf_text",
            )
        return DocumentResult(
            name=document_name,
            document_type=vision_type,
            pages=pages,
            fields=merge_extractions(local_fields, vision_fields),
            method="vision",
        )

    return DocumentResult(
        name=document_name,
        document_type=document_type,
        pages=pages,
        fields=local_fields,
        method="ocr" if any(page.text for page in pages) else "pdf_text",
    )


FIELD_DOCUMENT_PRIORITY = {
    "passport_number": ("passport",),
    "passport_issuer": ("passport",),
    "passport_issue_date": ("passport",),
    "passport_expiry": ("passport",),
    "personal_id": ("passport", "residence_permit"),
    "date_of_birth": ("passport", "birth_certificate", "application_form"),
    "birth_place": ("passport", "birth_certificate", "application_form"),
}
CONFIDENCE_WEIGHT = {"high": 3, "medium": 2, "low": 1, "not_found": 0}


def _merge_document_results(documents: list[DocumentResult]) -> PersonData:
    values: dict[str, ExtractedField] = {}
    for field_name in FIELD_NAMES:
        candidates = [
            (document, getattr(document.fields, field_name))
            for document in documents
            if getattr(document.fields, field_name).value
        ]
        preferred_types = FIELD_DOCUMENT_PRIORITY.get(field_name, ())
        candidates.sort(
            key=lambda item: (
                item[0].document_type in preferred_types,
                CONFIDENCE_WEIGHT[item[1].confidence],
            ),
            reverse=True,
        )
        values[field_name] = candidates[0][1] if candidates else ExtractedField()
    return PersonData(**values)


def _comparison_value(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", _normalize_text(value).lower())


def build_cross_checks(documents: list[DocumentResult]) -> list[CrossCheck]:
    checks: list[CrossCheck] = []
    for field_name in (
        "full_name",
        "passport_number",
        "passport_issue_date",
        "personal_id",
        "date_of_birth",
    ):
        found: dict[str, list[str]] = {}
        for document in documents:
            field = getattr(document.fields, field_name)
            if not field.value:
                continue
            found.setdefault(_comparison_value(field.value), []).append(
                f"{document.name}, səhifə {field.source_page or '?'}: {field.value}"
            )
        values = list(found.values())
        if not values:
            status = "missing"
            message = "Məlumat sənədlərdə tapılmadı."
        elif len(values) == 1 and len(values[0]) > 1:
            status = "match"
            message = "Bir neçə sənəddə eyni məlumat təsdiqləndi."
        elif len(values) > 1:
            status = "conflict"
            message = "Sənədlər arasında uyğunsuzluq var; operator yoxlamalıdır."
        else:
            status = "single_source"
            message = "Yalnız bir sənəd mənbəsində tapıldı."
        checks.append(
            CrossCheck(
                field=field_name,
                status=status,
                message=message,
                sources=[source for group in values for source in group],
            )
        )
    return checks


def analyze_documents(documents: list[tuple]) -> ExtractionResponse:
    analyzed: list[DocumentResult] = []
    for index, document in enumerate(documents, start=1):
        content, content_type, *rest = document
        name = rest[0] if rest else f"Sənəd {index}"
        analyzed.append(_analyze_single_document(content, content_type, name))

    all_text = "\n".join(
        page.text for document in analyzed for page in document.pages if page.text
    )
    used_vision = any(document.method == "vision" for document in analyzed)
    vision_unavailable = bool(os.getenv("OPENAI_API_KEY")) and not used_vision
    notes = [
        f"{len(analyzed)} sənəd və {sum(len(document.pages) for document in analyzed)} səhifə analiz edildi.",
        "Pasport nömrəsi, şəxsi kod, ad-soyad və doğum tarixi üzrə çarpaz yoxlama nəticələrini nəzərdən keçirin.",
        "Hüquqi nəticə avtomatik qəbul edilmir; operator tərəfindən yoxlanılmalıdır.",
    ]
    if vision_unavailable:
        notes.insert(
            1,
            "Vision əlçatan olmadı; PDF mətn və lokal OCR nəticələri saxlanıldı.",
        )
    elif not os.getenv("OPENAI_API_KEY"):
        notes.insert(
            1,
            "Vision açarı qurulmayıb; seçilə bilən PDF mətni və lokal OCR istifadə edildi.",
        )

    return ExtractionResponse(
        fields=_merge_document_results(analyzed),
        extraction_method="vision" if used_vision else "local_text",
        notes=notes,
        text_preview=_clean(all_text)[:2500],
        documents=[
            DocumentSummary(
                name=document.name,
                document_type=document.document_type,
                page_count=len(document.pages),
                extraction_method=document.method,
            )
            for document in analyzed
        ],
        cross_checks=build_cross_checks(analyzed),
    )


def analyze_document(content: bytes, content_type: str) -> ExtractionResponse:
    return analyze_documents([(content, content_type)])
