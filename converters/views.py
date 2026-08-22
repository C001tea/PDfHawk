import base64
from django.utils import timezone
from datetime import timedelta
from django.http import JsonResponse, FileResponse, HttpResponse
from django.shortcuts import render, get_object_or_404
from .models import ConversionJob
from . import tasks
from .tasks import convert_pdf_to_word, convert_pdf_to_pngjpg, convert_compress_pdf, convert_pdf_ocr, convert_word_to_pdf, convert_join_pdf, convert_image_pdf
from django.core.files.storage import default_storage
from django.urls import reverse
import os, fitz, zipfile

def pdf_to_word(request):
    if request.method == 'POST':
        if check_ip_limit(get_ip_client(request)):
            return JsonResponse({'error': 'Daily limit reached. Try again tomorrow.'})
        files = request.FILES.getlist('file')

        if len(files) > 20:
            return JsonResponse({'error': 'Maximum 20 files per session'})
        job_list = []
        if 'file' not in request.FILES:
            return JsonResponse({'error': 'file is not selected'})
        for file in request.FILES.getlist('file'):
            job = ConversionJob.objects.create(tool_type='pdf-to-word', input_file=file, original_name=file.name, ip_address=get_ip_client(request))
            convert_pdf_to_word.delay(job.id)
            job_list.append(str(job.id))
        return JsonResponse({"job_id": job_list})
    return render(request, 'converters/pdf_to_word.html')


def pdf_to_pngjpg(request):
    if request.method == 'POST':
        if check_ip_limit(get_ip_client(request)):
            return JsonResponse({'error': 'Daily limit reached. Try again tomorrow.'})
        files = request.FILES.getlist('file')

        if len(files) > 20:
            return JsonResponse({'error': 'Maximum 20 files per session'})
        output_format = request.POST.get('format', 'png').lower()
        job_list = []
        if 'file' not in request.FILES:
            return JsonResponse({'error': 'file is not selected'})
        for file in request.FILES.getlist('file'):
            job = ConversionJob.objects.create(tool_type='pdf-to-pngjpg', output_format=output_format, input_file=file, original_name=file.name, ip_address=get_ip_client(request))
            convert_pdf_to_pngjpg.delay(job.id)
            job_list.append(str(job.id))
        return JsonResponse({"job_id": job_list})
    return render(request, 'converters/pdf_to_pngjpg.html')


def compress_pdf(request):
    if request.method == 'POST':
        if check_ip_limit(get_ip_client(request)):
            return JsonResponse({'error': 'Daily limit reached. Try again tomorrow.'})
        files = request.FILES.getlist('file')
        if len(files) > 20:
            return JsonResponse({'error': 'Maximum 20 files per session'})
        job_list = []
        if 'file' not in request.FILES:
            return JsonResponse({'error': 'file is not selected'})
        for file in request.FILES.getlist('file'):
            job = ConversionJob.objects.create(tool_type='compress-pdf', input_file=file, original_name=file.name, ip_address=get_ip_client(request))
            convert_compress_pdf.delay(job.id)
            job_list.append(str(job.id))
        return JsonResponse({"job_id": job_list})
    return render(request, 'converters/compress_pdf.html')

def pdf_ocr(request):
    if request.method == 'POST':
        if check_ip_limit(get_ip_client(request)):
            return JsonResponse({'error': 'Daily limit reached. Try again tomorrow.'})
        files = request.FILES.getlist('file')
        if len(files) > 20:
            return JsonResponse({'error': 'Maximum 20 files per session'})
        job_list = []
        if 'file' not in request.FILES:
            return JsonResponse({'error': 'file is not selected'})
        for file in request.FILES.getlist('file'):
            job = ConversionJob.objects.create(tool_type='pdf-ocr', input_file=file, original_name=file.name, ip_address=get_ip_client(request))
            convert_pdf_ocr.delay(job.id)
            job_list.append(str(job.id))
        return JsonResponse({"job_id": job_list})
    return render(request, 'converters/pdf_ocr.html')


def word_to_pdf(request):
    if request.method == 'POST':
        if check_ip_limit(get_ip_client(request)):
            return JsonResponse({'error': 'Daily limit reached. Try again tomorrow.'})
        files = request.FILES.getlist('file')
        if len(files) > 20:
            return JsonResponse({'error': 'Maximum 20 files per session'})
        job_list = []
        if 'file' not in request.FILES:
            return JsonResponse({'error': 'file is not selected'})
        for file in request.FILES.getlist('file'):
            job = ConversionJob.objects.create(tool_type='image-to-pdf', input_file=file, original_name=file.name, ip_address=get_ip_client(request))
            convert_word_to_pdf.delay(job.id)
            job_list.append(str(job.id))
        return JsonResponse({"job_id": job_list})
    return render(request, 'converters/word_to_pdf.html')


