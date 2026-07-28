from django.urls import path
from . import views

app_name = "visitas"

urlpatterns = [
    path("", views.listar, name="listar"),
    path("crear/", views.reservar, name="crear"),
    path("gestion/<int:pk>/", views.detalle, name="detalle"),
    path("gestion/<int:pk>/crear-alquiler/", views.crear_alquiler, name="crear_alquiler"),
    path("gestion/bloqueos/", views.bloqueos, name="bloqueos"),
    path("gestion/bloqueos/<int:pk>/eliminar/", views.eliminar_bloqueo, name="eliminar_bloqueo"),

    path(
        "reservar/",
        views.reservar,
        name="reservar"
    ),

    path(
        "confirmada/",
        views.confirmada,
        name="confirmada"
    ),

    path(
        "horarios-disponibles/",
        views.horarios_disponibles,
        name="horarios_disponibles"
    ),

]
