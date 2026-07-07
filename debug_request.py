import os, sys
os.environ['DJANGO_SETTINGS_MODULE'] = 'ai_marketing_agency.settings'
import django
django.setup()
from django.conf import settings
from django.http import HttpRequest

req = HttpRequest()
req.META = {
    'HTTP_HOST': '13.140.132.52',
    'SERVER_NAME': '13.140.132.52',
    'SERVER_PORT': '80',
    'REQUEST_METHOD': 'GET',
    'PATH_INFO': '/',
}
print('Host header:', req.get_host())
print('ALLOWED_HOSTS:', settings.ALLOWED_HOSTS)
print('Allowed?:', req.get_host() in settings.ALLOWED_HOSTS)
print()
print('Full env DJANGO_*:')
for k,v in os.environ.items():
    if k.startswith('DJANGO_'):
        print(' ', k, '=', repr(v[:60]))