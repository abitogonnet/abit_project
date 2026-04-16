from django.urls import path
from . import views

app_name = "prendas"

urlpatterns = [
    path("crear/", views.crear_prenda, name="crear"),
    path("stock/", views.stock, name="stock"),
    path("stock/<int:pk>/editar/", views.editar_prenda, name="editar"),
    path("buscar/", views.buscar_prenda, name="buscar_prenda"),
]
