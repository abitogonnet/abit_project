from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.core.exceptions import ImproperlyConfigured
from django.db import models

from core.models import ConfiguracionSitio
from prendas.models import Color
from .image_utils import normalize_uploaded_image


class NormalizedImageFieldsMixin(models.Model):
    normalized_image_fields = ()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        pending_images = [
            getattr(self, field_name, None)
            for field_name in self.normalized_image_fields
            if getattr(self, field_name, None)
            and not getattr(getattr(self, field_name), "_committed", True)
        ]
        if (
            pending_images
            and getattr(settings, "IS_RENDER", False)
            and isinstance(pending_images[0].storage, FileSystemStorage)
            and not getattr(settings, "MEDIA_ROOT_ENV", "")
        ):
            raise ImproperlyConfigured(
                "El almacenamiento de imágenes no está configurado en "
                "producción. Configurá S3 o un MEDIA_ROOT persistente."
            )
        for field_name in self.normalized_image_fields:
            image_field = getattr(self, field_name, None)
            if image_field and not getattr(image_field, "_committed", True):
                source = getattr(image_field, "file", image_field)
                if getattr(source, "_catalog_normalized", False):
                    continue
                setattr(
                    self,
                    field_name,
                    normalize_uploaded_image(
                        image_field,
                        fallback_name=f"{self.__class__.__name__.lower()}-{field_name}",
                    ),
                )

        super().save(*args, **kwargs)


class StockColorsMixin(models.Model):
    colores_stock = models.ManyToManyField(
        Color,
        blank=True,
        related_name="%(class)s_catalogo",
        verbose_name="Colores disponibles",
        help_text="Se muestran solamente colores que existen en Stock para esta categoría.",
    )

    class Meta:
        abstract = True

    @property
    def colores_disponibles(self):
        return list(self.colores_stock.all().order_by("nombre"))

    @property
    def foto_publica(self):
        for name in ("foto_modelo", "foto_1"):
            image = getattr(self, name, None)
            if image:
                return image
        return None


class Traje(StockColorsMixin, NormalizedImageFieldsMixin):
    LINEA_IMPORTADA = "IMPORTADO"
    LINEA_NACIONAL = "NACIONAL"
    LINEA_UNICO = "UNICO"

    LINEAS = [
        (LINEA_IMPORTADA, "Linea importada"),
        (LINEA_NACIONAL, "Linea nacional"),
        (LINEA_UNICO, "Talles unicos"),
    ]

    linea = models.CharField(max_length=20, choices=LINEAS)
    foto_modelo = models.ImageField(upload_to="trajes/")
    foto_colgado = models.ImageField(upload_to="trajes/")
    tela = models.CharField(max_length=100)
    color_stock = models.ForeignKey(
        Color, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="modelos_catalogo",
        help_text="Color maestro usado para mostrar talles existentes en Stock.",
    )
    descripcion = models.TextField(blank=True, default="")
    precio = models.DecimalField(max_digits=10, decimal_places=2)
    talles_saco_stock = models.JSONField(default=list, blank=True)
    talles_pantalon_stock = models.JSONField(default=list, blank=True)
    activo = models.BooleanField(default=True)
    creado = models.DateTimeField(auto_now_add=True)
    normalized_image_fields = ("foto_modelo", "foto_colgado")

    class Meta:
        ordering = ["linea", "-creado"]

    def __str__(self):
        return f"{self.get_linea_display()} - {self.tela}"

    @property
    def colores_disponibles(self):
        colores = list(self.colores_stock.all().order_by("nombre"))
        if self.color_stock and self.color_stock not in colores:
            colores.append(self.color_stock)
        return colores

    @staticmethod
    def _agrupar_talles(values, limite_adulto):
        letras_orden = ["XS", "S", "M", "L", "XL", "2XL", "3XL", "4XL", "5XL"]
        numeros = sorted({int(v) for v in values if str(v).isdigit()})
        letras = [v for v in letras_orden if v in {str(x).upper() for x in values}]
        return {
            "ninos": [str(v) for v in numeros if v < limite_adulto],
            "adultos": letras + [str(v) for v in numeros if v >= limite_adulto],
        }

    @property
    def talles_saco_grupos(self):
        return self._agrupar_talles(self.talles_saco_stock, 46)

    @property
    def talles_pantalon_grupos(self):
        return self._agrupar_talles(self.talles_pantalon_stock, 40)


class TalleColorTraje(models.Model):
    traje = models.ForeignKey(
        Traje,
        on_delete=models.CASCADE,
        related_name="talles",
    )
    color = models.CharField(max_length=50)
    talle_saco = models.CharField(max_length=50)
    talle_pantalon = models.CharField(max_length=50)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.color} | Saco {self.talle_saco} | Pantalon {self.talle_pantalon}"


class ImagenTraje(NormalizedImageFieldsMixin):
    traje = models.ForeignKey(
        Traje,
        on_delete=models.CASCADE,
        related_name="imagenes_galeria",
    )
    imagen = models.ImageField(upload_to="trajes/galeria/")
    orden = models.PositiveIntegerField(default=0)
    creada = models.DateTimeField(auto_now_add=True)
    normalized_image_fields = ("imagen",)

    class Meta:
        ordering = ["orden", "id"]

    def __str__(self):
        return f"Imagen de {self.traje}"


