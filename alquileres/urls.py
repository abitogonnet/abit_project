from django.urls import path
from . import views

app_name = "alquileres"

urlpatterns = [
    path("", views.home, name="home"),
    path("crear/", views.crear, name="crear"),
    path("ver/", views.ver, name="ver"),
    path("ruedos/", views.ruedos, name="ruedos"),
    path("panel/<int:alquiler_id>/<str:panel_name>/", views.panel, name="panel"),

    # NUEVOS
    path("entregas/", views.entregas, name="entregas"),
    path("retrasados/", views.retrasados, name="retrasados"),
]
