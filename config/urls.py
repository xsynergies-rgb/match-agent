from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from common.health import liveness, readiness

admin.site.site_header = "Glocal Sport admin"
admin.site.site_title = "Glocal Sport admin"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", liveness, name="health"),
    path("api/ready/", readiness, name="ready"),
    path("api/v1/auth/", include("apps.users.urls")),
    path("api/v1/", include("apps.booking.urls")),
]

if settings.DEBUG:
    from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

    urlpatterns += [
        path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
        path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    ]

# Anything else is a JSON 404, never a file: this server only answers the API and the admin.
handler404 = "common.views.not_found"
handler500 = "common.views.server_error"
