from django.apps import apps
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand
from django.db import connection, models

from catalogo.media_repair import normalize_stored_image_name


class Command(BaseCommand):
    help = (
        "Audita todos los ImageField del proyecto sin mostrar credenciales."
    )

    def handle(self, *args, **options):
        storage_name = (
            f"{default_storage.__class__.__module__}."
            f"{default_storage.__class__.__name__}"
        )
        self.stdout.write(f"Storage por defecto: {storage_name}")
        checked = ok = missing = errors = 0
        available_tables = set(connection.introspection.table_names())

        for model in apps.get_models():
            image_fields = [
                field
                for field in model._meta.fields
                if isinstance(field, models.ImageField)
            ]
            if not image_fields:
                continue
            if model._meta.db_table not in available_tables:
                errors += 1
                self.stderr.write(
                    f"ERROR | {model._meta.label} | tabla no existente: "
                    f"{model._meta.db_table}"
                )
                continue
            field_names = [field.name for field in image_fields]
            for instance in (
                model._default_manager.only("pk", *field_names).iterator()
            ):
                for model_field in image_fields:
                    checked += 1
                    image = getattr(instance, model_field.name)
                    name = getattr(image, "name", "") or ""
                    reference = (
                        f"{model._meta.label}#{instance.pk}."
                        f"{model_field.name}"
                    )
                    product_name = str(instance)
                    if not name:
                        missing += 1
                        self.stdout.write(
                            f"FALTANTE | {reference} | producto={product_name!r} | nombre vacío | "
                            f"storage={image.storage.__class__.__name__}"
                        )
                        continue
                    try:
                        exists = image.storage.exists(name)
                        url = image.url
                    except Exception as exc:
                        errors += 1
                        self.stderr.write(
                            f"ERROR | {reference} | nombre={name!r} | "
                            f"storage={image.storage.__class__.__name__} | "
                            f"{exc}"
                        )
                        continue
                    legacy = normalize_stored_image_name(name) != name
                    status = "LEGACY" if legacy else ("OK" if exists else "FALTANTE")
                    if exists:
                        ok += 1
                    else:
                        missing += 1
                    self.stdout.write(
                        f"{status} | {reference} | producto={product_name!r} | nombre={name!r} | "
                        f"storage={image.storage.__class__.__name__} | "
                        f"exists={exists} | url={url}"
                    )

        self.stdout.write(
            self.style.SUCCESS(
                f"Resumen: revisadas={checked} ok={ok} "
                f"faltantes={missing} errores={errors}"
            )
        )
