from typing import Literal

from pydantic import BaseModel, Field


class ExtractedField(BaseModel):
    value: str = ""
    confidence: Literal["high", "medium", "low", "not_found"] = "not_found"
    source: str = ""


class PersonData(BaseModel):
    full_name: ExtractedField = Field(default_factory=ExtractedField)
    date_of_birth: ExtractedField = Field(default_factory=ExtractedField)
    sex: ExtractedField = Field(default_factory=ExtractedField)
    citizenship: ExtractedField = Field(default_factory=ExtractedField)
    personal_id: ExtractedField = Field(default_factory=ExtractedField)
    passport_number: ExtractedField = Field(default_factory=ExtractedField)
    passport_expiry: ExtractedField = Field(default_factory=ExtractedField)
    visa_number: ExtractedField = Field(default_factory=ExtractedField)
    entry_date: ExtractedField = Field(default_factory=ExtractedField)
    phone: ExtractedField = Field(default_factory=ExtractedField)
    email: ExtractedField = Field(default_factory=ExtractedField)
    address: ExtractedField = Field(default_factory=ExtractedField)
    application_type: ExtractedField = Field(default_factory=ExtractedField)


class ExtractionResponse(BaseModel):
    fields: PersonData
    extraction_method: Literal["vision", "local_text"]
    notes: list[str] = []
    text_preview: str = ""
