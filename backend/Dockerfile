# Docker deploy (instead of Render's plain Python buildpack) so the OCR
# fallback in document_loader.py has its system binaries available.
# Render's native Python environment build step can't apt-get install
# tesseract-ocr/poppler-utils, so without this, scanned-PDF OCR silently
# no-ops (everything else in the app still works fine without Docker).
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000}"]
