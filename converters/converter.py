import zipfile
import pytesseract
from PIL import Image, ImageFilter, ImageEnhance
from docx import Document
import io, pikepdf, pdf2docx, os, fitz
import subprocess, tempfile
from pathlib import Path

pytesseract.pytesseract.tesseract_cmd = os.path.join(os.path.dirname(__file__), "tesseract-ocr", "tesseract.exe")

def pdf_to_image(path_to_file_in, path_to_file_out):
    with fitz.open(path_to_file_in) as doc:

        word_doc = Document()
        for page_index in range(len(doc)):
            page = doc[page_index]

            mat = fitz.Matrix(4, 4)
            pix = page.get_pixmap(matrix=mat)
            img_path = os.path.join(path_to_file_out, f"page_{page_index}-image_{page_index}.png")
            pix.save(img_path)

            imag = Image.open(img_path)
            imag = imag.convert("L")
            enhancer = ImageEnhance.Contrast(imag)
            imag = enhancer.enhance(2.0)
            imag = imag.filter(ImageFilter.SHARPEN)
            imag = imag.filter(ImageFilter.MedianFilter(size=3))
            text = pytesseract.image_to_string(imag, lang="eng+rus", config="--oem 1 --psm 6")

            word_doc.add_paragraph(text)
            os.remove(img_path)

        basname = os.path.basename(path_to_file_in)
        pdf_to_docx = os.path.splitext(basname)[0] + ".docx"
        out_doc = str(os.path.join(path_to_file_out, pdf_to_docx))
        word_doc.save(out_doc)

def pdf_to_text(path_to_file, path_to_file_out):
    path_to_file = normalize_pdf(path_to_file)
    basname = os.path.basename(path_to_file)
    pdf_to_docx = os.path.splitext(basname)[0] + ".docx"
    out_doc = str(os.path.join(path_to_file_out, pdf_to_docx))

    converter = pdf2docx.Converter(path_to_file)
    converter.convert(out_doc)
    converter.close()
    optimize_docx_image(out_doc)

#choosing which function to use
def switch_method(path_to_file_in, path_to_file_out):

    for path_to_file in path_to_file_in:
        try:
            with fitz.open(path_to_file) as file:
                total_chars = 0
                for page in file:
                    text = page.get_text()
                    total_chars += len(text.strip())

        except fitz.FileDataError:
            continue

        #using only common pdf-to-word, ocr is using as another function
        pdf_to_text(path_to_file, path_to_file_out)

        # if total_chars > 50:
        #     print("use common")
        #     pdf_to_text(path_to_file, path_to_file_out)
        # else:
        #     print("use ocr")
        #     pdf_to_image(path_to_file, path_to_file_out)

def optimize_docx_image(docx_path, quality=75):
    buffer = io.BytesIO()

    with zipfile.ZipFile(docx_path, 'r') as zip_in:
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zip_out:
            for item in zip_in.infolist():
                data = zip_in.read(item.filename)
                if item.filename.startswith('word/media') and item.filename.endswith(('.jpg', '.jpeg', '.png')):
                    try:
                        img = Image.open(io.BytesIO(data))
                        if img.mode in ("RGBA", "P"):
                            img = img.convert("RGB")

                        img_out = io.BytesIO()
                        img.save(img_out, format="JPEG", quality=quality, optimize=True)
                        data = img_out.getvalue()
                    except Exception:
                        pass
                zip_out.writestr(item, data)
    with open(docx_path, 'wb') as f:
        f.write(buffer.getvalue())
# принимает пдф файл с избражениями, которые имеют цветовую модель CMYK и преобразовывает в RGB
def normalize_pdf(file):

    temp_path = os.path.basename(file)
    temp_file = os.path.join(os.path.dirname(file), os.path.splitext(temp_path)[0] + "_.pdf")

    doc = fitz.open(file)
    for page in doc:
        page_img = page.get_images(full=True)
        for img in page_img:
            xref = img[0]
            pix = fitz.Pixmap(doc, xref)

            if pix.n - pix.alpha > 3:
                pix_rgb = fitz.Pixmap(fitz.csRGB, pix)
                doc.update_image(xref, pix_rgb)
                pix_rgb = None
            pix = None

    doc.save(temp_file)
    doc.close()
    os.replace(temp_file, file)

    return file


