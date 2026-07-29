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
from catalogo.models import Combo, ImagenTraje, Traje
from catalogo.stock_sizes import actualizar_talles_traje, talles_stock_para_color
from core.models import ConfiguracionSitio
from prendas.models import Color, Prenda


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
        self.assertNotContains(response, "variantes", html=False)
        self.assertNotContains(response, "Formato de variante inválido")
        self.assertContains(response, "Talles detectados en Stock")


class CatalogoStockSizeTests(TestCase):
    def setUp(self):
        self.color_topo = Color.objects.get(
            clave_normalizada=Color.normalizar_clave("Gris Topo")
        )

    def prenda(self, codigo, categoria, talle, estado=Prenda.E_DISP, color="Gris Topo"):
        return Prenda.objects.create(
            codigo=codigo,
            categoria=categoria,
            color=color,
            talle=talle,
            estado=estado,
        )

    def traje(self, color=None):
        traje = Traje.objects.create(
            linea=Traje.LINEA_NACIONAL,
            foto_modelo="trajes/modelo.jpg",
            foto_colgado="trajes/colgado.jpg",
            tela="Modelo Topo",
            descripcion="Descripción comercial",
            precio="120000",
            color_stock=color or self.color_topo,
        )
        actualizar_talles_traje(traje)
        return traje

    def test_talles_distintos_ordenados_incluyen_estados_temporales(self):
        self.prenda("SA-T-1", Prenda.C_SACO, "XL")
        self.prenda("SA-T-2", Prenda.C_SACO, "M", Prenda.E_RES)
        self.prenda("SA-T-3", Prenda.C_SACO, "L", Prenda.E_ENT)
        self.prenda("SA-T-4", Prenda.C_SACO, "L", Prenda.E_LAV)
        self.prenda("PA-T-1", Prenda.C_PANTALON, "50")
        self.prenda("PA-T-2", Prenda.C_PANTALON, "42", Prenda.E_RES)
        self.prenda("PA-T-3", Prenda.C_PANTALON, "44", Prenda.E_ENT)
        self.prenda("PA-T-4", Prenda.C_PANTALON, "44", Prenda.E_LAV)

        talles = talles_stock_para_color(self.color_topo)

        self.assertEqual(talles["sacos"], ["M", "L", "XL"])
        self.assertEqual(talles["pantalones"], ["42", "44", "50"])

    def test_unica_unidad_danada_no_publica_talle_pero_otra_util_si(self):
        self.prenda("SA-D-1", Prenda.C_SACO, "S", Prenda.E_DAN)
        self.prenda("SA-D-2", Prenda.C_SACO, "M", Prenda.E_DAN)
        self.prenda("SA-D-3", Prenda.C_SACO, "M", Prenda.E_RES)

        talles = talles_stock_para_color(self.color_topo)

        self.assertEqual(talles["sacos"], ["M"])

    def test_color_sin_una_categoria_devuelve_lista_vacia_y_endpoint_200(self):
        self.prenda("PA-S-1", Prenda.C_PANTALON, "42")
        user = get_user_model().objects.create_superuser(
            username="stock-preview",
            password="secret123",
        )
        self.client.force_login(user)

        response = self.client.get(
            reverse("catalogo:talles_stock"),
            {"color_id": self.color_topo.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"sacos": [], "pantalones": ["42"]})

    def test_nuevo_talle_actualiza_traje_sin_editarlo(self):
        self.prenda("SA-N-1", Prenda.C_SACO, "M")
        traje = self.traje()
        self.assertEqual(traje.talles_saco_stock, ["M"])

        self.prenda("SA-N-2", Prenda.C_SACO, "3XL")

        traje.refresh_from_db()
        self.assertEqual(traje.talles_saco_stock, ["M", "3XL"])

    def test_gris_oscuro_y_gris_topo_comparten_talles(self):
        color_oscuro = (
            Color.objects.filter(
                clave_normalizada=Color.normalizar_clave("Gris Oscuro")
            ).first()
            or Color.objects.create(nombre="Gris Oscuro")
        )
        self.prenda(
            "SA-G-1",
            Prenda.C_SACO,
            "L",
            color="gris oscuro",
        )

        talles_topo = talles_stock_para_color(self.color_topo)
        talles_oscuro = talles_stock_para_color(color_oscuro)

        self.assertEqual(talles_topo["sacos"], ["L"])
        self.assertEqual(talles_oscuro["sacos"], ["L"])

    def test_formulario_crea_y_edita_traje_sin_variantes_manual(self):
        self.prenda("SA-F-1", Prenda.C_SACO, "L")
        self.prenda("PA-F-1", Prenda.C_PANTALON, "44")
        form_class = MODEL_FORMS["traje"]
        data = {
            "linea": Traje.LINEA_NACIONAL,
            "tela": "Modelo automático",
            "descripcion": "Texto comercial",
            "color_stock": str(self.color_topo.pk),
            "precio": "130000",
            "activo": "on",
        }
        files = {
            "foto_modelo": CatalogoMobileImageUploadTests().image_upload(
                "principal.jpg", "JPEG"
            ),
            "foto_colgado": CatalogoMobileImageUploadTests().image_upload(
                "detalle.jpg", "JPEG"
            ),
        }

        form = form_class(data, files)
        self.assertTrue(form.is_valid(), form.errors.as_json())
        traje = form.save()
        self.assertEqual(traje.talles_saco_stock, ["L"])
        self.assertEqual(traje.talles_pantalon_stock, ["44"])

        color_azul = Color.objects.get(
            clave_normalizada=Color.normalizar_clave("Azul Oscuro")
        )
        self.prenda(
            "SA-F-2",
            Prenda.C_SACO,
            "XL",
            color="Azul Oscuro",
        )
        edit_data = data | {
            "color_stock": str(color_azul.pk),
            "precio": "140000",
        }
        edit_form = form_class(edit_data, instance=traje)
        self.assertTrue(edit_form.is_valid(), edit_form.errors.as_json())
        edit_form.save()
        traje.refresh_from_db()
        self.assertEqual(traje.color_stock, color_azul)
        self.assertEqual(traje.talles_saco_stock, ["XL"])
        self.assertEqual(traje.talles_pantalon_stock, [])
