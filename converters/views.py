import base64
import os
import uuid
import zipfile

import fitz
from django.core.files.storage import default_storage
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone

from .models import ConversionJob
from .tasks import (
    convert_compress_pdf,
    convert_image_pdf,
    convert_join_pdf,
    convert_pdf_ocr,
    convert_pdf_to_pngjpg,
    convert_pdf_to_word,
    convert_word_to_pdf,
)

MAX_FILES = 20
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 МБ на файл

WORD_EXT = ('.doc', '.docx', '.odt', '.rtf')
IMAGE_EXT = ('.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif', '.tif', '.tiff')

# какое расширение у результата каждого инструмента
RESULT_EXT = {
    'pdf-to-word': '.docx',
    'pdf-to-pngjpg': '.zip',
}


# ---------------------------------------------------------------- вспомогательное

def get_ip_client(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def check_ip_limit(ip, limit=200):
    today = timezone.now().date()
    count = ConversionJob.objects.filter(
        ip_address=ip,
        created_at__date=today
    ).count()
    return count >= limit


def _valid_file(f, kind):
    name = f.name.lower()
    if kind == 'pdf':
        head = f.read(1024)
        f.seek(0)
        return b'%PDF-' in head
    if kind == 'word':
        return name.endswith(WORD_EXT)
    if kind == 'image':
        return name.endswith(IMAGE_EXT)
    return True


def _check_upload(request, kind):
    """Возвращает (files, None) или (None, JsonResponse с ошибкой)."""
    if check_ip_limit(get_ip_client(request)):
        return None, JsonResponse({'error': 'Daily limit reached. Try again tomorrow.'})
    files = request.FILES.getlist('file')
    if not files:
        return None, JsonResponse({'error': 'file is not selected'})
    if len(files) > MAX_FILES:
        return None, JsonResponse({'error': 'Maximum 20 files per session'})
    for f in files:
        if f.size > MAX_FILE_SIZE:
            return None, JsonResponse({'error': f'File "{f.name}" is too large (max 50 MB)'})
        if not _valid_file(f, kind):
            return None, JsonResponse({'error': f'File "{f.name}" has an unsupported format'})
    return files, None


def _simple_tool(request, tool_type, task, template, kind='pdf', **job_kwargs):
    """Общая логика для инструментов: 1 загруженный файл = 1 задача."""
    if request.method == 'POST':
        files, error = _check_upload(request, kind)
        if error:
            return error
        job_list = []
        for file in files:
            job = ConversionJob.objects.create(
                tool_type=tool_type,
                input_file=file,
                original_name=file.name,
                ip_address=get_ip_client(request),
                **job_kwargs,
            )
            task.delay(job.id)
            job_list.append(str(job.id))
        return JsonResponse({"job_id": job_list})
    return render(request, template)


def _batch_tool(request, tool_type, task, template, kind):
    """Общая логика для join-pdf и image-pdf: много файлов = 1 задача."""
    if request.method == 'POST':
        files, error = _check_upload(request, kind)
        if error:
            return error
        batch_dir = f'uploads/batch_{uuid.uuid4().hex}'
        paths = [default_storage.save(f'{batch_dir}/{file.name}', file) for file in files]
        job = ConversionJob.objects.create(
            tool_type=tool_type,
            input_file=paths[0],
            original_name=files[0].name,
            ip_address=get_ip_client(request),
        )
        task.delay(job.id, paths)
        return JsonResponse({"job_id": [str(job.id)]})
    return render(request, template)


# ---------------------------------------------------------------- инструменты

def pdf_to_word(request):
    return _simple_tool(request, 'pdf-to-word', convert_pdf_to_word, 'converters/pdf_to_word.html')


def pdf_to_pngjpg(request):
    output_format = request.POST.get('format', 'png').lower()
    if output_format not in ('png', 'jpg', 'jpeg'):
        output_format = 'png'
    return _simple_tool(request, 'pdf-to-pngjpg', convert_pdf_to_pngjpg,
                        'converters/pdf_to_pngjpg.html', output_format=output_format)


def compress_pdf(request):
    return _simple_tool(request, 'compress-pdf', convert_compress_pdf, 'converters/compress_pdf.html')


def pdf_ocr(request):
    return _simple_tool(request, 'pdf-ocr', convert_pdf_ocr, 'converters/pdf_ocr.html')


def word_to_pdf(request):
    return _simple_tool(request, 'word-to-pdf', convert_word_to_pdf,
                        'converters/word_to_pdf.html', kind='word')


def join_pdf(request):
    return _batch_tool(request, 'join-pdf', convert_join_pdf, 'converters/join_pdf.html', 'pdf')


def image_pdf(request):
    return _batch_tool(request, 'image-pdf', convert_image_pdf, 'converters/image_pdf.html', 'image')


# ---------------------------------------------------------------- статус и скачивание

def get_status(request, job_id):
    job = get_object_or_404(ConversionJob, id=job_id)
    if job.status == 'done' and job.output_file:
        download_url = reverse('download_file', kwargs={"job_id": job.id})
        return JsonResponse({'status': 'done', 'url': download_url})
    return JsonResponse({'status': job.status})


def download_file(request, job_id):
    job = get_object_or_404(ConversionJob, id=job_id)
    if job.status != 'done' or not job.output_file:
        raise Http404

    base = os.path.splitext(os.path.basename(job.original_name))[0]
    download_name = base + RESULT_EXT.get(job.tool_type, '.pdf')

    return FileResponse(
        job.output_file.open('rb'),
        as_attachment=True,
        filename=download_name
    )


def get_preview(request):
    if request.method == "POST":
        file = request.FILES.get('file')
        if not file:
            return JsonResponse({"error": "file is not selected"}, status=400)
        try:
            with fitz.open(stream=file.read(), filetype='pdf') as f:
                page = f[0]
                pix = page.get_pixmap(matrix=fitz.Matrix(0.6, 0.6))
                img_bytes = pix.tobytes("png")
            base64_img = base64.b64encode(img_bytes).decode('utf-8')
            return JsonResponse({"preview_url": f"data:image/png;base64,{base64_img}"})
        except Exception:
            return JsonResponse({"error": "Cannot build preview"}, status=400)
    return JsonResponse({"error": "Something went wrong!"})


def _unique_name(name, used):
    """Если имя уже занято в архиве — добавляет (1), (2) ..."""
    base, ext = os.path.splitext(name)
    candidate, i = name, 1
    while candidate in used:
        candidate = f"{base} ({i}){ext}"
        i += 1
    used.add(candidate)
    return candidate


def download_zip(request):
    job_ids = request.GET.getlist('job_id')

    response = HttpResponse(content_type='application/zip')
    response['Content-Disposition'] = 'attachment; filename="files.zip"'

    used = set()
    with zipfile.ZipFile(response, 'w', compression=zipfile.ZIP_DEFLATED) as zipf:
        for job_id in job_ids:
            job = get_object_or_404(ConversionJob, id=job_id)
            if job.status != 'done' or not job.output_file:
                continue
            base = os.path.splitext(os.path.basename(job.original_name))[0]

            if job.tool_type == "pdf-to-pngjpg":
                folder = _unique_name(base, used)
                with zipfile.ZipFile(job.output_file.path, 'r') as inner_zip:
                    for member in inner_zip.infolist():
                        zipf.writestr(f"{folder}/{member.filename}", inner_zip.read(member.filename))
            else:
                out_name = _unique_name(base + RESULT_EXT.get(job.tool_type, '.pdf'), used)
                zipf.write(job.output_file.path, arcname=out_name)

    return response


def privacy_policy(request):
    return render(request, 'converters/privacy_policy.html')


def terms(request):
    return render(request, 'converters/terms.html')