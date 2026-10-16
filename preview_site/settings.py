import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
SECRET_KEY = 'public-preview-no-authentication-no-sessions-not-a-production-secret'
DEBUG = False
ALLOWED_HOSTS = ['localhost', '127.0.0.1', '[::1]']
render_host = os.environ.get('RENDER_EXTERNAL_HOSTNAME', '').strip()
if render_host and '/' not in render_host and '*' not in render_host:
    ALLOWED_HOSTS.append(render_host)
ROOT_URLCONF = 'preview_site.urls'
WSGI_APPLICATION = 'preview_site.wsgi.application'
INSTALLED_APPS = []
DATABASES = {'default': {'ENGINE': 'django.db.backends.dummy'}}
MIDDLEWARE = ['preview_site.views.PreviewBoundary']
USE_TZ = True
DEFAULT_CHARSET = 'utf-8'
LOGGING = {'version': 1, 'disable_existing_loggers': False,
           'handlers': {'console': {'class': 'logging.StreamHandler'}},
           'root': {'handlers': ['console'], 'level': 'WARNING'}}
