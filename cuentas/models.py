from django.conf import settings
from django.db import models


class PerfilUsuario(models.Model):
    PROPIETARIO = "PROPIETARIO"
    ADMINISTRADOR = "ADMINISTRADOR"
    EMPLEADO = "EMPLEADO"
    ROLES = [
        (PROPIETARIO, "Propietario"),
        (ADMINISTRADOR, "Administrador"),
        (EMPLEADO, "Empleado"),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="perfil")
    nombre = models.CharField(max_length=150)
    rol = models.CharField(max_length=20, choices=ROLES, default=EMPLEADO)
    debe_cambiar_password = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.nombre} ({self.get_rol_display()})"


class Actividad(models.Model):
    ALQUILER = "ALQUILER"
    ENTREGA = "ENTREGA"
    PAGO = "PAGO"
    DEVOLUCION = "DEVOLUCION"
    STOCK = "STOCK"
    FINANZAS = "FINANZAS"
    USUARIOS = "USUARIOS"
    CATEGORIAS = [
        (ALQUILER, "Alquileres"), (ENTREGA, "Entrega"),
        (PAGO, "Abonado restante"), (DEVOLUCION, "Devolución/cierre"),
        (STOCK, "Stock"), (FINANZAS, "Finanzas"), (USUARIOS, "Usuarios"),
    ]
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="actividades")
    usuario_nombre = models.CharField(max_length=150, blank=True)
    accion = models.CharField(max_length=120)
    categoria = models.CharField(max_length=20, choices=CATEGORIAS, db_index=True)
    creado_en = models.DateTimeField(auto_now_add=True, db_index=True)
    tipo_objeto = models.CharField(max_length=40, blank=True)
    objeto_id = models.CharField(max_length=64, blank=True)
    referencia = models.CharField(max_length=160, blank=True)
    detalle = models.CharField(max_length=255, blank=True)
    es_financiera = models.BooleanField(default=False, db_index=True)

    class Meta:
        ordering = ["-creado_en", "-id"]
