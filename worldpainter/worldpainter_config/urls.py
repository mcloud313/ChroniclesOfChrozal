from django.contrib import admin
from django.urls import path

# --- NEW: Customize the Admin Site Titles ---
admin.site.site_header = "Chrozal Admin Portal"
admin.site.site_title = "Chrozal Admin"
admin.site.index_title = "Welcome to the WorldPainter"

urlpatterns = [
    path('admin/', admin.site.urls),
]