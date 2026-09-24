FROM python:3.13-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
RUN useradd --create-home appuser \
    && mkdir -p /home/appuser/.cache/huggingface/gradio/frpc \
    && python -c "from urllib.request import urlretrieve; urlretrieve('https://cdn-media.huggingface.co/frpc-gradio-0.3/frpc_linux_amd64', '/home/appuser/.cache/huggingface/gradio/frpc/frpc_linux_amd64_v0.3')" \
    && chmod 755 /home/appuser/.cache/huggingface/gradio/frpc/frpc_linux_amd64_v0.3 \
    && chown -R appuser:appuser /home/appuser/.cache
USER appuser
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
