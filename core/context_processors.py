from django.conf import settings
from django.core.cache import cache
from django.db.utils import OperationalError, ProgrammingError

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

    return {
        "site_config": config,
    }
