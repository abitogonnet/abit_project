from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.urls import resolve, Resolver404
from django.shortcuts import redirect

from .access import puede_finanzas, rol_de
from .models import PerfilUsuario


class AccesoAbitoMiddleware:
    PUBLIC_NAMES = {
        "home", "publico:home", "cuentas:login", "cuentas:configuracion_inicial",
        "visitas:reservar", "visitas:confirmada", "visitas:horarios_disponibles",
    }
    FINANCE_NAMES = {"gastos:home", "gastos:crear", "gastos:division_bienes", "gastos:movimientos", "reportes:home", "reportes:exportar_excel"}

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            match = resolve(request.path_info)
            name = f"{match.namespace}:{match.url_name}" if match.namespace else match.url_name
        except Resolver404:
            name = None
        static_url = settings.STATIC_URL or "/static/"
        media_url = settings.MEDIA_URL or "/media/"
        if not request.path_info.startswith((static_url, media_url)) and name not in self.PUBLIC_NAMES:
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path(), settings.LOGIN_URL)
            try:
                debe_cambiar_password = request.user.perfil.debe_cambiar_password
            except PerfilUsuario.DoesNotExist:
                debe_cambiar_password = False
            if (
                debe_cambiar_password
                and name not in {"cuentas:cambiar_password", "cuentas:logout"}
            ):
                return redirect("cuentas:cambiar_password")
            if rol_de(request.user) == PerfilUsuario.COSTURERA:
                if name not in {"alquileres:ruedos", "cuentas:cambiar_password", "cuentas:logout"}:
                    raise PermissionDenied
            if name in self.FINANCE_NAMES and not puede_finanzas(request.user):
                raise PermissionDenied
        return self.get_response(request)
