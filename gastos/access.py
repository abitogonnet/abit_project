from django.core.exceptions import PermissionDenied
from cuentas.access import puede_finanzas


def require_finanzas_access(request, *, title="Finanzas protegidas"):
    if not puede_finanzas(request.user):
        raise PermissionDenied
    return None
