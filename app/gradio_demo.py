"""Temporary protected demo for exercising the same document engine in a browser."""

import mimetypes
import os
import json
import uuid
import threading
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
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
        backend_url = os.getenv("DEMO_BACKEND_URL", "").rstrip("/")
        if backend_url:
            boundary = f"----gradio-{uuid.uuid4().hex}"
            body = b"".join(
                (
                    f"--{boundary}\r\n".encode(),
                    (
                        'Content-Disposition: form-data; name="file"; '
                        f'filename="{path.name}"\r\n'
                    ).encode(),
                    f"Content-Type: {mime_type}\r\n\r\n".encode(),
                    path.read_bytes(),
                    f"\r\n--{boundary}--\r\n".encode(),
                )
            )
            request = Request(
                f"{backend_url}/api/extract",
                data=body,
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
                method="POST",
            )
            # First use can need several minutes while local OCR models warm up.
            # Keep the operator-facing request alive rather than discarding a
            # completed server result as a generic Gradio error.
            with urlopen(request, timeout=600) as response:  # noqa: S310 - configured operator backend
                payload = json.loads(response.read().decode("utf-8"))
                # The operator view should present structured fields only;
                # raw OCR text may contain unnecessary personal data.
                payload.pop("text_preview", None)
                return payload

        result = analyze_document(path.read_bytes(), mime_type)
        payload = result.model_dump()
        # The extracted raw text may contain personal data and is not useful for this demo view.
        payload.pop("text_preview", None)
        return payload
    except HTTPError as error:
        # Return a safe operational signal.  The backend response can include
        # provider internals or document data, so it must not be exposed here.
        return {"error": f"Emal serveri HTTP {error.code} xətası qaytardı."}
    except TimeoutError:
        return {"error": "Emal vaxt limiti keçdi. OCR xidməti cavab vermədi."}
    except URLError:
        return {"error": "Emal serveri ilə əlaqə yaradıla bilmədi."}
    except Exception as error:  # noqa: BLE001 - do not leak provider details or document data
        return {"error": f"Emal mərhələsində {type(error).__name__} xətası baş verdi."}


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
    tunnel_address = os.getenv("GRADIO_SHARE_SERVER_ADDRESS")
    if tunnel_address:
        # Some managed Windows networks intercept the Gradio API certificate.
        # The share endpoint is obtained from the system-trusted route and passed
        # in explicitly, so Gradio can still establish its standard FRP tunnel.
        from gradio import networking

        demo.share_url = networking.setup_tunnel(
            local_host="0.0.0.0",
            local_port=int(os.getenv("DEMO_PORT", "8099")),
            share_token=demo.share_token,
            share_server_address=tunnel_address,
            share_server_tls_certificate=None,
        )
    public_demo = os.getenv("DEMO_PUBLIC", "").lower() == "true"
    demo.launch(
        server_name="0.0.0.0",
        server_port=int(os.getenv("DEMO_PORT", "8099")),
        share=True,
        auth=None
        if public_demo
        else (os.getenv("DEMO_USER", "demo"), os.environ["DEMO_PASSWORD"]),
        auth_message=None if public_demo else "Bu müvəqqəti yoxlama mühitidir.",
        show_error=False,
        prevent_thread_lock=True,
    )
    share_url_file = os.getenv("DEMO_SHARE_URL_FILE")
    if share_url_file:
        Path(share_url_file).write_text(str(demo.share_url), encoding="utf-8")
    threading.Event().wait()
