import os
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .extractor import analyze_document
from .schemas import ExtractionResponse

BASE_DIR = Path(__file__).resolve().parent
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_MB", "15")) * 1024 * 1024
ALLOWED_TYPES = {"application/pdf", "image/jpeg", "image/png"}

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
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/extract", response_model=ExtractionResponse)
async def extract_document(file: UploadFile = File(...)):
    content_type = file.content_type or ""
    if content_type not in ALLOWED_TYPES:
        raise HTTPException(415, "Yalnız PDF, JPG və PNG faylları yüklənə bilər.")
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if not content:
        raise HTTPException(400, "Boş fayl yüklənib.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"Fayl ölçüsü {MAX_UPLOAD_BYTES // 1024 // 1024} MB-dan çox ola bilməz.")
    try:
        return analyze_document(content, content_type)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    except Exception:
        # Do not expose document text, provider errors, or credentials to the client.
        raise HTTPException(502, "Sənəd oxuna bilmədi. Faylı və API sazlamalarını yoxlayın.")
