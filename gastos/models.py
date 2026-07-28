from decimal import Decimal
from django.db import models
from django.conf import settings
from django.utils import timezone


class Gasto(models.Model):
    fecha = models.DateField(default=timezone.localdate)

    categoria = models.CharField(max_length=40)
    metodo = models.CharField(max_length=30, blank=True, default="")

    descripcion = models.CharField(max_length=140, blank=True, default="")
    notas = models.CharField(max_length=200, blank=True, default="")
    monto = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.fecha} - {self.categoria} - ${self.monto}"


class MovimientoFinanciero(models.Model):
    clave = models.CharField(max_length=100, unique=True)
    fecha_hora = models.DateTimeField(default=timezone.now, db_index=True)
    concepto = models.CharField(max_length=100)
    referencia = models.CharField(max_length=160, blank=True)
    ingreso = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    egreso = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    informativo = models.BooleanField(default=False, db_index=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    alquiler = models.ForeignKey("alquileres.Alquiler", null=True, blank=True, on_delete=models.SET_NULL)
    gasto = models.ForeignKey(Gasto, null=True, blank=True, on_delete=models.SET_NULL)
    division = models.ForeignKey("DivisionBienes", null=True, blank=True, on_delete=models.SET_NULL)
    cliente = models.ForeignKey("alquileres.Cliente", null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["-fecha_hora", "-id"]


class InformeFinancieroSemanal(models.Model):
    clave_solicitud = models.UUIDField(unique=True, editable=False)
    periodo_desde = models.DateTimeField()
    periodo_hasta = models.DateTimeField()
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    destinatarios = models.JSONField(default=dict)
    resultados = models.JSONField(default=dict)
    creado_en = models.DateTimeField(auto_now_add=True, db_index=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-creado_en", "-id"]

    def __str__(self):
        return f"Informe semanal {self.periodo_desde:%d/%m/%Y}"


class DivisionBienes(models.Model):
    """
    Cuando se saca plata de la cuenta y se divide entre Tade y Bauti.
    """
    fecha = models.DateField(default=timezone.localdate)

    monto_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    para_tade = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    para_bauti = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    notas = models.CharField(max_length=140, blank=True, default="")

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.fecha} - División bienes - Total ${self.monto_total}"
