from pathlib import Path

from django.conf import settings
from django.core.files.storage import FileSystemStorage, default_storage
from django.core.management.base import BaseCommand, CommandError

from catalogo.media_migration import migrate_catalog_media


class Command(BaseCommand):
    help = (
        "Migra imágenes existentes del catálogo desde un MEDIA_ROOT local "
        "hacia el storage persistente configurado."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--source-root",
            default=getattr(settings, "LEGACY_MEDIA_ROOT", settings.MEDIA_ROOT),
            help="Raíz local donde todavía existen los archivos originales.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Informa qué migraría sin subir ni modificar la base.",
        )
        parser.add_argument(
            "--allow-filesystem-destination",
            action="store_true",
            help="Solo para pruebas controladas; permite destino FileSystemStorage.",
        )

    def handle(self, *args, **options):
        source_root = Path(options["source_root"]).resolve()
        if not source_root.is_dir():
            raise CommandError(
                f"No existe el directorio de origen: {source_root}"
            )

        if (
            isinstance(default_storage, FileSystemStorage)
            and not options["allow_filesystem_destination"]
            and not options["dry_run"]
        ):
            raise CommandError(
                "El storage destino continúa siendo filesystem local. "
                "Configurá primero AWS_STORAGE_BUCKET_NAME y sus credenciales."
            )

        result = migrate_catalog_media(
            source_root=source_root,
            destination_storage=default_storage,
            dry_run=options["dry_run"],
            check_destination=not (
                options["dry_run"]
                and isinstance(default_storage, FileSystemStorage)
                and not options["allow_filesystem_destination"]
            ),
        )

        self.stdout.write(f"Referencias revisadas: {result.references_checked}")
        self.stdout.write(f"Archivos encontrados: {result.files_found}")
        self.stdout.write(
            self.style.SUCCESS(f"Imágenes migradas: {result.migrated}")
        )
        self.stdout.write(
            f"Ya estaban en almacenamiento persistente: "
            f"{result.already_persistent}"
        )
        self.stdout.write(
            self.style.WARNING(
                f"Archivos originales no encontrados: {len(result.missing)}"
            )
        )
        for missing in result.missing:
            self.stdout.write(f"  FALTANTE: {missing}")

        if result.errors:
            for error in result.errors:
                self.stderr.write(f"  ERROR: {error}")
            raise CommandError(
                f"La migración terminó con {len(result.errors)} errores."
            )
