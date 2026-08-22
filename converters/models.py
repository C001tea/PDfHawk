from django.db import models
import uuid

class ConversionJob(models.Model):
    STATUS = [
        ("pending", "Pending"),
        ("done", "Done"),
        ("error", "Error")
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    tool_type = models.CharField(max_length=100)
    input_file = models.FileField(upload_to='uploads/')
    output_file = models.FileField(blank=True, null=True, upload_to='outputs/')
    output_format = models.CharField(blank=True, null=True, max_length=20)
    original_name = models.CharField(max_length=255, blank=True, null=True)
    preview = models.ImageField(upload_to='previews/', blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField()
