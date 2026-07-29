from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.datastructures import MultiValueDict
from PIL import Image

from catalogo.forms import IMAGE_ERROR, MODEL_FORMS
from catalogo.image_utils import MAX_IMAGE_DIMENSION, normalize_uploaded_image
from catalogo.media_repair import normalize_stored_image_name, repair_catalog_media
from catalogo.models import Combo, ImagenTraje, TalleColorTraje, Traje
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


class CatalogoMobileImageUploadTests(TestCase):
    def image_upload(
        self,
        name,
        image_format,
        *,
        size=(80, 120),
        exif=None,
        content_type=None,
    ):
        buffer = BytesIO()
        image = Image.new("RGB", size, (90, 120, 150))
        save_kwargs = {"format": image_format}
        if exif is not None:
            save_kwargs["exif"] = exif
        image.save(buffer, **save_kwargs)
        return SimpleUploadedFile(
            name,
            buffer.getvalue(),
            content_type=content_type or f"image/{image_format.lower()}",
        )

    def base_data(self):
        return {
            "linea": Traje.LINEA_NACIONAL,
            "tela": "Gris Perla",
            "descripcion": "Traje de prueba",
            "precio": "120000.00",
            "activo": "on",
            "variantes": "Gris Perla | 48 | 42\nAzul | 50 | 44",
        }

    def test_acepta_jpg_jpeg_png_webp_heic_y_heif_por_contenido(self):
        cases = [
            ("foto.jpg", "JPEG", "image/jpeg"),
            ("foto.jpeg", "JPEG", "image/jpeg"),
            ("foto.png", "PNG", "image/png"),
            ("foto.webp", "WEBP", "image/webp"),
            ("foto.heic", "HEIF", "image/heic"),
            ("foto.heif", "HEIF", "image/heif"),
        ]
        for name, image_format, content_type in cases:
            with self.subTest(name=name):
                field = MODEL_FORMS["traje"]().fields["foto_modelo"]
                normalized = field.clean(
                    self.image_upload(
                        name,
                        image_format,
                        content_type=content_type,
                    )
                )
                self.assertTrue(normalized.name.endswith(".jpg"))
                with Image.open(BytesIO(normalized.read())) as image:
                    self.assertEqual(image.format, "JPEG")

    def test_corrige_orientacion_exif_vertical(self):
        exif = Image.Exif()
        exif[274] = 6
        upload = self.image_upload(
            "vertical.jpg",
            "JPEG",
            size=(120, 80),
            exif=exif,
        )

        normalized = normalize_uploaded_image(upload, "vertical")

        with Image.open(BytesIO(normalized.read())) as image:
            self.assertEqual(image.size, (80, 120))

    def test_foto_grande_se_optimiza_y_limita_dimensiones(self):
        upload = self.image_upload(
            "foto-grande.jpg",
            "JPEG",
            size=(3000, 1800),
        )

        normalized = normalize_uploaded_image(upload, "foto-grande")

        with Image.open(BytesIO(normalized.read())) as image:
            self.assertEqual(max(image.size), MAX_IMAGE_DIMENSION)
            self.assertLess(normalized.size, upload.size)

    def test_archivo_falso_muestra_error_claro_y_registra_detalle(self):
        form = MODEL_FORMS["traje"](
            self.base_data(),
            {
                "foto_modelo": SimpleUploadedFile(
                    "engaño.jpg",
                    b"esto no es una imagen",
                    content_type="image/jpeg",
                ),
                "foto_colgado": self.image_upload("detalle.jpg", "JPEG"),
            },
        )

        with self.assertLogs("catalogo.forms", level="ERROR"):
            self.assertFalse(form.is_valid())

        self.assertIn("engaño.jpg", form.errors["foto_modelo"][0])
        self.assertIn(IMAGE_ERROR, form.errors["foto_modelo"][0])
        self.assertEqual(form.data["tela"], "Gris Perla")

    def test_archivo_excesivo_se_rechaza_con_mensaje_claro(self):
        upload = self.image_upload("grande.jpg", "JPEG")
        upload.size = 51 * 1024 * 1024
        field = MODEL_FORMS["traje"]().fields["foto_modelo"]

        with self.assertLogs("catalogo.forms", level="ERROR"):
            with self.assertRaisesMessage(Exception, IMAGE_ERROR):
                field.clean(upload)

    def test_crea_traje_completo_con_principal_detalle_y_galeria(self):
        Combo.objects.create(
            nombre="Combo 1",
            foto=self.image_upload("combo.jpg", "JPEG"),
            descripcion="Traje + camisa",
            precio_importado="150000",
            precio_nacional="140000",
            precio_ninos="90000",
            precio_unico="140000",
        )
        files = MultiValueDict({
            "foto_modelo": [self.image_upload("principal.heic", "HEIF")],
            "foto_colgado": [self.image_upload("detalle.webp", "WEBP")],
            "imagenes_galeria": [
                self.image_upload("galeria-1.png", "PNG"),
                self.image_upload("galeria-2.jpeg", "JPEG"),
            ],
        })
        form = MODEL_FORMS["traje"](self.base_data(), files)

        self.assertTrue(form.is_valid(), form.errors.as_json())
        traje = form.save()

        self.assertEqual(Traje.objects.count(), 1)
        self.assertEqual(TalleColorTraje.objects.filter(traje=traje).count(), 2)
        self.assertEqual(ImagenTraje.objects.filter(traje=traje).count(), 2)
        self.assertTrue(traje.foto_modelo.name.endswith(".jpg"))
        self.assertTrue(traje.foto_colgado.name.endswith(".jpg"))
        self.assertTrue(all(
            image.imagen.name.endswith(".jpg")
            for image in traje.imagenes_galeria.all()
        ))

    def test_formulario_de_catalogo_es_multipart_y_admite_galeria_multiple(self):
        user = get_user_model().objects.create_superuser(
            username="catalog-owner",
            email="owner@example.com",
            password="secret123",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("catalogo:crear", args=["traje"]))

        self.assertContains(response, 'enctype="multipart/form-data"', html=False)
        self.assertContains(response, 'name="imagenes_galeria"', html=False)
        self.assertContains(response, "multiple", html=False)
