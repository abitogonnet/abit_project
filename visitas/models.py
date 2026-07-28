from django.core.exceptions import ValidationError
from django.db import models

from catalogo.models import Traje
from alquileres.models import Alquiler, Cliente


class Visita(models.Model):
    ESTADO_CONFIRMADA = "CONFIRMADA"
    ESTADO_CANCELADA = "CANCELADA"
    ESTADO_REALIZADA = "REALIZADA"
    ESTADO_NO_ASISTIO = "NO_ASISTIO"

    ESTADOS = [
        (ESTADO_CONFIRMADA, "Confirmada"),
        (ESTADO_CANCELADA, "Cancelada"),
        (ESTADO_REALIZADA, "Realizada"),
        (ESTADO_NO_ASISTIO, "No asistio"),
    ]

    ORIGEN_WEB = "WEB"
    ORIGEN_MANUAL = "MANUAL"

    ORIGENES = [
        (ORIGEN_WEB, "Web"),
        (ORIGEN_MANUAL, "Manual"),
    ]

    nombre = models.CharField(max_length=120, blank=True)
    dni = models.CharField(max_length=20, blank=True, default="")
    telefono = models.CharField(max_length=30)
    cliente = models.ForeignKey(
        Cliente, null=True, blank=True, on_delete=models.PROTECT,
        related_name="visitas",
    )
    alquiler = models.OneToOneField(
        Alquiler, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="visita_origen",
    )
    cantidad_personas = models.PositiveIntegerField(default=1)
    fecha_evento = models.DateField()
    fecha_visita = models.DateField(null=True, blank=True)
    hora_visita = models.TimeField(null=True, blank=True)
    vio_prendas_catalogo = models.BooleanField(
        null=True,
        blank=True,
        verbose_name="Vio prendas en el catalogo",
    )
    estado = models.CharField(
        max_length=20,
        choices=ESTADOS,
        default=ESTADO_CONFIRMADA,
    )
    origen = models.CharField(
        max_length=20,
        choices=ORIGENES,
        default=ORIGEN_WEB,
    )
    observaciones_internas = models.TextField(blank=True, default="")
    inicio = models.DateTimeField(null=True, blank=True)
    duracion_min = models.PositiveSmallIntegerField(
        choices=[(30, "30 min"), (60, "60 min")], default=30
    )
    personas = models.PositiveSmallIntegerField(default=1)
    calendar_event_id = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-fecha_visita", "-hora_visita", "-created_at"]
        indexes = [
            models.Index(
                fields=["fecha_visita", "hora_visita"],
                name="visitas_fecha_hora_idx",
            ),
            models.Index(
                fields=["fecha_visita", "estado"],
                name="visitas_fecha_estado_idx",
            ),
        ]

    def __str__(self):
        return f"{self.nombre} - {self.fecha_visita} {self.hora_visita}"


class AgendaDia(models.Model):
    """Fila de sincronización: serializa reservas concurrentes de una fecha."""
    fecha = models.DateField(unique=True)

    def __str__(self):
        return str(self.fecha)


class PreferenciaAmboVisita(models.Model):
    visita = models.ForeignKey(
        Visita,
        on_delete=models.CASCADE,
        related_name="preferencias_ambos",
    )
    traje = models.ForeignKey(
        Traje,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="preferencias_visita",
    )
    orden = models.PositiveSmallIntegerField()
    linea = models.CharField(max_length=20, blank=True, default="")
    tela = models.CharField(max_length=100, blank=True, default="")
    color = models.CharField(max_length=50)
    talle_saco = models.CharField(max_length=50)
    talle_pantalon = models.CharField(max_length=50)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["orden", "id"]
        verbose_name = "Preferencia de ambo"
        verbose_name_plural = "Preferencias de ambos"

    def __str__(self):
        return (
            f"Preferencia {self.orden}: {self.linea} - {self.tela} - "
            f"{self.color} ({self.talle_saco}/{self.talle_pantalon})"
        )


class BloqueoAgenda(models.Model):
    fecha = models.DateField()
    hora_inicio = models.TimeField(blank=True, null=True)
    hora_fin = models.TimeField(blank=True, null=True)
    motivo = models.CharField(max_length=200, blank=True, default="")
    activo = models.BooleanField(default=True)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["fecha", "hora_inicio", "id"]
        verbose_name = "Bloqueo de agenda"
        verbose_name_plural = "Bloqueos de agenda"

    def clean(self):
        if bool(self.hora_inicio) != bool(self.hora_fin):
            raise ValidationError(
                "Si indicas un horario de inicio, tambien debes indicar el de fin."
            )

        if self.hora_inicio and self.hora_fin and self.hora_inicio >= self.hora_fin:
            raise ValidationError(
                "La hora de fin debe ser posterior a la hora de inicio."
            )

    def __str__(self):
        if self.hora_inicio and self.hora_fin:
            return f"{self.fecha} {self.hora_inicio}-{self.hora_fin}"
        return f"{self.fecha} bloqueada"
