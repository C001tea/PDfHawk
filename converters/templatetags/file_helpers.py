import os
from django import template
from django.templatetags.static import static

register = template.Library()

ICON_MAPPING = {
    '.docx': 'icons/docx.svg',
    '.doc': 'icons/doc.svg',
}

@register.filter
def file_icon(value):
    file_str = str(value)
    _, ext = os.path.splitext(file_str)
    ext = ext.lower()

    icon_path = ICON_MAPPING.get(ext)
    return static(icon_path)