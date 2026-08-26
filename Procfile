web: python manage.py collectstatic --noinput && gunicorn Filetools.wsgi
worker: celery -A Filetools worker --loglevel=info
beat: celery -A Filetools beat --loglevel=info