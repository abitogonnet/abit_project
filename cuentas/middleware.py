from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.urls import resolve, Resolver404

from .access import puede_finanzas, rol_de
from .models import PerfilUsuario


class AccesoAbitoMiddleware:
    PUBLIC_NAMES = {"cuentas:login", "cuentas:configuracion_inicial"}
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
        if not request.path_info.startswith(static_url) and name not in self.PUBLIC_NAMES:
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path(), settings.LOGIN_URL)
            if rol_de(request.user) == PerfilUsuario.COSTURERA:
                if name not in {"alquileres:ruedos", "cuentas:cambiar_password", "cuentas:logout"}:
                    raise PermissionDenied
            if name in self.FINANCE_NAMES and not puede_finanzas(request.user):
                raise PermissionDenied
        return self.get_response(request)
