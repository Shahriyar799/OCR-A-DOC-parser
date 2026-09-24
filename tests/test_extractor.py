from app.extractor import local_extract


def test_email_and_phone_are_extracted():
    result = local_extract("E-poçt: test@example.com Telefon: +994 50 123 45 67")
    assert result.email.value == "test@example.com"
    assert "+994" in result.phone.value


def test_unseen_fields_are_blank():
    result = local_extract("sadə mətn")
    assert result.passport_number.value == ""
    assert result.passport_number.confidence == "not_found"
