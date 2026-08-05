from django.core.management.base import BaseCommand

from catalogo.media_repair import repair_catalog_media


class Command(BaseCommand):
    help = "Normaliza rutas heredadas y recupera imágenes locales del catálogo."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        result = repair_catalog_media(dry_run=dry_run)
        mode = "SIMULACIÓN" if dry_run else "REPARACIÓN"
        self.stdout.write(
            f"{mode}: revisadas={result['checked_fields']} "
            f"rutas={result['rewritten_paths']} copias={result['copied_files']}"
        )
        for item in result["missing_files"]:
            self.stdout.write(self.style.WARNING(
                f"REQUIERE CARGA MANUAL | {item.model}#{item.object_id} | "
                f"{item.field_name} | {item.stored_name}"
            ))
