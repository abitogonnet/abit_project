from django.contrib import admin
from .models import Alquiler, AlquilerItem, Cliente

admin.site.register(Cliente)

class AlquilerItemInline(admin.TabularInline):
    model = AlquilerItem
    extra = 0

@admin.register(Alquiler)
class AlquilerAdmin(admin.ModelAdmin):
    list_display = ("id", "cliente_nombre", "fecha_entrega", "fecha_devolucion", "estado_alquiler", "estado_saldo", "total_final")
    list_filter = ("estado_alquiler", "estado_saldo")
    search_fields = ("cliente_nombre", "cliente_telefono")
    inlines = [AlquilerItemInline]