def join_pdf(request):
    if request.method == 'POST':
        if check_ip_limit(get_ip_client(request)):
            return JsonResponse({'error': 'Daily limit reached. Try again tomorrow.'})
        files = request.FILES.getlist('file')
        if len(files) > 20:
            return JsonResponse({'error': 'Maximum 20 files per session'})
        if 'file' not in request.FILES:
            return JsonResponse({'error': 'file is not selected'})
        first_original_name = None
        paths = []
        for file in request.FILES.getlist('file'):
            if first_original_name is None:
                first_original_name = file.name
            path = default_storage.save(f'uploads/{file.name}', file)
            paths.append(path)
        job = ConversionJob.objects.create(tool_type='join-pdf', input_file=paths[0], original_name=first_original_name,
                                               ip_address=get_ip_client(request))

        convert_join_pdf.delay(job.id, paths)

        return JsonResponse({"job_id": [str(job.id)]})
    return render(request, 'converters/join_pdf.html')


def image_pdf(request):
    if request.method == 'POST':
        if check_ip_limit(get_ip_client(request)):
            return JsonResponse({'error': 'Daily limit reached. Try again tomorrow.'})
        files = request.FILES.getlist('file')
        if len(files) > 20:
            return JsonResponse({'error': 'Maximum 20 files per session'})
        if 'file' not in request.FILES:
            return JsonResponse({'error': 'file is not selected'})
        paths = []
        first_original_name = None
        for file in request.FILES.getlist('file'):
            if first_original_name is None:
                first_original_name = file.name
            path = default_storage.save(f'uploads/{file.name}', file)
            paths.append(path)
        job = ConversionJob.objects.create(tool_type='image-pdf', input_file=paths[0], original_name=first_original_name ,ip_address=get_ip_client(request))
        convert_image_pdf.delay(job.id, paths)
        return JsonResponse({"job_id": [str(job.id)]})
    return render(request, 'converters/image_pdf.html')


def get_status(request, job_id):
    job = get_object_or_404(ConversionJob, id=job_id)
    if job.status == 'done':

        download_url = reverse('download_file', kwargs={"job_id": job.id})

        return JsonResponse({'status': 'done','url': download_url})
    return JsonResponse({'status': job.status})

def get_ip_client(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def download_file(request, job_id):
    job = get_object_or_404(ConversionJob, id=job_id)

    filename = os.path.basename(job.original_name)
    filename = os.path.splitext(filename)[0]
    if job.tool_type == "pdf-to-pngjpg":
        download_name = f"{filename}.zip"
    elif job.tool_type == "pdf-to-word":
         download_name = f"{filename}.docx"
    else:
        download_name = f"{filename}.pdf"

    file_handle = job.output_file.open('rb')
    return FileResponse(
        file_handle,
        as_attachment=True,
        filename=download_name
    )

def get_preview(request):
    if request.method == "POST":
        file = request.FILES.get('file')

        with fitz.open(stream=file.read(), filetype='pdf') as f:
            page = f[0]
            mat = fitz.Matrix(0.6, 0.6)
            pix = page.get_pixmap(matrix=mat)

            img_bytes = pix.tobytes("png")

            base64_img = base64.b64encode(img_bytes).decode('utf-8')
            preview_url = f"data:image/png;base64,{base64_img}"

        return JsonResponse({"preview_url": preview_url})
    return JsonResponse({"error": "Something went wrong!"})


def download_zip(request):
    job_ids = request.GET.getlist('job_id')

    response = HttpResponse(content_type='application/zip')
    response['Content-Disposition'] = 'attachment; filename="files.zip"'

    with zipfile.ZipFile(response, 'w', compression=zipfile.ZIP_DEFLATED) as zipf:
        for job_id in job_ids:
            job = get_object_or_404(ConversionJob, id=job_id)
            folder_name = os.path.splitext(os.path.basename(job.original_name))[0]
            if job.tool_type == "pdf-to-pngjpg":
                with zipfile.ZipFile(job.output_file.path, 'r') as inner_zip:
                    for member in inner_zip.infolist():
                        file_data = inner_zip.read(member.filename)
                        zip_path = f"{folder_name}/{member.filename}"
                        zipf.writestr(zip_path, file_data)
            else:
                out_filename = os.path.basename(job.original_name)
                out_filename = os.path.splitext(out_filename)[0] + '.pdf'
                zipf.write(job.output_file.path, arcname=out_filename)

    return response

def check_ip_limit(ip, limit=200):
    today = timezone.now().date()
    count = ConversionJob.objects.filter(
        ip_address=ip,
        created_at__date=today
    ).count()
    return count >= limit


def privacy_policy(request):
    return render(request, 'converters/privacy_policy.html')

def terms(request):
    return render(request, 'converters/terms.html')