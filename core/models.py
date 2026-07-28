from django.core.exceptions import ValidationError
from django.db import models


class ConfiguracionSitio(models.Model):
    whatsapp_url = models.URLField(
        default="https://wa.me/message/IXNVRCQIC6YFF1",
        help_text="Enlace completo de WhatsApp que se muestra en la web publica.",
    )
    instagram_url = models.URLField(
        blank=True,
        default="https://www.instagram.com/abito.gonnet/",
        help_text="Enlace completo del Instagram oficial.",
    )
    direccion_post_reserva = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Direccion exacta que se muestra despues de confirmar la visita.",
    )
    mensaje_confirmacion = models.TextField(
        default=(
            "Tu visita quedo confirmada. Te esperamos en el horario elegido y "
            "si necesitas reprogramar, escribinos por WhatsApp."
        ),
        help_text="Mensaje principal que se muestra al confirmar una visita.",
    )
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Configuracion del sitio"
        verbose_name_plural = "Configuracion del sitio"

    def clean(self):
        if not self.pk and ConfiguracionSitio.objects.exists():
            raise ValidationError("Solo puede existir una configuracion del sitio.")

    def __str__(self):
        return "Configuracion del sitio"

    @classmethod
    def load(cls):
        instance = cls.objects.order_by("pk").first()
        if instance:
            return instance

        return cls.objects.create()
