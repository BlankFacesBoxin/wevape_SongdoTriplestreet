import os
from django.core.wsgi import get_wsgi_application

if os.environ.get('DJANGO_SETTINGS_MODULE') not in (None, 'preview_site.settings'):
    raise RuntimeError('Preview requires preview_site.settings exclusively.')
os.environ['DJANGO_SETTINGS_MODULE'] = 'preview_site.settings'
application = get_wsgi_application()
