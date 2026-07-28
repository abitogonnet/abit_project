from decimal import Decimal, ROUND_HALF_UP
from django.conf import settings
from django.db import models
from django.utils import timezone

from prendas.models import Prenda


def _q2(x: Decimal) -> Decimal:
    return (x or Decimal("0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class Cliente(models.Model):
    nombre = models.CharField(max_length=80)
    dni = models.CharField(max_length=12, unique=True, db_index=True)
    telefono = models.CharField(max_length=30)
    saldo_a_favor = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.nombre} - DNI {self.dni}"


class Alquiler(models.Model):
    MAX_PERSONAS = 6

    # Estados del alquiler
    EST_RESERVADO = "RESERVADO"
    EST_ENTREGADO = "ENTREGADO"
    EST_CERRADO = "CERRADO"
    EST_CANCELADO = "CANCELADO"
    ESTADOS_ALQUILER = [
        (EST_RESERVADO, "Reservado"),
        (EST_ENTREGADO, "Entregado"),
        (EST_CERRADO, "Cerrado"),
        (EST_CANCELADO, "Cancelado"),
    ]
    ESTADOS_ALQUILER_ACTIVOS = [EST_RESERVADO, EST_ENTREGADO]
    ESTADOS_ALQUILER_FINALES = [EST_CERRADO, EST_CANCELADO]

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
    cliente = models.ForeignKey(Cliente, null=True, blank=True, on_delete=models.PROTECT, related_name="alquileres")

    # Fechas
    fecha_visita = models.DateField()
    fecha_reserva = models.DateField()
    fecha_entrega = models.DateField()
    fecha_devolucion = models.DateField()

    # Personas del alquiler
    persona1_nombre = models.CharField(max_length=80)
    persona2_nombre = models.CharField(max_length=80, blank=True, default="")
    persona3_nombre = models.CharField(max_length=80, blank=True, default="")
    persona4_nombre = models.CharField(max_length=80, blank=True, default="")
    persona5_nombre = models.CharField(max_length=80, blank=True, default="")
    persona6_nombre = models.CharField(max_length=80, blank=True, default="")

    # Pagos
    total_bruto = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    descuento_pct = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    descuento_monto = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_final = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    sena = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    saldo = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    saldo_a_favor_aplicado = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    credito_cancelacion_generado = models.BooleanField(default=False)

    # ✅ Métodos (seña al crear; saldo al marcar PAGADO)
    metodo_sena = models.CharField(max_length=20, choices=METODOS_PAGO, blank=True, default="")
    metodo_saldo = models.CharField(max_length=20, choices=METODOS_PAGO, blank=True, default="")
    saldo_pagado_en = models.DateField(null=True, blank=True)  # fecha real en que se marcó como pagado

    estado_saldo = models.CharField(max_length=12, choices=ESTADOS_SALDO, default=SAL_PEND)
    estado_alquiler = models.CharField(max_length=12, choices=ESTADOS_ALQUILER, default=EST_RESERVADO)

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)
    cerrado_en = models.DateTimeField(null=True, blank=True)
    cerrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="alquileres_cerrados",
    )

    @classmethod
    def calcular_importes(cls, total_bruto, descuento_pct, sena):
        """Única fórmula para total final y saldo contractual."""
        bruto = _q2(Decimal(total_bruto or 0))
        pct = Decimal(descuento_pct or 0)
        if pct < 0:
            pct = Decimal("0")
        if pct > 100:
            pct = Decimal("100")

        desc = _q2(bruto * (pct / Decimal("100")))
        final = _q2(bruto - desc)

        sena = _q2(Decimal(sena or 0))
        if sena < 0:
            sena = Decimal("0")
        if sena > final:
            sena = final

        return bruto, pct, desc, final, sena, _q2(final - sena)

    def calcular_totales(self):
        bruto, pct, desc, final, sena, saldo_contractual = self.calcular_importes(
            self.total_bruto, self.descuento_pct, self.sena
        )

        self.total_bruto = bruto
        self.descuento_pct = pct
        self.descuento_monto = desc
        self.total_final = final
        self.sena = sena
        saldo_contractual = max(
            Decimal("0.00"),
            _q2(saldo_contractual - Decimal(self.saldo_a_favor_aplicado or 0)),
        )
        completamente_abonado = (
            saldo_contractual <= 0
            or self.estado_saldo == self.SAL_PAG
            or self.estado_alquiler in (self.EST_ENTREGADO, self.EST_CERRADO)
        )
        if completamente_abonado:
            self.saldo = Decimal("0.00")
            self.estado_saldo = self.SAL_PAG
            if self.saldo_pagado_en is None:
                self.saldo_pagado_en = self.fecha_reserva or timezone.localdate()
        else:
            self.saldo = saldo_contractual
            self.estado_saldo = self.SAL_PEND

    @property
    def esta_completamente_abonado(self):
        return self.estado_saldo == self.SAL_PAG and self.saldo <= 0

    @property
    def saldo_pendiente_actual(self):
        return Decimal("0.00") if self.esta_completamente_abonado else _q2(Decimal(self.saldo or 0))

    @property
    def saldo_contractual(self):
        return max(
            Decimal("0.00"),
            _q2(
                Decimal(self.total_final or 0)
                - Decimal(self.sena or 0)
                - Decimal(self.saldo_a_favor_aplicado or 0)
            ),
        )

    def marcar_completamente_abonado(self, fecha=None):
        if self.esta_completamente_abonado:
            return False
        self.estado_saldo = self.SAL_PAG
        self.saldo = Decimal("0.00")
        if self.saldo_pagado_en is None:
            self.saldo_pagado_en = fecha or timezone.localdate()
        return True

    def marcar_saldo_pendiente(self):
        contractual = self.saldo_contractual
        if contractual <= 0:
            return False
        self.estado_saldo = self.SAL_PEND
        self.saldo = contractual
        self.metodo_saldo = ""
        self.saldo_pagado_en = None
        return True
    def save(self, *args, **kwargs):
        self.calcular_totales()
        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = set(kwargs["update_fields"]) | {
                "total_bruto", "descuento_pct", "descuento_monto", "total_final",
                "sena", "saldo", "estado_saldo", "saldo_pagado_en",
            }
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Alquiler #{self.id} - {self.cliente_nombre}"

    def persona_nombre(self, persona_num: int) -> str:
        return getattr(self, f"persona{persona_num}_nombre", "") or ""

    def personas_cargadas(self):
        return [
            (persona_num, self.persona_nombre(persona_num).strip())
            for persona_num in range(1, self.MAX_PERSONAS + 1)
        ]

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
    persona_num = models.PositiveSmallIntegerField(default=1)  # 1 a 6
    prenda = models.ForeignKey(Prenda, on_delete=models.PROTECT)

    ruedo_valor = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    ruedo_tipo = models.CharField(max_length=10, choices=RUEDO_TIPOS, blank=True, default="")
    notas = models.CharField(max_length=200, blank=True, default="")
    ruedo_listo = models.BooleanField(default=False)
    ruedo_listo_en = models.DateTimeField(null=True, blank=True)
    ruedo_listo_por = models.ForeignKey(
        "auth.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="ruedos_marcados_listos",
    )

    def __str__(self):
        return f"{self.alquiler_id} - P{self.persona_num} - {self.prenda.codigo}"
