from django.contrib import admin
from django.http import HttpResponseRedirect
from django.urls import reverse

from .models import (
    Camisa,
    Chaleco,
    Cinturon,
    Combo,
    ConfiguracionVisitas,
    Corbata,
    TalleColorCamisa,
    TalleColorChaleco,
    TalleColorTraje,
    TalleColorZapato,
    Traje,
    Zapato,
)


class BaseCatalogAdmin(admin.ModelAdmin):
    save_on_top = True
    show_full_result_count = False
    show_facets = admin.ShowFacets.NEVER


class TalleColorTrajeInline(admin.TabularInline):
    model = TalleColorTraje
    extra = 1


class TalleColorChalecoInline(admin.TabularInline):
    model = TalleColorChaleco
    extra = 1


class TalleColorCamisaInline(admin.TabularInline):
    model = TalleColorCamisa
    extra = 1


class TalleColorZapatoInline(admin.TabularInline):
    model = TalleColorZapato
    extra = 1


@admin.register(Traje)
class TrajeAdmin(BaseCatalogAdmin):
    list_display = ("id", "linea", "tela", "precio", "activo", "creado")
    list_filter = ("linea", "activo")
    search_fields = ("tela", "descripcion")
    inlines = [TalleColorTrajeInline]
    fieldsets = (
        (
            "Datos principales",
            {
                "fields": ("linea", "tela", "descripcion", "precio", "activo"),
            },
        ),
        (
            "Fotos",
            {
                "fields": ("foto_modelo", "foto_colgado"),
            },
        ),
    )


@admin.register(Chaleco)
class ChalecoAdmin(BaseCatalogAdmin):
    list_display = ("id", "precio", "activo", "creado")
    list_filter = ("activo",)
    search_fields = ("descripcion",)
    inlines = [TalleColorChalecoInline]
    fields = ("descripcion", "precio", "activo", "foto_modelo", "foto_colgado")


@admin.register(Cinturon)
class CinturonAdmin(BaseCatalogAdmin):
    list_display = ("id", "precio", "activo", "creado")
    list_filter = ("activo",)
    search_fields = ("descripcion",)
    fields = ("descripcion", "precio", "activo", "foto_1", "foto_2")


@admin.register(Corbata)
class CorbataAdmin(BaseCatalogAdmin):
    list_display = ("id", "precio", "activo", "creado")
    list_filter = ("activo",)
    search_fields = ("descripcion",)
    fields = ("descripcion", "precio", "activo", "foto_1", "foto_2")


@admin.register(Camisa)
class CamisaAdmin(BaseCatalogAdmin):
    list_display = ("id", "precio", "activo", "creado")
    list_filter = ("activo",)
    search_fields = ("descripcion",)
    inlines = [TalleColorCamisaInline]
    fields = ("descripcion", "precio", "activo", "foto_modelo", "foto_colgado")


@admin.register(Zapato)
class ZapatoAdmin(BaseCatalogAdmin):
    list_display = ("id", "precio", "activo", "creado")
    list_filter = ("activo",)
    search_fields = ("descripcion",)
    inlines = [TalleColorZapatoInline]
    fields = ("descripcion", "precio", "activo", "foto_modelo", "foto_colgado")


@admin.register(Combo)
class ComboAdmin(BaseCatalogAdmin):
    list_display = (
        "id",
        "orden",
        "nombre",
        "precio_importado",
        "precio_nacional",
        "precio_ninos",
        "precio_unico",
        "activo",
    )
    list_filter = ("activo",)
    search_fields = ("nombre", "descripcion")
    ordering = ("orden", "id")


@admin.register(ConfiguracionVisitas)
class ConfiguracionVisitasAdmin(BaseCatalogAdmin):
    readonly_fields = ("actualizado",)
    fieldsets = (
        (
            "Visitas confirmadas",
            {
                "fields": ("direccion_post_reserva", "mensaje_confirmacion"),
                "description": (
                    "Estos datos se cargan solo desde el admin interno y se muestran "
                    "recien despues de confirmar una visita."
                ),
            },
        ),
        (
            "Control",
            {
                "fields": ("actualizado",),
            },
        ),
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        if not self.has_view_or_change_permission(request):
            return super().changelist_view(request, extra_context)

        config = ConfiguracionVisitas.load()
        return HttpResponseRedirect(
            reverse("admin:catalogo_configuracionvisitas_change", args=[config.pk])
        )

    def add_view(self, request, form_url="", extra_context=None):
        if not self.has_change_permission(request):
            return super().add_view(request, form_url, extra_context)

        config = ConfiguracionVisitas.load()
        return HttpResponseRedirect(
            reverse("admin:catalogo_configuracionvisitas_change", args=[config.pk])
        )
