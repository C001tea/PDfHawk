FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends ocrmypdf gettext tesseract-ocr tesseract-ocr-rus tesseract-ocr-eng unpaper ghostscript pngquant libpq-dev gcc && rm -rf /var/lib/apt/lists/*
RUN  sed -i 's/main/main contrib/g' /etc/apt/sources.list.d/debian.sources || true && apt-get update && apt-get install -y --no-install-recommends libreoffice fonts-liberation fonts-dejavu msttcorefonts ttf-mscorefonts-installer fontconfig fonts-freefont-ttf && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY ../requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


COPY .. .