from celery import shared_task
from .models import ConversionJob
import os
from PIL import Image
from django.conf import settings
from .converter import switch_method, pdf_to_pngjpg, compress_pdf, word_pdf
from pathlib import Path
from django.core.files.base import ContentFile
import ocrmypdf, pikepdf
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

@shared_task
def convert_pdf_to_word(job_id):
    try:
        job = ConversionJob.objects.get(id=job_id)
    except ConversionJob.DoesNotExist:
        return

    input_file = job.input_file.path
    filename = os.path.splitext(os.path.basename(job.input_file.name))[0]
    output_path = os.path.join(settings.MEDIA_ROOT, 'outputs', 'pdf-word')
    os.makedirs(output_path, exist_ok=True)
    switch_method([input_file], output_path)

    try:
        job.output_file = 'outputs/pdf-word/' + filename + '.docx'
        job.status = 'done'
        print("output_file:", job.output_file)
        print("status:", job.status)
    except Exception:
        job.status = 'error'
    finally:
        print("saving job:", job.id)
        print("output_file before save:", job.output_file)
        job.save(update_fields=['status', 'output_file'])
        job.refresh_from_db()
        print("output_file after save:", job.output_file)


@shared_task
def convert_pdf_to_pngjpg(job_id):
    try:
        job = ConversionJob.objects.get(id=job_id)
    except ConversionJob.DoesNotExist:
        print("Does not exists")
        return

    output_format = job.output_format
    input_file = job.input_file.path
    zip_file = pdf_to_pngjpg(input_file, output_format)

    file_name = Path(input_file).stem

    try:
        job.output_file.save(f"pngjpg/{file_name}.zip", ContentFile(zip_file.getvalue()), save=False)

        job.status = 'done'
        print('status:', job.status)
    except Exception:
        job.status = 'error'
        print("error")
    finally:
        job.save(update_fields=['status', 'output_file'])
        job.refresh_from_db()


@shared_task
def convert_compress_pdf(job_id):
    try:
        job = ConversionJob.objects.get(id=job_id)
    except ConversionJob.DoesNotExist:
        return

    input_file = job.input_file.path
    filename = Path(input_file).name
    output_file = os.path.join(settings.MEDIA_ROOT, 'outputs', 'compress')
    output_path = os.path.join(output_file, filename)

    os.makedirs(output_file, exist_ok=True)

    try:
        compress_pdf(input_file, output_path)
        job.output_file = os.path.join('outputs', 'compress', filename)
        job.status = 'done'
        print(200)
    except Exception as e:
        job.status = 'error'
        print(e)
    finally:
        job.save(update_fields=['status', 'output_file'])
        job.refresh_from_db()

@shared_task
def convert_pdf_ocr(job_id):
    try:
        job = ConversionJob.objects.get(id=job_id)
    except ConversionJob.DoesNotExist:
        return

    input_file = job.input_file.path
    filename = Path(input_file).name
    output_file = os.path.join(settings.MEDIA_ROOT, 'outputs', 'ocr')
    output_path = os.path.join(output_file, filename)
    os.makedirs(output_file, exist_ok=True)

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
        job.output_file = os.path.join('outputs', 'ocr', filename)
        job.status = 'done'

    except Exception as e:
        job.status = 'error'

    finally:
        job.save(update_fields=['status', 'output_file'])
        job.refresh_from_db()

@shared_task
def convert_word_to_pdf(job_id):
    try:
        job = ConversionJob.objects.get(id=job_id)
    except ConversionJob.DoesNotExist:
        return

    input_file = job.input_file.path
    filename = Path(input_file).stem
    output_path = os.path.join(settings.MEDIA_ROOT, 'outputs', 'word_pdf')

    os.makedirs(output_path, exist_ok=True)

    try:
        result = word_pdf(input_file, output_path)
        with open(result, 'rb') as f:
            job.output_file.save(f"word_pdf/{filename}.pdf", ContentFile(f.read()), save=False)
        job.status = 'done'
    except Exception as e:
        job.status = 'error'
        print(e)
    finally:
        job.save(update_fields=['status', 'output_file'])
        job.refresh_from_db()


@shared_task
def convert_join_pdf(job_id, input_files):
    try:
        job = ConversionJob.objects.get(id=job_id)
    except ConversionJob.DoesNotExist:
        return

    os.makedirs(os.path.join(settings.MEDIA_ROOT, 'outputs', 'join_pdf'), exist_ok=True)

    try:
        output_pdf = pikepdf.Pdf.new()
        for file in input_files:
            full_path = os.path.join(settings.MEDIA_ROOT, file)
            with pikepdf.open(full_path) as f:
                output_pdf.pages.extend(f.pages)

        output_path = os.path.join(settings.MEDIA_ROOT, 'outputs', 'join_pdf', f'{job_id}.pdf')
        output_pdf.save(output_path)
        output_pdf.close()

        job.output_file = f'outputs/join_pdf/{job_id}.pdf'
        job.status = 'done'
    except Exception as e:
        job.status = 'error'

    finally:
        job.save(update_fields=['status', 'output_file'])
        job.refresh_from_db()

@shared_task
def convert_image_pdf(job_id, input_files):
    try:
        job = ConversionJob.objects.get(id=job_id)
    except ConversionJob.DoesNotExist:
        print('Does not exist')
        return

    os.makedirs(os.path.join(settings.MEDIA_ROOT, 'outputs', 'image_pdf'), exist_ok=True)
    output_path = os.path.join(settings.MEDIA_ROOT, 'outputs', 'image_pdf', f'{job_id}.pdf')

    try:
        images = []
        for file_path in input_files:
            full_path = os.path.join(settings.MEDIA_ROOT, file_path)
            img = Image.open(full_path)
            if img.mode != "RGB":
                img = img.convert("RGB")
            images.append(img)

        if images:
            images[0].save(
                output_path,
                save_all=True,
                append_images=images[1:]
            )

        job.output_file = f"outputs/image_pdf/{job_id}.pdf"
        job.status = 'done'

    except Exception as e:
        job.status = 'error'

    finally:
        job.save(update_fields=['status', 'output_file'])
        job.refresh_from_db()

@shared_task()
def cleanup_old_files():
    from datetime import timedelta
    from django.utils import timezone

    one_hour_ago = timezone.now() - timedelta(hours=1)
    old_jobs = ConversionJob.objects.filter(created_at__lt=one_hour_ago)
    for job in old_jobs:
        if job.input_file:
            job.input_file.delete()
        if job.output_file:
            job.output_file.delete()
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