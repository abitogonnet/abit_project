from django.conf import settings
from django.core.checks import Error, Warning, register
from django.core.files.storage import FileSystemStorage, default_storage


@register()
def persistent_media_storage_check(app_configs, **kwargs):
    if not getattr(settings, "IS_RENDER", False):
        return []
    bucket = getattr(settings, "AWS_STORAGE_BUCKET_NAME", "")
    if bucket:
        missing = [name for name in (
            "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_S3_ENDPOINT_URL",
        ) if not getattr(settings, name, None)]
        if missing:
            return [Error(
                "El storage S3/R2 tiene una configuración incompleta.",
                hint="Configurá las variables requeridas: " + ", ".join(missing),
                id="catalogo.E002",
            )]
        if not isinstance(default_storage, FileSystemStorage):
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
