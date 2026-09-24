import base64
import io
import json
import os
import re

import pymupdf
from PIL import Image

from .schemas import ExtractedField, ExtractionResponse, PersonData

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


VISION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "full_name": {"type": "string"},
        "application_date": {"type": "string"},
        "date_of_birth": {"type": "string"},
        "birth_place": {"type": "string"},
        "sex": {"type": "string"},
        "citizenship": {"type": "string"},
        "personal_id": {"type": "string"},
        "passport_number": {"type": "string"},
        "passport_issuer": {"type": "string"},
        "passport_issue_date": {"type": "string"},
        "passport_expiry": {"type": "string"},
        "visa_number": {"type": "string"},
        "entry_date": {"type": "string"},
        "phone": {"type": "string"},
        "email": {"type": "string"},
        "address": {"type": "string"},
        "application_type": {"type": "string"},
        "permit_basis": {"type": "string"},
        "basis_note": {"type": "string"},
        "special_note": {"type": "string"},
        "temporary_permit_history": {"type": "string"},
        "permanent_permit_history": {"type": "string"},
        "conclusion": {"type": "string"},
    },
    "required": [
        "full_name",
        "application_date",
        "date_of_birth",
        "birth_place",
        "sex",
        "citizenship",
        "personal_id",
        "passport_number",
        "passport_issuer",
        "passport_issue_date",
        "passport_expiry",
        "visa_number",
        "entry_date",
        "phone",
        "email",
        "address",
        "application_type",
        "permit_basis",
        "basis_note",
        "special_note",
        "temporary_permit_history",
        "permanent_permit_history",
        "conclusion",
    ],
}


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


def extract_text_from_pdf(content: bytes) -> tuple[str, list[bytes]]:
    document = pymupdf.open(stream=content, filetype="pdf")
    text = "\n".join(page.get_text("text") for page in document)
    images: list[bytes] = []
    for page in list(document)[:3]:
        pix = page.get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5), alpha=False)
        images.append(pix.tobytes("png"))
    document.close()
    return text, images


def local_extract(text: str) -> PersonData:
    normalized = _normalize_text(text)
    values: dict[str, ExtractedField] = {}
    for key, pattern in FIELD_LABELS.items():
        match = re.search(pattern, normalized, re.IGNORECASE | re.MULTILINE)
        value = _clean(match.group(1)) if match else ""
        values[key] = ExtractedField(
            value=value,
            confidence="medium" if value else "not_found",
            source="PDF mətni" if value else "",
        )
    sex_match = re.search(
        r"^(?:cins[ıi]?|sex|gender|пол)[ \t]*[:\-]?[ \t]*(qadın|kişi|female|male|f|m|жен|муж)[^\n]*",
        normalized,
        re.IGNORECASE | re.MULTILINE,
    )
    values["sex"] = ExtractedField(
        value=_clean(sex_match.group(1)) if sex_match else "",
        confidence="medium" if sex_match else "not_found",
        source="PDF mətni" if sex_match else "",
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
            source="PDF mətni",
        )
        values["birth_place"] = ExtractedField(
            value=_clean(combined_birth.group(2)),
            confidence="medium",
            source="PDF mətni",
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
            source="PDF mətni",
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
            source="PDF mətni",
        )
        values["passport_expiry"] = ExtractedField(
            value=f"{_clean(combined_passport_dates.group(2))} il",
            confidence="medium",
            source="PDF mətni",
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
                source="PDF mətni",
            )
    return PersonData(**values)


def _image_part(image_bytes: bytes) -> dict:
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return {
        "type": "input_image",
        "image_url": f"data:image/png;base64,{encoded}",
        "detail": "high",
    }


def vision_extract(images: list[bytes]) -> PersonData:
    from openai import OpenAI

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    prompt = (
        "Sən miqrasiya sənədlərindən məlumat çıxaran köməkçisən. Şəkillərdəki "
        "anket, pasport, qeydiyyat, MYİ və DYİ məlumatlarını oxu. Bir neçə şəkil eyni "
        "şəxsə aid ola bilər. Yalnız açıq görünən məlumatı yaz; təxmin etmə və hüquqi "
        "nəticə yaratma. Nəticə yalnız sənəddə açıq yazılıbsa çıxarılsın. Tarixləri "
        "sənəddəki formada saxla. Sahə yoxdursa boş sətir qaytar."
    )
    response = client.responses.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    *[_image_part(i) for i in images],
                ],
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
    return PersonData(
        **{
            key: ExtractedField(
                value=_clean(value),
                confidence="high" if _clean(value) else "not_found",
                source="Sənəd şəkli",
            )
            for key, value in raw.items()
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


def analyze_documents(documents: list[tuple[bytes, str]]) -> ExtractionResponse:
    texts: list[str] = []
    images: list[bytes] = []
    for content, content_type in documents:
        if content_type == "application/pdf":
            document_text, document_images = extract_text_from_pdf(content)
            texts.append(document_text)
            images.extend(document_images)
        elif content_type.startswith("image/"):
            images.append(normalize_image(content))
        else:
            raise ValueError("Yalnız PDF, JPG və PNG faylları qəbul edilir.")

    text = "\n".join(texts)

    local_fields = local_extract(text)

    if os.getenv("OPENAI_API_KEY") and images:
        try:
            vision_fields = vision_extract(images[:12])
        except Exception:  # noqa: BLE001 - preserve usable PDF text when vision is unavailable
            fields = local_fields
            method = "local_text"
            notes = [
                "Şəkil üzrə oxuma əlçatan olmadı; seçilə bilən PDF mətni əsasında nəticə göstərilir.",
                "Hüquqi nəticə avtomatik qəbul edilmir; operator tərəfindən yoxlanılmalıdır.",
            ]
        else:
            fields = merge_extractions(local_fields, vision_fields)
            method = "vision"
            notes = [
                f"{len(documents)} sənəd birlikdə oxundu. Vision və PDF mətni nəticələri birləşdirildi.",
                "Hüquqi nəticə avtomatik qəbul edilmir; operator tərəfindən yoxlanılmalıdır.",
            ]
    else:
        fields = local_fields
        method = "local_text"
        notes = [
            f"Vision açarı qurulmayıb; {len(documents)} sənəddə yalnız seçilə bilən PDF mətni analiz edildi.",
            "Skan edilmiş pasport/anket üçün OPENAI_API_KEY əlavə edin.",
        ]

    return ExtractionResponse(
        fields=fields,
        extraction_method=method,
        notes=notes,
        text_preview=_clean(text)[:2500],
    )


def analyze_document(content: bytes, content_type: str) -> ExtractionResponse:
    return analyze_documents([(content, content_type)])
