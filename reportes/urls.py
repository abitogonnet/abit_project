from django.urls import path
from . import views

app_name = "reportes"

urlpatterns = [
    path("", views.home, name="home"),
    path("exportar/", views.exportar_excel, name="exportar_excel"),
]
