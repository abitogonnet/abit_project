from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from prendas.models import Prenda

from .models import Traje
from .stock_sizes import actualizar_talles_traje, actualizar_trajes_por_nombres_color


@receiver(post_save, sender=Traje)
def refresh_stock_sizes_after_suit_save(sender, instance, **kwargs):
    actualizar_talles_traje(instance)


@receiver(pre_save, sender=Prenda)
def remember_previous_stock_color(sender, instance, **kwargs):
    if not instance.pk:
        instance._catalog_previous_color = ""
        return
    instance._catalog_previous_color = (
        sender.objects.filter(pk=instance.pk)
        .values_list("color", flat=True)
        .first()
        or ""
    )


@receiver(post_save, sender=Prenda)
def refresh_catalog_sizes_after_stock_save(sender, instance, **kwargs):
    actualizar_trajes_por_nombres_color(
        getattr(instance, "_catalog_previous_color", ""),
        instance.color,
    )


@receiver(post_delete, sender=Prenda)
def refresh_catalog_sizes_after_stock_delete(sender, instance, **kwargs):
    actualizar_trajes_por_nombres_color(instance.color)
