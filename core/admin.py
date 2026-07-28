from django.contrib import admin
from django.http import HttpResponseRedirect
from django.urls import reverse

from .models import ConfiguracionSitio


@admin.register(ConfiguracionSitio)
class ConfiguracionSitioAdmin(admin.ModelAdmin):
    readonly_fields = ("actualizado",)
    save_on_top = True
    show_full_result_count = False
    show_facets = admin.ShowFacets.NEVER
    fieldsets = (
        (
            "Canales publicos",
            {
                "fields": ("whatsapp_url", "instagram_url"),
            },
        ),
        (
            "Reserva y confirmacion",
            {
                "fields": ("direccion_post_reserva", "mensaje_confirmacion"),
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

        config = ConfiguracionSitio.load()
        return HttpResponseRedirect(
            reverse("admin:core_configuracionsitio_change", args=[config.pk])
        )

    def add_view(self, request, form_url="", extra_context=None):
        if not self.has_change_permission(request):
            return super().add_view(request, form_url, extra_context)

        config = ConfiguracionSitio.load()
        return HttpResponseRedirect(
            reverse("admin:core_configuracionsitio_change", args=[config.pk])
        )


admin.site.site_header = "ABITO Administracion"
admin.site.site_title = "ABITO Admin"
admin.site.index_title = "Gestion interna"
