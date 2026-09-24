import io

import pytest
import pymupdf
from PIL import Image

from app import extractor
from app.extractor import analyze_document, local_extract, normalize_image
from app.schemas import PersonData


def test_email_and_phone_are_extracted():
    result = local_extract("E-poçt: test@example.com Telefon: +994 50 123 45 67")
    assert result.email.value == "test@example.com"
    assert "+994" in result.phone.value


def test_unseen_fields_are_blank():
    result = local_extract("sadə mətn")
    assert result.passport_number.value == ""
    assert result.passport_number.confidence == "not_found"


def test_multiline_fields_stop_at_the_end_of_their_line():
    result = local_extract(
        "Ad: Leyla Məmmədova\nVətəndaşlıq: Azərbaycan\nÜnvan: Bakı şəhəri"
    )

    assert result.full_name.value == "Leyla Məmmədova"
    assert result.citizenship.value == "Azərbaycan"
    assert result.address.value == "Bakı şəhəri"


def test_certificate_specific_fields_are_extracted():
    result = local_extract(
        "Müraciət etdiyi tarix: 10 yanvar 2020-ci il\n"
        "Verən orqan: FMS 24008\n"
        "Vəsatətin əsası: Əyani təhsil"
    )

    assert result.application_date.value == "10 yanvar 2020-ci il"
    assert result.passport_issuer.value == "FMS 24008"
    assert result.permit_basis.value == "Əyani təhsil"


def test_combined_birth_line_is_split_into_date_and_place():
    result = local_extract(
        "Doğum tarixi, doğulduğu yer: 04 may 2005-ci il, Rusiya Federasiyası"
    )

    assert result.date_of_birth.value == "04 may 2005-ci il"
    assert result.birth_place.value == "Rusiya Federasiyası"


def test_pdf_font_confusables_and_combined_passport_dates_are_normalized():
    result = local_extract(
        "Vәtәndaşlığı: Rusiya Federasiyası\n"
        "Cinsi: qadın\n"
        "Verildiyi tarix-etibarlılıdır: 22 fevral 2011\u00adci ildən- "
        "22 fevral 2021\u00adci ilədək"
    )

    assert result.citizenship.value == "Rusiya Federasiyası"
    assert result.sex.value == "qadın"
    assert result.passport_issue_date.value == "22 fevral 2011-ci il"
    assert result.passport_expiry.value == "22 fevral 2021-ci il"


def test_empty_text_field_does_not_consume_the_next_line():
    result = local_extract("Ad:\nVətəndaşlıq: Azərbaycan")

    assert result.full_name.value == ""
    assert result.citizenship.value == "Azərbaycan"


def test_address_is_not_mistaken_for_short_name_label():
    result = local_extract("Address: 10 Main Street")

    assert result.full_name.value == ""
    assert result.address.value == "10 Main Street"


def test_jpeg_is_normalized_to_png_for_vision():
    source = io.BytesIO()
    Image.new("RGB", (2, 2), color="white").save(source, format="JPEG")

    normalized = normalize_image(source.getvalue())

    assert normalized.startswith(b"\x89PNG\r\n\x1a\n")


def test_invalid_image_is_rejected_without_calling_vision():
    with pytest.raises(ValueError, match="zədəlidir"):
        analyze_document(b"not an image", "image/jpeg")


def test_blank_vision_result_does_not_erase_selectable_pdf_text(monkeypatch):
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text(
        (72, 72),
        "Name: Amina Abbasova\nPassport number: P1234567\nCitizenship: Russia",
    )
    content = document.tobytes()
    document.close()

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(extractor, "vision_extract", lambda _images: PersonData())

    result = analyze_document(content, "application/pdf")

    assert result.extraction_method == "vision"
    assert result.fields.full_name.value == "Amina Abbasova"
    assert result.fields.passport_number.value == "P1234567"
    assert result.fields.citizenship.value == "Russia"
