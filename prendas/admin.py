from django.contrib import admin
from .models import Prenda

@admin.register(Prenda)
class PrendaAdmin(admin.ModelAdmin):
    list_display = ("codigo", "categoria", "marca", "color", "talle", "estado")
    list_filter = ("categoria", "estado", "marca", "color")
    search_fields = ("codigo", "marca", "color", "talle")
