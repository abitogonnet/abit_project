from django.db.utils import OperationalError, ProgrammingError

from .models import ConfiguracionSitio


def site_config(request):
    try:
        config = ConfiguracionSitio.load()
    except (OperationalError, ProgrammingError):
        config = None

    return {
        "site_config": config,
    }
