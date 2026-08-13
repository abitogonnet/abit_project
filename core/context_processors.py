from django.conf import settings
from django.core.cache import cache
from django.db.utils import OperationalError, ProgrammingError
from django.utils import timezone

from .models import ConfiguracionSitio


def site_config(request):
    cache_key = "abito:site-config"
    config = cache.get(cache_key)
    if config is None:
        try:
            config = ConfiguracionSitio.load()
            cache.set(
                cache_key,
                config,
                getattr(settings, "SITE_CONFIG_CACHE_SECONDS", 60),
            )
        except (OperationalError, ProgrammingError):
            config = None

    context = {"site_config": config}
    if request.user.is_authenticated:
        try:
            from alquileres.models import Alquiler
            from prendas.models import Prenda
            from visitas.models import Visita
            hoy = timezone.localdate()
            avisos = [
                {"label": "Entregas de hoy", "total": Alquiler.objects.filter(fecha_entrega=hoy, estado_alquiler=Alquiler.EST_RESERVADO).count(), "url": "/alquileres/entregas/"},
                {"label": "Devoluciones atrasadas", "total": Alquiler.objects.filter(fecha_devolucion__lt=hoy, estado_alquiler=Alquiler.EST_ENTREGADO).count(), "url": "/alquileres/retrasados/"},
                {"label": "Saldos pendientes", "total": Alquiler.objects.filter(estado_alquiler__in=Alquiler.ESTADOS_ALQUILER_ACTIVOS, estado_saldo=Alquiler.SAL_PEND, saldo__gt=0).count(), "url": "/alquileres/ver/?saldo=PENDIENTE"},
                {"label": "Visitas de hoy", "total": Visita.objects.filter(fecha_visita=hoy, estado=Visita.ESTADO_CONFIRMADA).count(), "url": "/visitas/?alcance=hoy"},
                {"label": "Prendas en lavandería", "total": Prenda.objects.filter(estado=Prenda.E_LAV).count(), "url": "/prendas/stock/?estado=LAVANDERIA"},
            ]
            context["avisos_globales"] = [aviso for aviso in avisos if aviso["total"]]
            context["avisos_globales_total"] = sum(aviso["total"] for aviso in avisos)
        except (OperationalError, ProgrammingError):
            pass
    return context
