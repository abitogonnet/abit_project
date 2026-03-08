from django.urls import path
from . import views

app_name = "alquileres"

urlpatterns = [
    path("", views.home, name="home"),
    path("crear/", views.crear, name="crear"),
    path("ver/", views.ver, name="ver"),
    path("eliminar/<int:alq_id>/", views.eliminar, name="eliminar"),

    path("entregas/", views.entregas, name="entregas"),
    path("retrasados/", views.retrasados, name="retrasados"),
]
