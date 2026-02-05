from django.contrib import admin
from .models import Gasto

@admin.register(Gasto)
class GastoAdmin(admin.ModelAdmin):
    list_display = ("fecha", "categoria", "metodo", "descripcion", "monto")
    list_filter = ("categoria", "metodo", "fecha")
    search_fields = ("descripcion",)
