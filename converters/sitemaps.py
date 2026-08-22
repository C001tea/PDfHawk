from django.contrib.sitemaps import Sitemap
from django.urls import reverse

class StaticViewSitemap(Sitemap):
    priority = 0.8
    changefreq = 'weekly'

    def items(self):
        return [
            'pdf-to-word',
            'pdf-to-image',
            'compress-pdf',
            'pdf-ocr',
            'word-to-pdf',
            'join-pdf',
            'image-pdf',
            'privacy-policy',
            'terms',
        ]
    def location(self, item):
        return reverse(item)