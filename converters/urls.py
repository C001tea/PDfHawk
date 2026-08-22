from django.urls import path
from . import views
from django.shortcuts import redirect

urlpatterns = [
    path('', lambda request: redirect('pdf-to-word'), name='home'),
    path('pdf-to-word/', views.pdf_to_word, name="pdf-to-word"),
    path('pdf-to-image/', views.pdf_to_pngjpg, name="pdf-to-image"),
    path('compress-pdf/', views.compress_pdf, name="compress-pdf"),
    path('pdf-ocr/', views.pdf_ocr, name="pdf-ocr"),
    path('word-to-pdf/', views.word_to_pdf, name="word-to-pdf"),
    path('join-pdf/', views.join_pdf, name="join-pdf"),
    path('image-pdf/', views.image_pdf, name="image-pdf"),
    path('get-preview/', views.get_preview, name="get-preview"),
    path('api/status/<uuid:job_id>/', views.get_status, name='get-status'),
    path('api/download-zip/', views.download_zip, name='download-zip'),
    path('download/<uuid:job_id>/', views.download_file, name='download_file'),
    path('privacy-policy/', views.privacy_policy, name='privacy-policy'),
    path('terms/', views.terms, name='terms'),
]
