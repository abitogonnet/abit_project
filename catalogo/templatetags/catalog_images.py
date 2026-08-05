from decimal import Decimal, InvalidOperation

from django import template
from django.templatetags.static import static

register = template.Library()

PLACEHOLDER_PATH = "img/catalog-placeholder.svg"


@register.filter
def catalog_image_url(image_field):
    if not image_field or not getattr(image_field, "name", ""):
        return static(PLACEHOLDER_PATH)
    try:
        return image_field.url
    except Exception:
        return static(PLACEHOLDER_PATH)


@register.filter
def ars_currency(value):
    try:
        amount = Decimal(value or 0)
    except (InvalidOperation, TypeError, ValueError):
        return "$0"
    rounded = f"{amount:,.0f}".replace(",", ".")
    return f"${rounded}"
