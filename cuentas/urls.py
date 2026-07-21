from django.urls import path
from . import views

app_name = "cuentas"
urlpatterns = [
    path("login/", views.iniciar_sesion, name="login"),
    path("logout/", views.cerrar_sesion, name="logout"),
    path("configuracion-inicial/", views.configuracion_inicial, name="configuracion_inicial"),
    path("administracion/usuarios/", views.usuarios, name="usuarios"),
    path("administracion/usuarios/crear/", views.usuario_crear, name="usuario_crear"),
    path("administracion/usuarios/<int:pk>/editar/", views.usuario_editar, name="usuario_editar"),
    path("administracion/usuarios/<int:pk>/estado/", views.usuario_estado, name="usuario_estado"),
    path("actividad/", views.actividad, name="actividad"),
]
