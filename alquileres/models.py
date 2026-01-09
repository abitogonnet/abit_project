from django.db import models

class Traje(models.Model):
    codigo = models.CharField(max_length=6, unique=True)
    prenda = models.CharField(max_length=50)
    marca = models.CharField(max_length=50)
    talle = models.CharField(max_length=20)
    color = models.CharField(max_length=30)
    estado = models.CharField(max_length=20, default='Disponible')

    def __str__(self):
        return f"{self.codigo} - {self.prenda}"

class Alquiler(models.Model):
    nombre_cliente = models.CharField(max_length=100)
    celular_cliente = models.CharField(max_length=20)
    prendas = models.ManyToManyField(Traje, related_name='alquileres')
    ruedo_pantalon = models.CharField(max_length=50, blank=True, null=True)
    ruedo_saco = models.CharField(max_length=50, blank=True, null=True)
    fecha_visita = models.DateField()
    fecha_retiro = models.DateField()
    fecha_devolucion = models.DateField()
    fecha_evento = models.DateField(blank=True, null=True)
    total_a_abonar = models.DecimalField(max_digits=10, decimal_places=2)
    seña = models.DecimalField(max_digits=10, decimal_places=2)
    metodo_pago_sena = models.CharField(max_length=20)
    saldo_restante = models.DecimalField(max_digits=10, decimal_places=2)
    metodo_pago_saldo = models.CharField(max_length=20)
    notas_adicionales = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Alquiler {self.id} - {self.nombre_cliente}"

class Gasto(models.Model):
    fecha = models.DateField()
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    detalle = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Gasto {self.id} - {self.monto} en {self.fecha}"