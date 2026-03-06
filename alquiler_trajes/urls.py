from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),

    path("", include("alquileres.urls")),
    path("prendas/", include("prendas.urls")),
    path("gastos/", include("gastos.urls")),
    path("reportes/", include("reportes.urls")),

    path("visitas/", include("visitas.urls")),
]