class Chaleco(StockColorsMixin, NormalizedImageFieldsMixin):
    foto_modelo = models.ImageField(upload_to="chalecos/")
    foto_colgado = models.ImageField(upload_to="chalecos/")
    descripcion = models.TextField(blank=True, default="")
    precio = models.DecimalField(max_digits=10, decimal_places=2)
    activo = models.BooleanField(default=True)
    creado = models.DateTimeField(auto_now_add=True)
    normalized_image_fields = ("foto_modelo", "foto_colgado")

    class Meta:
        ordering = ["-creado"]

    def __str__(self):
        if self.descripcion:
            return f"Chaleco - {self.descripcion[:40]}"
        return f"Chaleco #{self.id}"


class TalleColorChaleco(models.Model):
    chaleco = models.ForeignKey(
        Chaleco,
        on_delete=models.CASCADE,
        related_name="talles",
    )
    color = models.CharField(max_length=50)
    talle = models.CharField(max_length=50)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.color} | Talle {self.talle}"


class Cinturon(StockColorsMixin, NormalizedImageFieldsMixin):
    foto_1 = models.ImageField(upload_to="cinturones/")
    foto_2 = models.ImageField(upload_to="cinturones/")
    descripcion = models.TextField(blank=True, default="")
    precio = models.DecimalField(max_digits=10, decimal_places=2)
    activo = models.BooleanField(default=True)
    creado = models.DateTimeField(auto_now_add=True)
    normalized_image_fields = ("foto_1", "foto_2")

    class Meta:
        ordering = ["-creado"]

    def __str__(self):
        if self.descripcion:
            return f"Cinturon - {self.descripcion[:40]}"
        return f"Cinturon #{self.id}"


class Corbata(StockColorsMixin, NormalizedImageFieldsMixin):
    foto_1 = models.ImageField(upload_to="corbatas/")
    foto_2 = models.ImageField(upload_to="corbatas/")
    descripcion = models.TextField(blank=True, default="")
    precio = models.DecimalField(max_digits=10, decimal_places=2)
    activo = models.BooleanField(default=True)
    creado = models.DateTimeField(auto_now_add=True)
    normalized_image_fields = ("foto_1", "foto_2")

    class Meta:
        ordering = ["-creado"]

    def __str__(self):
        if self.descripcion:
            return f"Corbata - {self.descripcion[:40]}"
        return f"Corbata #{self.id}"


class Camisa(StockColorsMixin, NormalizedImageFieldsMixin):
    foto_modelo = models.ImageField(upload_to="camisas/")
    foto_colgado = models.ImageField(upload_to="camisas/")
    descripcion = models.TextField(blank=True, default="")
    precio = models.DecimalField(max_digits=10, decimal_places=2)
    activo = models.BooleanField(default=True)
    creado = models.DateTimeField(auto_now_add=True)
    normalized_image_fields = ("foto_modelo", "foto_colgado")

    class Meta:
        ordering = ["-creado"]

    def __str__(self):
        if self.descripcion:
            return f"Camisa - {self.descripcion[:40]}"
        return f"Camisa #{self.id}"


class TalleColorCamisa(models.Model):
    camisa = models.ForeignKey(
        Camisa,
        on_delete=models.CASCADE,
        related_name="talles",
    )
    color = models.CharField(max_length=50)
    talle = models.CharField(max_length=50)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.color} | Talle {self.talle}"


class Zapato(StockColorsMixin, NormalizedImageFieldsMixin):
    foto_modelo = models.ImageField(upload_to="zapatos/")
    foto_colgado = models.ImageField(upload_to="zapatos/")
    descripcion = models.TextField(blank=True, default="")
    precio = models.DecimalField(max_digits=10, decimal_places=2)
    activo = models.BooleanField(default=True)
    creado = models.DateTimeField(auto_now_add=True)
    normalized_image_fields = ("foto_modelo", "foto_colgado")

    class Meta:
        ordering = ["-creado"]

    def __str__(self):
        if self.descripcion:
            return f"Zapato - {self.descripcion[:40]}"
        return f"Zapato #{self.id}"


class TalleColorZapato(models.Model):
    zapato = models.ForeignKey(
        Zapato,
        on_delete=models.CASCADE,
        related_name="talles",
    )
    color = models.CharField(max_length=50)
    talle = models.CharField(max_length=50)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.color} | Talle {self.talle}"


class Combo(NormalizedImageFieldsMixin):
    nombre = models.CharField(max_length=100)
    foto = models.ImageField(upload_to="combos/")
    descripcion = models.TextField(blank=True, default="")
    precio_importado = models.DecimalField(max_digits=10, decimal_places=2)
    precio_nacional = models.DecimalField(max_digits=10, decimal_places=2)
    precio_ninos = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    precio_unico = models.DecimalField(max_digits=10, decimal_places=2)
    orden = models.PositiveIntegerField(default=1)
    activo = models.BooleanField(default=True)
    disponible_todos_trajes = models.BooleanField(
        default=True,
        verbose_name="Disponible para todos los trajes activos",
        help_text="Incluye automáticamente los trajes publicados actuales y futuros.",
    )
    creado = models.DateTimeField(auto_now_add=True)
    normalized_image_fields = ("foto",)

    class Meta:
        ordering = ["orden", "id"]

    def __str__(self):
        return self.nombre

    @property
    def colores_disponibles(self):
        if not self.disponible_todos_trajes:
            return []
        colores = {}
        for traje in Traje.objects.filter(activo=True).select_related("color_stock").prefetch_related("colores_stock"):
            for color in traje.colores_disponibles:
                colores[color.clave_normalizada] = color
        return sorted(colores.values(), key=lambda color: color.nombre.casefold())


class ConfiguracionVisitas(ConfiguracionSitio):
    class Meta:
        proxy = True
        app_label = "catalogo"
        verbose_name = "Direccion de visitas"
        verbose_name_plural = "Direccion de visitas"
