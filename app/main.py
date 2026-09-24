import os
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .certificate import build_certificate_pdf
from .extractor import analyze_document, analyze_documents
from .schemas import CertificateData, ExtractionResponse

BASE_DIR = Path(__file__).resolve().parent
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_MB", "15")) * 1024 * 1024
ALLOWED_TYPES = {"application/pdf", "image/jpeg", "image/png"}
MAX_FILES_PER_PERSON = 8
MAX_TOTAL_BYTES = 40 * 1024 * 1024

app = FastAPI(title="Sənəd Məlumat Çıxarışı", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


@app.middleware("http")
async def no_store(request: Request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html", context={})


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/extract", response_model=ExtractionResponse)
async def extract_document(file: Annotated[UploadFile, File()]):
    content, content_type = await _read_upload(file)
    return _analyze_or_error([(content, content_type)])


@app.post("/api/extract-many", response_model=ExtractionResponse)
async def extract_many(files: Annotated[list[UploadFile], File()]):
    if not files:
        raise HTTPException(400, "Ən azı bir sənəd seçilməlidir.")
    if len(files) > MAX_FILES_PER_PERSON:
        raise HTTPException(
            413, f"Bir əcnəbi üçün ən çox {MAX_FILES_PER_PERSON} sənəd yüklənə bilər."
        )

    documents: list[tuple[bytes, str]] = []
    total_size = 0
    for file in files:
        content, content_type = await _read_upload(file)
        total_size += len(content)
        if total_size > MAX_TOTAL_BYTES:
            raise HTTPException(
                413, "Sənədlərin ümumi ölçüsü 40 MB-dan çox ola bilməz."
            )
        documents.append((content, content_type))
    return _analyze_or_error(documents)


@app.post("/api/certificate")
async def create_certificate(data: CertificateData):
    try:
        pdf = build_certificate_pdf(data)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    except Exception as error:
        raise HTTPException(500, "Arayış PDF-i yaradıla bilmədi.") from error
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="arayis.pdf"'},
    )


async def _read_upload(file: UploadFile) -> tuple[bytes, str]:
    content_type = file.content_type or ""
    if content_type not in ALLOWED_TYPES:
        raise HTTPException(415, "Yalnız PDF, JPG və PNG faylları yüklənə bilər.")
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if not content:
        raise HTTPException(400, "Boş fayl yüklənib.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            413,
            f"Fayl ölçüsü {MAX_UPLOAD_BYTES // 1024 // 1024} MB-dan çox ola bilməz.",
        )
    return content, content_type


def _analyze_or_error(documents: list[tuple[bytes, str]]) -> ExtractionResponse:
    try:
        if len(documents) == 1:
            return analyze_document(*documents[0])
        return analyze_documents(documents)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    except Exception:  # noqa: BLE001 - keep provider and parser failures behind the API boundary
        # Do not expose document text, provider errors, or credentials to the client.
        raise HTTPException(
            502, "Sənəd oxuna bilmədi. Faylı və API sazlamalarını yoxlayın."
        )
