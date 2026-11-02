import io
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

import fitz
import ocrmypdf
from docx import Document
from pdf2docx import Converter
from PIL import Image

# Если рядом лежит свой tesseract-ocr (как у вас на Windows), добавляем его в PATH,
# чтобы ocrmypdf его нашёл.
_tess_dir = os.path.join(os.path.dirname(__file__), "tesseract-ocr")
if os.path.isdir(_tess_dir):
    os.environ["PATH"] = _tess_dir + os.pathsep + os.environ.get("PATH", "")
    _tessdata = os.path.join(_tess_dir, "tessdata")
    if os.path.isdir(_tessdata) and "TESSDATA_PREFIX" not in os.environ:
        os.environ["TESSDATA_PREFIX"] = _tessdata


# ---------------------------------------------------------------- PDF -> WORD

def is_scanned(path, sample=5, min_chars=30):
    """True, если в PDF почти нет текстового слоя (это скан)."""
    with fitz.open(path) as doc:
        n = min(len(doc), sample)
        if n == 0:
            return False
        text_pages = sum(1 for i in range(n) if len(doc[i].get_text().strip()) >= min_chars)
        return text_pages / n < 0.5


def fix_cmyk(path):
    """Переводит CMYK-картинки в RGB (работает с файлом на месте)."""
    doc = fitz.open(path)
    changed = False
    try:
        for page in doc:
            for img in page.get_images(full=True):
                xref = img[0]
                try:
                    pix = fitz.Pixmap(doc, xref)
                    if pix.n - pix.alpha > 3:
                        page.replace_image(xref, pixmap=fitz.Pixmap(fitz.csRGB, pix))
                        changed = True
                except Exception:
                    continue
        if changed:
            doc.save(path + ".tmp", garbage=3, deflate=True)
    finally:
        doc.close()
    if changed:
        os.replace(path + ".tmp", path)


def optimize_docx_image(docx_path, quality=80, max_side=2000):
    """Аккуратно сжимает только JPEG внутри docx. PNG и прозрачность не трогает."""
    tmp = docx_path + ".tmp"
    with zipfile.ZipFile(docx_path) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            name = item.filename.lower()
            if name.startswith("word/media/") and name.endswith((".jpg", ".jpeg")):
                try:
                    img = Image.open(io.BytesIO(data))
                    img.thumbnail((max_side, max_side))
                    buf = io.BytesIO()
                    img.convert("RGB").save(buf, "JPEG", quality=quality, optimize=True)
                    if buf.tell() < len(data):
                        data = buf.getvalue()
                except Exception:
                    pass
            zout.writestr(item, data)
    os.replace(tmp, docx_path)


def scan_to_docx(pdf_path, out_doc, work_dir):
    """Скан -> OCR -> простой docx с текстом."""
    txt_path = os.path.join(work_dir, "out.txt")
    ocrmypdf.ocr(
        pdf_path,
        os.path.join(work_dir, "ocr.pdf"),
        language="eng+rus",
        deskew=True,
        force_ocr=True,
        output_type="pdf",
        optimize=0,
        sidecar=txt_path,
    )
    text = Path(txt_path).read_text(encoding="utf-8", errors="ignore")
    pages = text.split("\f")  # sidecar разделяет страницы символом \f
    if pages and not pages[-1].strip():
        pages.pop()

    doc = Document()
    for i, page_text in enumerate(pages):
        for para in page_text.split("\n\n"):
            para = " ".join(para.split())
            if para:
                doc.add_paragraph(para)
        if i < len(pages) - 1:
            doc.add_page_break()
    doc.save(out_doc)


def pdf_to_word(src, out_dir):
    """Конвертирует PDF в DOCX и возвращает путь к файлу. При ошибке бросает исключение."""
    os.makedirs(out_dir, exist_ok=True)
    out_doc = os.path.join(out_dir, Path(src).stem + ".docx")

    with tempfile.TemporaryDirectory() as work:
        tmp = os.path.join(work, "in.pdf")
        shutil.copy(src, tmp)  # оригинал не трогаем
        try:
            fix_cmyk(tmp)
        except Exception:
            pass

        if is_scanned(tmp):
            scan_to_docx(tmp, out_doc, work)
        else:
            cv = Converter(tmp)
            try:
                cv.convert(out_doc)
            finally:
                cv.close()

    optimize_docx_image(out_doc)
    return out_doc


# ---------------------------------------------------------------- PDF -> PNG/JPG

def pdf_to_pngjpg(path_to_file_in, extension='.png'):
    img_format = extension.lstrip('.').lower()
    if img_format == "jpg":
        img_format = "jpeg"
    zip_buffer = io.BytesIO()

    with fitz.open(path_to_file_in) as doc, \
            zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        mat = fitz.Matrix(2, 2)  # ~150 dpi
        ext = "jpg" if img_format == "jpeg" else img_format
        for page_index in range(len(doc)):
            pix = doc[page_index].get_pixmap(matrix=mat)
            zip_file.writestr(f"page-{page_index + 1}.{ext}", pix.tobytes(img_format))

    zip_buffer.seek(0)
    return zip_buffer


# ---------------------------------------------------------------- COMPRESS

def compress_pdf(input_file, output_file):
    with fitz.open(input_file) as doc:
        try:
            doc.rewrite_images(dpi_threshold=150, dpi_target=110, quality=60)
        except Exception:
            pass  # старая версия PyMuPDF — просто пережмём структуру
        doc.save(output_file, garbage=4, deflate=True, clean=True)

    if os.path.getsize(output_file) >= os.path.getsize(input_file):
        shutil.copy(input_file, output_file)


# ---------------------------------------------------------------- WORD -> PDF

def word_pdf(input_file, outputfile):
    input_file = Path(input_file)
    outputfile = Path(outputfile)
    outputfile.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as user_dir:
        command = [
            'libreoffice',
            f'-env:UserInstallation={Path(user_dir).as_uri()}',
            '--headless',
            '--convert-to', 'pdf',
            '--outdir', str(outputfile),
            str(input_file),
        ]
        try:
            subprocess.run(command, check=True, capture_output=True, timeout=120)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            raise RuntimeError("Error with conversion") from e

    expected_pdf_file = outputfile / f"{input_file.stem}.pdf"
    if not expected_pdf_file.exists():
        raise RuntimeError("Error with conversion: output file not found")
    return str(expected_pdf_file)