from typing import Literal

from pydantic import BaseModel, Field


class ExtractedField(BaseModel):
    value: str = ""
    confidence: Literal["high", "medium", "low", "not_found"] = "not_found"
    source: str = ""
    source_page: int | None = None


class DocumentSummary(BaseModel):
    name: str
    document_type: str = "naməlum"
    page_count: int = 1
    extraction_method: Literal["vision", "ocr", "pdf_text"] = "pdf_text"


class CrossCheck(BaseModel):
    field: str
    status: Literal["match", "conflict", "single_source", "missing"]
    message: str
    sources: list[str] = Field(default_factory=list)


class PersonData(BaseModel):
    full_name: ExtractedField = Field(default_factory=ExtractedField)
    application_date: ExtractedField = Field(default_factory=ExtractedField)
    date_of_birth: ExtractedField = Field(default_factory=ExtractedField)
    birth_place: ExtractedField = Field(default_factory=ExtractedField)
    sex: ExtractedField = Field(default_factory=ExtractedField)
    citizenship: ExtractedField = Field(default_factory=ExtractedField)
    personal_id: ExtractedField = Field(default_factory=ExtractedField)
    passport_number: ExtractedField = Field(default_factory=ExtractedField)
    passport_issuer: ExtractedField = Field(default_factory=ExtractedField)
    passport_issue_date: ExtractedField = Field(default_factory=ExtractedField)
    passport_expiry: ExtractedField = Field(default_factory=ExtractedField)
    visa_number: ExtractedField = Field(default_factory=ExtractedField)
    entry_date: ExtractedField = Field(default_factory=ExtractedField)
    phone: ExtractedField = Field(default_factory=ExtractedField)
    email: ExtractedField = Field(default_factory=ExtractedField)
    address: ExtractedField = Field(default_factory=ExtractedField)
    application_type: ExtractedField = Field(default_factory=ExtractedField)
    permit_basis: ExtractedField = Field(default_factory=ExtractedField)
    basis_note: ExtractedField = Field(default_factory=ExtractedField)
    special_note: ExtractedField = Field(default_factory=ExtractedField)
    temporary_permit_history: ExtractedField = Field(default_factory=ExtractedField)
    permanent_permit_history: ExtractedField = Field(default_factory=ExtractedField)
    conclusion: ExtractedField = Field(default_factory=ExtractedField)


class ExtractionResponse(BaseModel):
    fields: PersonData
    extraction_method: Literal["vision", "local_text"]
    notes: list[str] = Field(default_factory=list)
    text_preview: str = ""
    documents: list[DocumentSummary] = Field(default_factory=list)
    cross_checks: list[CrossCheck] = Field(default_factory=list)


class CertificateData(BaseModel):
    recipient: str = ""
    full_name: str = ""
    application_date: str = ""
    citizenship: str = ""
    sex: str = ""
    passport_number: str = ""
    passport_issuer: str = ""
    passport_issue_date: str = ""
    passport_expiry: str = ""
    date_of_birth: str = ""
    birth_place: str = ""
    permit_basis: str = ""
    basis_note: str = ""
    special_note: str = ""
    temporary_permit_history: str = ""
    permanent_permit_history: str = ""
    conclusion: str = ""
    manager_title: str = "İdarə rəisi"
    manager_name: str = ""
