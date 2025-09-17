from django.contrib import admin
from django.urls import path
from django.views.generic.base import RedirectView

# --- NEW: Customize the Admin Site Titles ---
admin.site.site_header = "Chrozal Admin Portal"
admin.site.site_title = "Chrozal Admin"
admin.site.index_title = "Welcome to the Chrozal Admin Portal"

urlpatterns = [
    # Add this line to redirect the root URL to the admin page
    path('', RedirectView.as_view(url='/admin/', permanent=False)),
    path("admin/", admin.site.urls),
]