from django.urls import path
from . import views

app_name = "gastos"

urlpatterns = [
    path("", views.home, name="home"),
    path("crear/", views.crear, name="crear"),
    path("division-bienes/", views.division_bienes, name="division_bienes"),
    path("movimientos/", views.movimientos, name="movimientos"),
]
