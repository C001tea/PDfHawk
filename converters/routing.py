from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/progress/(?P<task_id>[-\w]+)/$', consumers.ProgressConsumers.as_asgi())
]