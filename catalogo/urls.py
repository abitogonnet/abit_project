from django.urls import path
from . import views

app_name = "catalogo"
urlpatterns = [
    path("", views.gestion, name="gestion"),
    path("<str:tipo>/nuevo/", views.editar, name="crear"),
    path("<str:tipo>/<int:pk>/", views.editar, name="editar"),
    path("<str:tipo>/<int:pk>/publicar/", views.publicar, name="publicar"),
]
