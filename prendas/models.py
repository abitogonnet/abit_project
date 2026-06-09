import unicodedata

from django.db import models


class Prenda(models.Model):
    # Categorías (2 letras para el código)
    C_SACO = "SACO"
    C_PANTALON = "PANTALON"
    C_CAMISA = "CAMISA"
    C_CHALECO = "CHALECO"
    C_MONO = "MONO"
    C_CORBATA = "CORBATA"
    C_ZAPATOS = "ZAPATOS"
    C_CINTURON = "CINTURON"

    CATEGORIAS = [
        (C_SACO, "Saco"),
        (C_PANTALON, "Pantalón"),
        (C_CAMISA, "Camisa"),
        (C_CHALECO, "Chaleco"),
        (C_MONO, "Moño"),
        (C_CORBATA, "Corbata"),
        (C_ZAPATOS, "Zapatos"),
        (C_CINTURON, "Cinturón"),
    ]

    # Estados del stock
    E_DISP = "DISPONIBLE"
    E_RES = "RESERVADO"
    E_ENT = "ENTREGADO"
    E_DAN = "DANADA"

    ESTADOS = [
        (E_DISP, "Disponible"),
        (E_RES, "Reservado"),
        (E_ENT, "Entregado"),
        (E_DAN, "Dañada"),
    ]

    O_NAC = "NACIONAL"
    O_IMP = "IMPORTADO"
    ORIGENES = [
        (O_NAC, "Nacional"),
        (O_IMP, "Importado"),
    ]

    codigo = models.CharField(max_length=10, unique=True, db_index=True)
    categoria = models.CharField(max_length=20, choices=CATEGORIAS)

    # Se cargan con “desplegable + se puede escribir” (datalist) pero validados
    marca = models.CharField(max_length=40, blank=True, default="")
    color = models.CharField(max_length=40, blank=True, default="")
    talle = models.CharField(max_length=20, blank=True, default="")
    origen = models.CharField(max_length=20, choices=ORIGENES, blank=True, default="")

    estado = models.CharField(max_length=20, choices=ESTADOS, default=E_DISP)

    notas = models.CharField(max_length=200, blank=True, default="")

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    @staticmethod
    def _simplify_color(value: str) -> str:
        color = " ".join((value or "").split()).casefold()
        if not color:
            return ""
        return "".join(
            char
            for char in unicodedata.normalize("NFKD", color)
            if not unicodedata.combining(char)
        )

    @staticmethod
    def normalize_color_value(value: str) -> str:
        color = " ".join((value or "").split())
        if not color:
            return ""

        color_cf = Prenda._simplify_color(color)
        alias_map = {
            "azul oscuro": "Azul Oscuro",
            "azul osc": "Azul Oscuro",
            "azul ocs": "Azul Oscuro",
            "osc": "Azul Oscuro",
            "azul francia": "Azul Francia",
            "gris perla": "Gris Perla",
            "gris oscuro": "Gris Oscuro",
            "gris topo": "Gris Topo",
            "celeste": "Celeste",
            "rosa": "Rosa",
            "verde pistacho": "Verde Pistacho",
            "pistacho": "Verde Pistacho",
            "verde oscuro": "Verde Oscuro",
            "verde osuro": "Verde Oscuro",
            "petroleo": "Petroleo",
            "bordo": "Bordo",
            "violeta": "Violeta",
            "beige": "Beige",
            "marron": "Marron",
            "negro": "Negro",
        }
        return alias_map.get(color_cf, color)

    def save(self, *args, **kwargs):
        self.color = self.normalize_color_value(self.color)
        super().save(*args, **kwargs)

    def __str__(self):
        extra = f" - {self.get_origen_display()}" if self.origen else ""
        return f"{self.codigo} - {self.get_categoria_display()} - {self.color} - {self.talle}{extra}".strip()

    class Meta:
        indexes = [
            models.Index(fields=["categoria", "estado"]),
            models.Index(fields=["origen"]),
            models.Index(fields=["marca"]),
            models.Index(fields=["color"]),
            models.Index(fields=["talle"]),
        ]
