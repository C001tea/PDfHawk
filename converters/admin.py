from django.contrib import admin
from .models import ConversionJob

@admin.register(ConversionJob)
class AdminConversionJob(admin.ModelAdmin):
    list_filter = ('created_at', )