import pymupdf
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _text_pdf(text: str) -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    content = document.tobytes()
    document.close()
    return content


def test_home_and_health_endpoints_are_available():
    home = client.get("/")
    health = client.get("/health")

    assert home.status_code == 200
    assert "Sənəddən məlumat çıxarışı" in home.text
    assert home.headers["cache-control"] == "no-store, max-age=0"
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}


def test_unsupported_file_type_is_rejected():
    response = client.post(
        "/api/extract",
        files={"file": ("document.txt", b"plain text", "text/plain")},
    )

    assert response.status_code == 415


def test_corrupt_image_is_rejected_without_leaking_an_internal_error():
    response = client.post(
        "/api/extract",
        files={"file": ("document.jpg", b"not an image", "image/jpeg")},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Şəkil faylı zədəlidir və ya dəstəklənmir."}


def test_multiple_documents_are_combined_for_one_person(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    response = client.post(
        "/api/extract-many",
        files=[
            (
                "files",
                ("identity.pdf", _text_pdf("Name: Amina Abbasova"), "application/pdf"),
            ),
            (
                "files",
                (
                    "contact.pdf",
                    _text_pdf("Phone: +994 50 123 45 67"),
                    "application/pdf",
                ),
            ),
        ],
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["fields"]["full_name"]["value"] == "Amina Abbasova"
    assert "+994" in payload["fields"]["phone"]["value"]


def test_cross_check_marks_conflicting_passport_issue_dates(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    response = client.post(
        "/api/extract-many",
        files=[
            (
                "files",
                (
                    "application.pdf",
                    _text_pdf(
                        "Passport number: P1234567\nDate of issue: 01.01.2020"
                    ),
                    "application/pdf",
                ),
            ),
            (
                "files",
                (
                    "passport.pdf",
                    _text_pdf(
                        "Passport number: P1234567\nDate of issue: 02.01.2020"
                    ),
                    "application/pdf",
                ),
            ),
        ],
    )

    assert response.status_code == 200
    checks = {item["field"]: item for item in response.json()["cross_checks"]}
    assert checks["passport_number"]["status"] == "match"
    assert checks["passport_issue_date"]["status"] == "conflict"


def test_certificate_endpoint_returns_a_two_page_pdf():
    response = client.post(
        "/api/certificate",
        json={
            "recipient": "Baş idarənin rəisi",
            "full_name": "Amina Abbasova",
            "application_date": "10 yanvar 2020-ci il",
            "citizenship": "Rusiya Federasiyası",
            "sex": "qadın",
            "passport_number": "713370808",
            "passport_issuer": "FMS 24008",
            "date_of_birth": "04 may 2005-ci il",
            "birth_place": "Rusiya Federasiyası",
            "permit_basis": "Əyani təhsil",
            "conclusion": "Müvəqqəti yaşamaq üçün icazə verilə bilər.",
            "manager_name": "M. Nurullah",
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    document = pymupdf.open(stream=response.content, filetype="pdf")
    assert document.page_count == 2
    text = "\n".join(page.get_text() for page in document)
    assert "Amina Abbasova" in text
    assert "NƏTİCƏ" in text
