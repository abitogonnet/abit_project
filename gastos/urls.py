from django.urls import path
from . import views

app_name = "gastos"

urlpatterns = [
    path("", views.home, name="home"),
    path("crear/", views.crear, name="crear"),
    path("division-bienes/", views.division_bienes, name="division_bienes"),
    path("movimientos/", views.movimientos, name="movimientos"),
    path("informe-semanal/", views.enviar_informe_semanal, name="enviar_informe_semanal"),
    path("informe-semanal/descargar/", views.descargar_informe_semanal, name="descargar_informe_semanal"),
]
