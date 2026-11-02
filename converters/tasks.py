import logging
import os
import shutil
from contextlib import ExitStack
from pathlib import Path

import ocrmypdf
import pikepdf
from asgiref.sync import async_to_sync
from celery import shared_task
from channels.layers import get_channel_layer
from django.conf import settings
from django.core.files.base import ContentFile
from PIL import Image, ImageOps

from .converter import pdf_to_word, pdf_to_pngjpg, compress_pdf, word_pdf
from .models import ConversionJob

logger = logging.getLogger(__name__)


def _get_job(job_id):
    try:
        return ConversionJob.objects.get(id=job_id)
    except ConversionJob.DoesNotExist:
        return None


@shared_task(soft_time_limit=300)
def convert_pdf_to_word(job_id):
    job = _get_job(job_id)
    if job is None:
        return

    out_dir = os.path.join(settings.MEDIA_ROOT, 'outputs', 'pdf-word')
    try:
        out = pdf_to_word(job.input_file.path, out_dir)
        job.output_file = os.path.relpath(out, settings.MEDIA_ROOT).replace(os.sep, '/')
        job.status = 'done'
    except Exception:
        logger.exception("pdf-to-word failed for job %s", job_id)
        job.status = 'error'
    finally:
        job.save(update_fields=['status', 'output_file'])


@shared_task
def convert_pdf_to_pngjpg(job_id):
    job = _get_job(job_id)
    if job is None:
        return

    try:
        input_file = job.input_file.path
        zip_file = pdf_to_pngjpg(input_file, job.output_format or 'png')
        file_name = Path(input_file).stem
        job.output_file.save(f"pngjpg/{file_name}.zip", ContentFile(zip_file.getvalue()), save=False)
        job.status = 'done'
    except Exception:
        logger.exception("pdf-to-pngjpg failed for job %s", job_id)
        job.status = 'error'
    finally:
        job.save(update_fields=['status', 'output_file'])


@shared_task
def convert_compress_pdf(job_id):
    job = _get_job(job_id)
    if job is None:
        return

    input_file = job.input_file.path
    filename = Path(input_file).name
    output_dir = os.path.join(settings.MEDIA_ROOT, 'outputs', 'compress')
    output_path = os.path.join(output_dir, filename)
    os.makedirs(output_dir, exist_ok=True)

    try:
        compress_pdf(input_file, output_path)
        job.output_file = 'outputs/compress/' + filename
        job.status = 'done'
    except Exception:
        logger.exception("compress failed for job %s", job_id)
        job.status = 'error'
    finally:
        job.save(update_fields=['status', 'output_file'])


@shared_task(soft_time_limit=900)
def convert_pdf_ocr(job_id):
    job = _get_job(job_id)
    if job is None:
        return

    input_file = job.input_file.path
    filename = Path(input_file).name
    output_dir = os.path.join(settings.MEDIA_ROOT, 'outputs', 'ocr')
    output_path = os.path.join(output_dir, filename)
    os.makedirs(output_dir, exist_ok=True)

    try:
        ocrmypdf.ocr(
            input_file,
            output_path,
            language='eng+rus',
            deskew=True,
            clean=True,
            skip_text=True,
            optimize=1,
        )
        job.output_file = 'outputs/ocr/' + filename
        job.status = 'done'
    except Exception:
        logger.exception("ocr failed for job %s", job_id)
        job.status = 'error'
    finally:
        job.save(update_fields=['status', 'output_file'])


@shared_task(soft_time_limit=180)
def convert_word_to_pdf(job_id):
    job = _get_job(job_id)
    if job is None:
        return

    input_file = job.input_file.path
    filename = Path(input_file).stem
    output_dir = os.path.join(settings.MEDIA_ROOT, 'outputs', 'word_pdf')
    os.makedirs(output_dir, exist_ok=True)

    try:
        result = word_pdf(input_file, output_dir)
        with open(result, 'rb') as f:
            job.output_file.save(f"word_pdf/{filename}.pdf", ContentFile(f.read()), save=False)
        try:
            os.remove(result)  # убираем временный файл LibreOffice
        except OSError:
            pass
        job.status = 'done'
    except Exception:
        logger.exception("word-to-pdf failed for job %s", job_id)
        job.status = 'error'
    finally:
        job.save(update_fields=['status', 'output_file'])


@shared_task
def convert_join_pdf(job_id, input_files):
    job = _get_job(job_id)
    if job is None:
        return

    out_dir = os.path.join(settings.MEDIA_ROOT, 'outputs', 'join_pdf')
    os.makedirs(out_dir, exist_ok=True)

    try:
        output_path = os.path.join(out_dir, f'{job_id}.pdf')
        with ExitStack() as stack:
            output_pdf = stack.enter_context(pikepdf.Pdf.new())
            # исходные файлы должны оставаться открытыми до save()
            for file in input_files:
                src = stack.enter_context(pikepdf.open(os.path.join(settings.MEDIA_ROOT, file)))
                output_pdf.pages.extend(src.pages)
            output_pdf.save(output_path)

        job.output_file = f'outputs/join_pdf/{job_id}.pdf'
        job.status = 'done'
    except Exception:
        logger.exception("join-pdf failed for job %s", job_id)
        job.status = 'error'
    finally:
        job.save(update_fields=['status', 'output_file'])


@shared_task
def convert_image_pdf(job_id, input_files):
    job = _get_job(job_id)
    if job is None:
        return

    out_dir = os.path.join(settings.MEDIA_ROOT, 'outputs', 'image_pdf')
    os.makedirs(out_dir, exist_ok=True)
    output_path = os.path.join(out_dir, f'{job_id}.pdf')

    try:
        images = []
        for file_path in input_files:
            full_path = os.path.join(settings.MEDIA_ROOT, file_path)
            with Image.open(full_path) as src:
                img = ImageOps.exif_transpose(src)  # учитываем поворот из EXIF
                if img.mode in ("RGBA", "LA", "P"):
                    img = img.convert("RGBA")
                    background = Image.new("RGB", img.size, (255, 255, 255))
                    background.paste(img, mask=img.split()[-1])
                    img = background
                elif img.mode != "RGB":
                    img = img.convert("RGB")
                else:
                    img = img.copy()
                images.append(img)

        if not images:
            raise ValueError("no images")

        images[0].save(
            output_path,
            save_all=True,
            append_images=images[1:],
            resolution=150.0,
        )
        job.output_file = f"outputs/image_pdf/{job_id}.pdf"
        job.status = 'done'
    except Exception:
        logger.exception("image-pdf failed for job %s", job_id)
        job.status = 'error'
    finally:
        job.save(update_fields=['status', 'output_file'])


@shared_task()
def cleanup_old_files():
    from datetime import timedelta
    from django.utils import timezone

    one_hour_ago = timezone.now() - timedelta(hours=1)
    old_jobs = ConversionJob.objects.filter(created_at__lt=one_hour_ago)
    for job in old_jobs:
        try:
            # для join-pdf и image-pdf все загруженные файлы лежат в папке batch_*
            if job.tool_type in ('join-pdf', 'image-pdf') and job.input_file:
                folder = Path(job.input_file.path).parent
                if folder.name.startswith('batch_'):
                    shutil.rmtree(folder, ignore_errors=True)
            if job.input_file:
                job.input_file.delete(save=False)
            if job.output_file:
                job.output_file.delete(save=False)
        except Exception:
            logger.exception("cleanup failed for job %s", job.id)
        job.delete()


def send_task_progress(task_id, percent, status):
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f'progress_{task_id}',
        {
            'type': 'send_progress',
            'message': {
                'percent': percent,
                'status': status
            }
        }
    )