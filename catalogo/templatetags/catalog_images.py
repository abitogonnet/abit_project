import logging
from decimal import Decimal, InvalidOperation

from django import template
from django.templatetags.static import static

logger = logging.getLogger(__name__)
register = template.Library()

PLACEHOLDER_PATH = "img/catalog-placeholder.svg"


@register.filter
def catalog_image_url(image_field):
    if not image_field or not getattr(image_field, "name", ""):
        return static(PLACEHOLDER_PATH)
    try:
        if not image_field.storage.exists(image_field.name):
            logger.warning(
                "Imagen de catálogo faltante en storage: %s",
                image_field.name,
            )
            return static(PLACEHOLDER_PATH)
        return image_field.url
    except Exception:
        logger.exception(
            "No se pudo resolver imagen de catálogo: %s",
            getattr(image_field, "name", ""),
        )
        return static(PLACEHOLDER_PATH)


@register.filter
def ars_currency(value):
    try:
        amount = Decimal(value or 0)
    except (InvalidOperation, TypeError, ValueError):
        return "$0"
    rounded = f"{amount:,.0f}".replace(",", ".")
    return f"${rounded}"
