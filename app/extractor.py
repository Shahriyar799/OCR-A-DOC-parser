import base64
import io
import json
import os
import re
from dataclasses import dataclass

import fitz
from PIL import Image

from .schemas import ExtractedField, ExtractionResponse, PersonData


FIELD_LABELS = {
    "full_name": r"(?:soyad[ıi]?\s*,?\s*ad[ıi]?\s*,?\s*ata\s*ad[ıi]?|full\s*name|name|фамилия.*имя)\s*[:\-]?\s*([^\n]{3,100})",
    "date_of_birth": r"(?:doğum\s*tarixi|date\s*of\s*birth|дата\s*рождения)\s*[:\-]?\s*([0-3]?\d[.\-/][01]?\d[.\-/](?:19|20)\d{2})",
    "citizenship": r"(?:vətəndaşlıq|citizenship|гражданств[оа])\s*[:\-]?\s*([^\n]{3,60})",
    "personal_id": r"(?:f[iİ]n\s*(?:kod)?|personal\s*(?:id|number)|персонал(?:ьный)?\s*(?:код|номер))\s*[:\-]?\s*([A-Z0-9\-]{5,20})",
    "passport_number": r"(?:passport\s*(?:no|number)?|pasport\s*(?:№|no|number)?|паспорт\s*(?:№|номер)?)\s*[:\-]?\s*([A-Z0-9]{5,16})",
    "passport_expiry": r"(?:expiry|valid\s*until|bitmə\s*tarixi|etibarlıdır|действителен\s*до)\s*[:\-]?\s*([0-3]?\d[.\-/][01]?\d[.\-/](?:19|20)\d{2})",
    "visa_number": r"(?:visa\s*(?:no|number)?|viza\s*(?:№|no|number)?|виза\s*(?:№|номер)?)\s*[:\-]?\s*([A-Z0-9\-]{5,20})",
    "entry_date": r"(?:entry\s*date|giriş\s*tarixi|дата\s*въезда)\s*[:\-]?\s*([0-3]?\d[.\-/][01]?\d[.\-/](?:19|20)\d{2})",
    "phone": r"(?:telefon|phone|tel\.?|моб(?:ильный)?)\s*[:\-]?\s*(\+?[0-9()\-\s]{7,25})",
    "email": r"\b([A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,})\b",
    "address": r"(?:yaşayış\s*ünvanı|ünvan|address|адрес)\s*[:\-]?\s*([^\n]{5,180})",
    "application_type": r"(?:müraciət(?:in)?\s*növü|application\s*type|вид\s*заявления)\s*[:\-]?\s*([^\n]{3,100})",
}


VISION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "full_name": {"type": "string"}, "date_of_birth": {"type": "string"},
        "sex": {"type": "string"}, "citizenship": {"type": "string"},
        "personal_id": {"type": "string"}, "passport_number": {"type": "string"},
        "passport_expiry": {"type": "string"}, "visa_number": {"type": "string"},
        "entry_date": {"type": "string"}, "phone": {"type": "string"},
        "email": {"type": "string"}, "address": {"type": "string"},
        "application_type": {"type": "string"},
    },
    "required": ["full_name", "date_of_birth", "sex", "citizenship", "personal_id", "passport_number", "passport_expiry", "visa_number", "entry_date", "phone", "email", "address", "application_type"],
}


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" :;,-")


def extract_text_from_pdf(content: bytes) -> tuple[str, list[bytes]]:
    document = fitz.open(stream=content, filetype="pdf")
    text = "\n".join(page.get_text("text") for page in document)
    images: list[bytes] = []
    for page in list(document)[:3]:
        pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
        images.append(pix.tobytes("png"))
    document.close()
    return text, images


def local_extract(text: str) -> PersonData:
    normalized = _clean(text)
    values: dict[str, ExtractedField] = {}
    for key, pattern in FIELD_LABELS.items():
        match = re.search(pattern, normalized, re.IGNORECASE)
        value = _clean(match.group(1)) if match else ""
        values[key] = ExtractedField(
            value=value,
            confidence="medium" if value else "not_found",
            source="PDF mətni" if value else "",
        )
    sex_match = re.search(r"(?:cins|sex|gender|пол)\s*[:\-]?\s*(qadın|kişi|female|male|f|m|жен|муж)[^\n]*", normalized, re.IGNORECASE)
    values["sex"] = ExtractedField(
        value=_clean(sex_match.group(1)) if sex_match else "",
        confidence="medium" if sex_match else "not_found",
        source="PDF mətni" if sex_match else "",
    )
    return PersonData(**values)


def _image_part(image_bytes: bytes) -> dict:
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return {"type": "input_image", "image_url": f"data:image/png;base64,{encoded}", "detail": "high"}


def vision_extract(images: list[bytes]) -> PersonData:
    from openai import OpenAI

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    prompt = (
        "Sən miqrasiya sənədlərindən məlumat çıxaran köməkçisən. Şəkillərdəki "
        "anket və pasport məlumatlarını oxu. Yalnız açıq görünən məlumatı yaz; "
        "təxmin etmə. Tarixləri sənəddəki formada saxla. Sahə yoxdursa boş sətir qaytar."
    )
    response = client.responses.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        input=[{"role": "user", "content": [{"type": "input_text", "text": prompt}, *[_image_part(i) for i in images]]}],
        text={"format": {"type": "json_schema", "name": "document_fields", "strict": True, "schema": VISION_SCHEMA}},
    )
    raw = json.loads(response.output_text)
    return PersonData(**{
        key: ExtractedField(value=_clean(value), confidence="high" if _clean(value) else "not_found", source="Sənəd şəkli")
        for key, value in raw.items()
    })


def analyze_document(content: bytes, content_type: str) -> ExtractionResponse:
    if content_type == "application/pdf":
        text, images = extract_text_from_pdf(content)
    elif content_type.startswith("image/"):
        text, images = "", [content]
    else:
        raise ValueError("Yalnız PDF, JPG və PNG faylları qəbul edilir.")

    if os.getenv("OPENAI_API_KEY") and images:
        fields = vision_extract(images)
        method = "vision"
        notes = ["Şəkil üzrə oxunuş aparıldı. Vacib sahələri sənəd əsasında yoxlayın."]
    else:
        fields = local_extract(text)
        method = "local_text"
        notes = [
            "Vision açarı qurulmayıb; yalnız PDF-dəki seçilə bilən mətn analiz edildi.",
            "Skan edilmiş pasport/anket üçün OPENAI_API_KEY əlavə edin.",
        ]

    return ExtractionResponse(fields=fields, extraction_method=method, notes=notes, text_preview=_clean(text)[:2500])
