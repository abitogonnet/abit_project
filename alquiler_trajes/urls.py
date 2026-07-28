from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, include
from core import views as core_views

urlpatterns = [
    path("", core_views.home, name="home"),
    path("", include("core.urls")),
    path("cuenta/", include("cuentas.urls")),
    path("admin/", admin.site.urls),

    path("gestion/", include("alquileres.urls")),
    path("prendas/", include("prendas.urls")),
    path("visitas/", include("visitas.urls")),
    path("catalogo/", include("catalogo.urls")),
    path("gastos/", include("gastos.urls")),
    path("reportes/", include("reportes.urls")),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
