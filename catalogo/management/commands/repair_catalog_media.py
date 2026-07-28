from django.core.management.base import BaseCommand

from catalogo.media_repair import repair_catalog_media


class Command(BaseCommand):
    help = (
        "Repara rutas de imagen del catalogo y vuelve a copiar archivos faltantes "
        "desde una carpeta base local."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--quiet",
            action="store_true",
            help="Muestra solo el resumen final.",
        )

    def handle(self, *args, **options):
        summary = repair_catalog_media()
        missing_files = summary["missing_files"]

        if not options["quiet"]:
            self.stdout.write(
                "Campos revisados: {checked_fields} | Rutas corregidas: {rewritten_paths} | "
                "Archivos copiados: {copied_files}".format(**summary)
            )

            if missing_files:
                self.stdout.write(
                    self.style.WARNING(
                        f"Imagenes sin recuperar automaticamente: {len(missing_files)}"
                    )
                )
                for item in missing_files[:20]:
                    self.stdout.write(
                        f"- {item.model} #{item.object_id} | {item.field_name} | {item.stored_name}"
                    )
            else:
                self.stdout.write(self.style.SUCCESS("No quedaron imagenes faltantes."))

        if missing_files:
            self.stdout.write(
                self.style.WARNING(
                    "Quedaron referencias sin archivo fisico. Si esas fotos no estan en la "
                    "carpeta base ni en el storage actual, hay que restaurarlas desde una copia."
                )
            )
