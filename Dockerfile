FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    MPLCONFIGDIR=/tmp/matplotlib \
    MPLBACKEND=Agg

WORKDIR /app
# Tesseract enables offline OCR (OCR_PROVIDER=tesseract or auto without a vision model)
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install -r requirements.txt pytesseract \
    && python -c "import matplotlib.pyplot" && chmod -R a+rwX /tmp/matplotlib

COPY app ./app
COPY static ./static
COPY config ./config
COPY samples ./samples

RUN useradd --create-home --uid 10001 assistant && mkdir -p /app/data && chown -R assistant /app/data
USER assistant

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:8080/api/health', timeout=4)" || exit 1

# One worker per container: the document index, rate limiter and background answer runs live in process memory.
# The app is fully async, so a single worker serves many concurrent chats. Scale with more containers
# only after moving the index to a shared vector store (see docs/ARCHITECTURE.md).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers", "--forwarded-allow-ips", "*"]
