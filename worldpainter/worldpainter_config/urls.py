# worldpainter/worldpainter_config/urls.py
from django.contrib import admin # <-- Change the import back
from django.urls import path
from django.views.generic.base import RedirectView

urlpatterns = [
    path('', RedirectView.as_view(url='/admin/', permanent=False)),
    path("admin/", admin.site.urls), # <-- Change back to admin.site.urls
]