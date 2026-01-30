from decimal import Decimal
from django.db import models
from django.utils import timezone


class Gasto(models.Model):
    fecha = models.DateField(default=timezone.localdate)

    categoria = models.CharField(max_length=40)
    metodo = models.CharField(max_length=30, blank=True, default="")

    descripcion = models.CharField(max_length=140, blank=True, default="")
    monto = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.fecha} - {self.categoria} - ${self.monto}"


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
