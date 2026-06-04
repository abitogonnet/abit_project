from decimal import Decimal, ROUND_HALF_UP
from django.db import models
from django.utils import timezone

from prendas.models import Prenda


def _q2(x: Decimal) -> Decimal:
    return (x or Decimal("0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class Alquiler(models.Model):
    # Estados del alquiler
    EST_RESERVADO = "RESERVADO"
    EST_ENTREGADO = "ENTREGADO"
    EST_CERRADO = "CERRADO"
    ESTADOS_ALQUILER = [
        (EST_RESERVADO, "Reservado"),
        (EST_ENTREGADO, "Entregado"),
        (EST_CERRADO, "Cerrado"),
    ]

    # Estado del saldo
    SAL_PEND = "PENDIENTE"
    SAL_PAG = "PAGADO"
    ESTADOS_SALDO = [
        (SAL_PEND, "Pendiente"),
        (SAL_PAG, "Pagado"),
    ]

    # ✅ Métodos de pago
    MP_EFEC = "EFECTIVO"
    MP_TRANS = "TRANSFERENCIA"
    MP_TARJ = "TARJETA"
    METODOS_PAGO = [
        (MP_EFEC, "Efectivo"),
        (MP_TRANS, "Transferencia"),
        (MP_TARJ, "Tarjeta"),
    ]

    # Datos cliente
    cliente_nombre = models.CharField(max_length=80)
    cliente_telefono = models.CharField(max_length=30)

    # Fechas
    fecha_visita = models.DateField()
    fecha_reserva = models.DateField()
    fecha_entrega = models.DateField()
    fecha_devolucion = models.DateField()

    # Persona 1/2
    persona1_nombre = models.CharField(max_length=80)
    persona2_nombre = models.CharField(max_length=80, blank=True, default="")

    # Pagos
    total_bruto = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    descuento_pct = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    descuento_monto = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_final = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    sena = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    saldo = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # ✅ Métodos (seña al crear; saldo al marcar PAGADO)
    metodo_sena = models.CharField(max_length=20, choices=METODOS_PAGO, blank=True, default="")
    metodo_saldo = models.CharField(max_length=20, choices=METODOS_PAGO, blank=True, default="")
    saldo_pagado_en = models.DateField(null=True, blank=True)  # fecha real en que se marcó como pagado

    estado_saldo = models.CharField(max_length=12, choices=ESTADOS_SALDO, default=SAL_PEND)
    estado_alquiler = models.CharField(max_length=12, choices=ESTADOS_ALQUILER, default=EST_RESERVADO)

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    def calcular_totales(self):
        bruto = _q2(Decimal(self.total_bruto or 0))
        pct = Decimal(self.descuento_pct or 0)
        if pct < 0:
            pct = Decimal("0")
        if pct > 100:
            pct = Decimal("100")

        desc = _q2(bruto * (pct / Decimal("100")))
        final = _q2(bruto - desc)

        sena = _q2(Decimal(self.sena or 0))
        if sena < 0:
            sena = Decimal("0")
        if sena > final:
            sena = final

        saldo = _q2(final - sena)

        self.descuento_monto = desc
        self.total_final = final
        self.sena = sena
        self.saldo = saldo

    def save(self, *args, **kwargs):
        self.calcular_totales()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Alquiler #{self.id} - {self.cliente_nombre}"

    class Meta:
        indexes = [
            models.Index(fields=["fecha_reserva"]),
            models.Index(fields=["fecha_entrega"]),
            models.Index(fields=["fecha_devolucion"]),
            models.Index(fields=["estado_alquiler", "fecha_entrega"]),
            models.Index(fields=["estado_alquiler", "fecha_devolucion"]),
            models.Index(fields=["estado_saldo", "saldo_pagado_en"]),
        ]


class AlquilerItem(models.Model):
    RUEDO_CM = "CM"
    RUEDO_BOTON = "BOTON"
    RUEDO_TIPOS = [
        (RUEDO_CM, "cm"),
        (RUEDO_BOTON, "botón"),
    ]

    alquiler = models.ForeignKey(Alquiler, on_delete=models.CASCADE, related_name="items")
    persona_num = models.PositiveSmallIntegerField(default=1)  # 1 o 2
    prenda = models.ForeignKey(Prenda, on_delete=models.PROTECT)

    ruedo_valor = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    ruedo_tipo = models.CharField(max_length=10, choices=RUEDO_TIPOS, blank=True, default="")
    notas = models.CharField(max_length=200, blank=True, default="")

    def __str__(self):
        return f"{self.alquiler_id} - P{self.persona_num} - {self.prenda.codigo}"
