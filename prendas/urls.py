from django.urls import path
from . import views

app_name = "prendas"

urlpatterns = [
    path("crear/", views.crear_prenda, name="crear"),
    path("stock/", views.stock, name="stock"),
    path("eliminar/<int:prenda_id>/", views.eliminar_prenda, name="eliminar"),
    path("buscar/", views.buscar_codigo, name="buscar_codigo"),
]
