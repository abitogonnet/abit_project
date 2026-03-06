from django.urls import path
from . import views

app_name = "visitas"

urlpatterns = [
    path("", views.listar, name="listar"),
    path("crear/", views.crear, name="crear"),
    path("<int:pk>/cancelar/", views.cancelar, name="cancelar"),
    path("<int:pk>/confirmar/", views.confirmar, name="confirmar"),
]
