from django.apps import AppConfig


class CatalogoConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "catalogo"

    def ready(self):
        try:
            from pillow_heif import register_heif_opener
        except ImportError:
            return

        register_heif_opener()
