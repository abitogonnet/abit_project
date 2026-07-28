from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from catalogo.image_utils import normalize_uploaded_image
from catalogo.media_repair import normalize_stored_image_name, repair_catalog_media
from catalogo.models import Traje
from core.models import ConfiguracionSitio


class ConfiguracionVisitasAdminTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="secret123",
        )
        self.client.force_login(self.user)

    def test_catalog_changelist_redirects_to_visit_settings(self):
        response = self.client.get(reverse("admin:catalogo_configuracionvisitas_changelist"))

        config = ConfiguracionSitio.objects.get()
        self.assertRedirects(
            response,
            reverse("admin:catalogo_configuracionvisitas_change", args=[config.pk]),
        )

    def test_catalog_admin_saves_visit_address(self):
        config = ConfiguracionSitio.load()
        response = self.client.post(
            reverse("admin:catalogo_configuracionvisitas_change", args=[config.pk]),
            {
                "direccion_post_reserva": "Calle 123, Gonnet",
                "mensaje_confirmacion": "Te esperamos.",
                "_save": "Save",
            },
        )

        self.assertEqual(response.status_code, 302)

        config.refresh_from_db()
        self.assertEqual(config.direccion_post_reserva, "Calle 123, Gonnet")


class CatalogoImageNormalizationTests(TestCase):
    def test_normalize_uploaded_image_returns_jpeg_with_standard_extension(self):
        normalized = normalize_uploaded_image(
            self._build_uploaded_image("foto-modelo", "PNG"),
            fallback_name="traje-foto-modelo",
        )

        self.assertTrue(normalized.name.endswith(".jpg"))

        with Image.open(BytesIO(normalized.read())) as saved_image:
            self.assertEqual(saved_image.format, "JPEG")

    def _build_uploaded_image(self, file_name, image_format):
        buffer = BytesIO()
        Image.new("RGBA", (30, 30), (255, 0, 0, 160)).save(buffer, format=image_format)
        return SimpleUploadedFile(
            file_name,
            buffer.getvalue(),
            content_type=f"image/{image_format.lower()}",
        )

    def test_normalize_stored_image_name_handles_media_prefixes_and_absolute_urls(self):
        self.assertEqual(
            normalize_stored_image_name("/media/trajes/foto.jpg"),
            "trajes/foto.jpg",
        )
        self.assertEqual(
            normalize_stored_image_name("media\\zapatos\\detalle.jpeg"),
            "zapatos/detalle.jpeg",
        )
        self.assertEqual(
            normalize_stored_image_name("https://abito.test/media/combos/look%201.jpg"),
            "combos/look 1.jpg",
        )

    @override_settings(MEDIA_URL="/media/")
    def test_repair_catalog_media_restores_missing_files_from_seed_root(self):
        with TemporaryDirectory() as storage_dir, TemporaryDirectory() as seed_dir:
            with override_settings(MEDIA_ROOT=storage_dir, MEDIA_SEED_ROOT=seed_dir):
                traje = Traje.objects.create(
                    linea=Traje.LINEA_IMPORTADA,
                    tela="Alpaca",
                    precio="120000.00",
                    foto_modelo=self._build_uploaded_image("modelo.png", "PNG"),
                    foto_colgado=self._build_uploaded_image("colgado.png", "PNG"),
                )

                for file_name in [traje.foto_modelo.name, traje.foto_colgado.name]:
                    Path(storage_dir, file_name).unlink()

                self._write_seed_image(Path(seed_dir) / "trajes" / "modelo-recuperado.jpg")
                self._write_seed_image(Path(seed_dir) / "trajes" / "colgado-recuperado.jpg")

                Traje.objects.filter(pk=traje.pk).update(
                    foto_modelo="/media/trajes/modelo-recuperado.jpg",
                    foto_colgado="https://abito.test/media/trajes/colgado-recuperado.jpg",
                )

                summary = repair_catalog_media(seed_roots=[Path(seed_dir)])

                traje.refresh_from_db()

                self.assertEqual(traje.foto_modelo.name, "trajes/modelo-recuperado.jpg")
                self.assertEqual(traje.foto_colgado.name, "trajes/colgado-recuperado.jpg")
                self.assertEqual(summary["rewritten_paths"], 2)
                self.assertEqual(summary["copied_files"], 2)
                self.assertFalse(summary["missing_files"])
                self.assertTrue(Path(storage_dir, traje.foto_modelo.name).exists())
                self.assertTrue(Path(storage_dir, traje.foto_colgado.name).exists())

    def _write_seed_image(self, destination):
        destination.parent.mkdir(parents=True, exist_ok=True)
        buffer = BytesIO()
        Image.new("RGB", (40, 40), (220, 180, 140)).save(buffer, format="JPEG")
        destination.write_bytes(buffer.getvalue())
