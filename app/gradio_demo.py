"""Temporary protected demo for exercising the same document engine in a browser."""

import mimetypes
import os
import json
import uuid
import threading
from html import escape
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


def _value(payload: dict, name: str) -> str:
    field = payload.get("fields", {}).get(name, {})
    return str(field.get("value") or "")


def _split_name(value: str) -> tuple[str, str]:
    parts = value.split()
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return " ".join(parts[:-1]), parts[-1]


def _sex_label(value: str) -> str:
    normalized = value.lower()
    if any(token in normalized for token in ("qad", "female", "woman")):
        return "Qadın"
    if any(token in normalized for token in ("kişi", "kisi", "male", "man")):
        return "Kişi"
    return value


def _cross_checks_html(payload: dict) -> str:
    rows = []
    label_map = {
        "full_name": "Ad, soyad",
        "passport_number": "Pasport nömrəsi",
        "passport_issue_date": "Pasportun verilmə tarixi",
        "personal_id": "Şəxsi kod",
        "date_of_birth": "Doğum tarixi",
    }
    status_map = {
        "match": "Uyğundur",
        "single_source": "Bir mənbə",
        "missing": "Tapılmadı",
        "conflict": "Uyğunsuzluq",
    }
    for check in payload.get("cross_checks", []):
        status = check.get("status", "missing")
        rows.append(
            "<tr>"
            f"<td>{escape(label_map.get(check.get('field'), check.get('field', '')))}</td>"
            f"<td><span class='check {escape(status)}'>{escape(status_map.get(status, status))}</span></td>"
            f"<td>{escape(check.get('message', ''))}</td>"
            "</tr>"
        )
    if not rows:
        return "<p class='muted'>Çarpaz yoxlama üçün məlumat yoxdur.</p>"
    return (
        "<table class='checks-table'><thead><tr><th>Sahə</th><th>Nəticə</th>"
        "<th>Qeyd</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )


def _form_values(file_path: str | None) -> tuple:
    payload = extract_for_demo(file_path)
    if payload.get("error"):
        return (
            f"<div class='operator-error'>{escape(payload['error'])}</div>",
            *([""] * 22),
            "<p class='muted'>Emal nəticəsi gözlənilir.</p>",
            "",
        )

    full_name = _value(payload, "full_name")
    first_name, last_name = _split_name(full_name)
    documents = payload.get("documents", [])
    document_type = documents[0].get("document_type", "Pasport") if documents else "Pasport"
    notes = " ".join(str(note) for note in payload.get("notes", []))
    found = sum(1 for field in payload.get("fields", {}).values() if field.get("value"))
    status = (
        "<div class='operator-success'>"
        f"Emal tamamlandı: {found} məlumat sahəsi tapıldı. Zəhmət olmasa xanaları yoxlayın."
        "</div>"
    )
    summary = (
        "<div class='summary-note'>"
        f"<strong>Tanınan sənəd:</strong> {escape(document_type)} · "
        f"<strong>Emal üsulu:</strong> {escape(payload.get('extraction_method', ''))}<br>"
        f"{escape(notes)}"
        "</div>"
    )
    return (
        status,
        document_type,
        "",
        _value(payload, "passport_number"),
        _value(payload, "passport_issuer"),
        _value(payload, "passport_issue_date"),
        _value(payload, "passport_expiry"),
        first_name,
        last_name,
        full_name,
        "",
        _value(payload, "citizenship"),
        _value(payload, "date_of_birth"),
        _value(payload, "birth_place"),
        _sex_label(_value(payload, "sex")),
        _value(payload, "application_type"),
        _value(payload, "permit_basis"),
        _value(payload, "application_date"),
        _value(payload, "phone"),
        _value(payload, "email"),
        _value(payload, "address"),
        _value(payload, "basis_note"),
        _value(payload, "special_note"),
        _cross_checks_html(payload),
        summary,
    )


FORM_CSS = """
.gradio-container { max-width: 1360px !important; background: #f3f7fb; }
.operator-title { margin-bottom: 0 !important; }
.operator-subtitle { color: #526678; margin-top: 0 !important; }
.form-panel { border: 1px solid #20bfce; background: #fff; box-shadow: none; }
.form-panel > .wrap { padding: 0 !important; }
.panel-heading { background: #35becd; color: #fff; font-size: 18px; font-weight: 700; padding: 11px 14px; margin: 0 0 12px; }
.panel-body { padding: 0 14px 14px; }
.operator-success, .operator-error, .summary-note { border-radius: 5px; padding: 11px 13px; margin: 8px 0 12px; }
.operator-success { background: #e9f8ee; border: 1px solid #8acda1; color: #176436; }
.operator-error { background: #fff0f0; border: 1px solid #e4a1a1; color: #a92525; }
.summary-note { background: #eef7fb; border: 1px solid #b8dde9; color: #345164; }
.checks-table { width: 100%; border-collapse: collapse; font-size: 14px; }
.checks-table th, .checks-table td { text-align: left; padding: 9px; border-bottom: 1px solid #d8e3ea; }
.check { border-radius: 999px; display: inline-block; font-weight: 600; padding: 3px 8px; }
.check.match { background: #dff4e5; color: #176436; }
.check.single_source { background: #e7f2ff; color: #1c6098; }
.check.missing { background: #f4f0e4; color: #766229; }
.check.conflict { background: #fde7e6; color: #a42725; }
.muted { color: #697b88; }
"""


with gr.Blocks(title="Sənəd Məlumat Çıxarışı", css=FORM_CSS) as demo:
    gr.Markdown("# Sənəddən məlumat çıxarışı", elem_classes="operator-title")
    gr.Markdown(
        "PDF və şəkildən çıxarılan məlumatları yoxlayın və lazım gələrsə düzəldin.",
        elem_classes="operator-subtitle",
    )
    with gr.Row():
        document = gr.File(
            label="Sənəd (PDF, JPG və ya PNG)",
            file_types=[".pdf", ".jpg", ".jpeg", ".png"],
            type="filepath",
            scale=5,
        )
        run = gr.Button("Məlumatları çıxar", variant="primary", scale=1)

    status_message = gr.HTML()
    with gr.Row():
        with gr.Column(scale=1, elem_classes="form-panel"):
            gr.HTML("<div class='panel-heading'>Şəxsiyyəti təsdiq edən sənədin detalları</div>")
            with gr.Column(elem_classes="panel-body"):
                with gr.Row():
                    document_type = gr.Dropdown(
                        ["Pasport", "Şəxsiyyət vəsiqəsi", "Digər"],
                        label="Sənədin növü *",
                        allow_custom_value=True,
                    )
                    passport_series = gr.Textbox(label="Seriya")
                    passport_number = gr.Textbox(label="Nömrə *")
                with gr.Row():
                    passport_issue_date = gr.Textbox(label="Verilmə tarixi *")
                    passport_expiry = gr.Textbox(label="Etibarlılıq tarixi")
                passport_issuer = gr.Textbox(label="Verən orqan *", lines=2)

        with gr.Column(scale=2, elem_classes="form-panel"):
            gr.HTML("<div class='panel-heading'>Oxuyucu məlumatları</div>")
            with gr.Column(elem_classes="panel-body"):
                with gr.Row():
                    first_name = gr.Textbox(label="Adı (Az) *")
                    last_name = gr.Textbox(label="Soyadı (Az) *")
                with gr.Row():
                    full_name_foreign = gr.Textbox(label="Adı, soyadı (beyn)")
                    father_name = gr.Textbox(label="Atasının adı (Az)")
                with gr.Row():
                    citizenship = gr.Textbox(label="Vətəndaşlığı *")
                    date_of_birth = gr.Textbox(label="Doğulduğu tarix *")
                with gr.Row():
                    birth_place = gr.Textbox(label="Doğulduğu yer")
                    sex = gr.Dropdown(["Kişi", "Qadın"], label="Cinsi *", allow_custom_value=True)

    with gr.Row():
        with gr.Column(scale=1, elem_classes="form-panel"):
            gr.HTML("<div class='panel-heading'>Müraciətin detalları</div>")
            with gr.Column(elem_classes="panel-body"):
                application_type = gr.Textbox(label="Müraciətin səbəbi *")
                permit_basis = gr.Textbox(label="Vəsatətin əsası")
                application_date = gr.Textbox(label="Müraciət tarixi *")
                basis_note = gr.Textbox(label="Qeyd", lines=3)
                special_note = gr.Textbox(label="Xüsusi qeyd", lines=3)

        with gr.Column(scale=1, elem_classes="form-panel"):
            gr.HTML("<div class='panel-heading'>Əlaqə vasitələri</div>")
            with gr.Column(elem_classes="panel-body"):
                phone = gr.Textbox(label="Telefon")
                email = gr.Textbox(label="E-poçt")
                address = gr.Textbox(label="Ünvan", lines=3)

    with gr.Group(elem_classes="form-panel"):
        gr.HTML("<div class='panel-heading'>Sənədlərarası yoxlama</div>")
        with gr.Column(elem_classes="panel-body"):
            summary = gr.HTML()
            cross_checks = gr.HTML()

    output_components = [
        status_message, document_type, passport_series, passport_number,
        passport_issuer, passport_issue_date, passport_expiry, first_name,
        last_name, full_name_foreign, father_name, citizenship, date_of_birth,
        birth_place, sex, application_type, permit_basis, application_date,
        phone, email, address, basis_note, special_note, cross_checks, summary,
    ]
    run.click(_form_values, inputs=document, outputs=output_components)


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
