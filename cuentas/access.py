from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied

from .models import PerfilUsuario


def rol_de(user):
    if not getattr(user, "is_authenticated", False):
        return None
    try:
        return user.perfil.rol
    except PerfilUsuario.DoesNotExist:
        return PerfilUsuario.PROPIETARIO if user.is_superuser else None


def es_propietario(user):
    return rol_de(user) == PerfilUsuario.PROPIETARIO


def puede_finanzas(user):
    return rol_de(user) in (PerfilUsuario.PROPIETARIO, PerfilUsuario.ADMINISTRADOR)


def roles_requeridos(*roles):
    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if rol_de(request.user) not in roles:
                raise PermissionDenied
            return view(request, *args, **kwargs)
        return wrapped
    return decorator

