"""Temporary protected demo for exercising the same document engine in a browser."""

import mimetypes
import os
from pathlib import Path

import gradio as gr

from .extractor import analyze_document


def extract_for_demo(file_path: str | None) -> dict:
    if not file_path:
        return {"error": "Əvvəlcə PDF, JPG və ya PNG faylı seçin."}

    path = Path(file_path)
    mime_type = mimetypes.guess_type(path.name)[0] or ""
    if mime_type == "image/jpg":
        mime_type = "image/jpeg"

    try:
        result = analyze_document(path.read_bytes(), mime_type)
        payload = result.model_dump()
        # The extracted raw text may contain personal data and is not useful for this demo view.
        payload.pop("text_preview", None)
        return payload
    except Exception:  # noqa: BLE001 - do not leak provider details or document data
        return {"error": "Sənəd oxuna bilmədi. Faylı və API sazlamalarını yoxlayın."}


with gr.Blocks(title="Sənəd Məlumat Çıxarışı — Lokal Demo") as demo:
    gr.Markdown(
        "# Sənəd məlumat çıxarışı\nBu, lokal mühərrikin müvəqqəti yoxlama versiyasıdır."
    )
    gr.Markdown(
        "⚠️ Yalnız test sənədlərindən istifadə edin. Nəticəni operator yoxlamalıdır."
    )
    with gr.Row():
        document = gr.File(
            label="PDF, JPG və ya PNG",
            file_types=[".pdf", ".jpg", ".jpeg", ".png"],
            type="filepath",
        )
        run = gr.Button("Məlumatları çıxar", variant="primary")
    result = gr.JSON(label="Strukturlaşdırılmış nəticə")
    run.click(extract_for_demo, inputs=document, outputs=result)


if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=int(os.getenv("DEMO_PORT", "8099")),
        share=True,
        auth=(os.getenv("DEMO_USER", "demo"), os.environ["DEMO_PASSWORD"]),
        auth_message="Bu müvəqqəti yoxlama mühitidir.",
        show_error=False,
    )
