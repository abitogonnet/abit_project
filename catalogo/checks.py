from django.conf import settings
from django.core.checks import Warning, register


@register()
def persistent_media_storage_check(app_configs, **kwargs):
    if settings.DEBUG or getattr(settings, "AWS_STORAGE_BUCKET_NAME", ""):
        return []
    if getattr(settings, "MEDIA_ROOT_ENV", ""):
        return []
    return [
        Warning(
            "MEDIA usa el filesystem local y puede perderse al reiniciar Render.",
            hint=(
                "Configurá AWS_STORAGE_BUCKET_NAME o MEDIA_ROOT sobre un "
                "Persistent Disk. STATIC no reemplaza almacenamiento de MEDIA."
            ),
            id="catalogo.W001",
        )
    ]
