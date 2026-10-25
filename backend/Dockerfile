FROM python:3.12-slim

# tesseract-ocr: OCR for scanned pages/images (pytesseract shells out to it).
# libgomp1: OpenMP runtime that faiss-cpu links against.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Runtime image only needs the app package; tests and .env stay out of the image.
COPY app ./app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
