from django.db import models

class Visita(models.Model):
    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        CONFIRMADA = "confirmada", "Confirmada"
        CANCELADA = "cancelada", "Cancelada"

    nombre = models.CharField(max_length=120, blank=True)
    telefono = models.CharField(max_length=40, help_text="Ej: +54 9 221 ...")

    fecha_evento = models.DateField()

    inicio = models.DateTimeField(help_text="Fecha y hora de la visita")
    duracion_min = models.PositiveSmallIntegerField(
        choices=[(30, "30 min"), (60, "60 min")],
        default=30
    )
    personas = models.PositiveSmallIntegerField(default=1)

    estado = models.CharField(
        max_length=20,
        choices=Estado.choices,
        default=Estado.PENDIENTE
    )

    # Para enlazar con Google Calendar más adelante
    calendar_event_id = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-inicio"]

    def __str__(self):
        return f"Visita {self.telefono} - {self.inicio} ({self.estado})"