def pdf_to_pngjpg(path_to_file_in, extension='.png'):
    img_format = extension.lstrip('.').lower()
    if img_format == "jpg":
        img_format = "jpeg"
    print(img_format)
    zip_buffer = io.BytesIO()

    with fitz.open(path_to_file_in) as doc, zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        mat = fitz.Matrix(4, 4)
        for page_index in range(len(doc)):
            page = doc[page_index]
            pix = page.get_pixmap(matrix=mat)
            img_bytes = pix.tobytes(img_format)

            file_name = f"page-{page_index}.{img_format}"
            zip_file.writestr(file_name, img_bytes)

    zip_buffer.seek(0)
    return zip_buffer

def compress_pdf(input_file, output_file):

    max_dimension = 2400
    quality = 65

    with pikepdf.open(input_file) as pdf:
        for page in pdf.pages:
            if '/Resources' not in page or '/XObject' not in page['/Resources']:
                continue

            xobjects = page['/Resources']['/XObject']

            for name, raw_image in list(xobjects.items()):
                if raw_image.get('/Subtype') != pikepdf.Name('/Image'):
                    continue

                if '/SMask' in raw_image or '/Mask' in raw_image:
                    continue

                try:
                    pdfimage = pikepdf.PdfImage(raw_image)
                    pil_image = pdfimage.as_pil_image()
                except Exception:
                    continue

                width, height = pil_image.size
                if max(width, height) > max_dimension:
                    pil_image.thumbnail((max_dimension, max_dimension), Image.LANCZOS)

                buffer = io.BytesIO()

                if pil_image.mode in ("RGBA", "P", "LA"):
                    background = Image.new("RGB", pil_image.size, (255, 255, 255))
                    if pil_image.mode == "P":
                        pil_image = pil_image.convert("RGBA")
                    background.paste(pil_image, mask=pil_image.split()[-1])
                    pil_image = background
                elif pil_image.mode != "RGB":
                    pil_image = pil_image.convert("RGB")

                if pil_image.mode == "L":
                    pil_image.save(buffer, format='PNG', optimize=True)
                else:
                    pil_image.save(buffer, format='JPEG', quality=quality, optimize=True)
                buffer.seek(0)
                raw_data = buffer.read()


                xobjects[name] = pdf.make_stream(
                    raw_data,
                    Filter=pikepdf.Name('/DCTDecode'),
                    Width=pil_image.width,
                    Height=pil_image.height,
                    ColorSpace=pikepdf.Name('/DeviceRGB'),
                    BitsPerComponent=8,
                    Subtype=pikepdf.Name('/Image'),
                    Type=pikepdf.Name('/XObject')
                )

        original_size = os.path.getsize(input_file)
        pdf.save(
            output_file,
            compress_streams=True,
            recompress_flate=True,
            object_stream_mode=pikepdf.ObjectStreamMode.generate,
            linearize=True)
        compressed_size = os.path.getsize(output_file)

        if compressed_size >= original_size:
            import shutil
            shutil.copy(input_file, output_file)

def word_pdf(input_file, outputfile):
    input_file = Path(input_file)
    outputfile = Path(outputfile)

    with tempfile.TemporaryDirectory() as user_dir:
        profile_flag = f"-env:UserInstallation=file://{user_dir}"

    command = [
        'libreoffice',
        profile_flag,
        '--headless',
        '--convert-to', 'pdf',
        '--outdir', str(outputfile),
        str(input_file)
    ]

    try:
        subprocess.run(
            command,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=120
        )
        expected_pdf_file = outputfile / f"{input_file.stem}.pdf"
        return str(expected_pdf_file)
    except subprocess.CalledProcessError as e:
        raise RuntimeError("Error with conversion")

