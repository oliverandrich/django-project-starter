# URL Configuration
# https://docs.djangoproject.com/en/6.1/topics/http/urls/

import re
from importlib import import_module
from urllib.parse import urlsplit

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.staticfiles.views import serve as serve_static
from django.urls import include, path, re_path
from django.views.generic import TemplateView

# A string, so the template repository stays valid Python before startproject renders it.
events = import_module("{{ project_name }}.events")

urlpatterns = [
    # Our urls
    path("", TemplateView.as_view(template_name="base.html")),
    # Admin area
    path("admin/", admin.site.urls),
    path("events/", events.stream, name="events"),
    # Django browser reload
    path("__reload__/", include("django_browser_reload.urls")),
]

# Static files from the app directories in DEBUG. serve_static checks DEBUG per request and
# returns 404 without it; granian serves STATIC_ROOT in production.
if not urlsplit(settings.STATIC_URL).netloc:
    prefix = re.escape(settings.STATIC_URL.lstrip("/"))
    urlpatterns += [re_path(rf"^{prefix}(?P<path>.*)$", serve_static)]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
