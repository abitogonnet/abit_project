import unicodedata

from django.db import migrations


RESTRICTED_CATEGORIES = {"SACO", "PANTALON", "CAMISA"}


def simplify_color(value):
    color = " ".join((value or "").split()).casefold()
    if not color:
        return ""
    return "".join(
        char
        for char in unicodedata.normalize("NFKD", color)
        if not unicodedata.combining(char)
    )


def normalize_restricted_color(value):
    color = " ".join((value or "").split())
    if not color:
        return ""

    alias_map = {
        "azul oscuro": "Azul Oscuro",
        "azul osc": "Azul Oscuro",
        "azul ocs": "Azul Oscuro",
        "osc": "Azul Oscuro",
        "azul francia": "Azul Francia",
        "blanco": "Blanca",
        "blanca": "Blanca",
        "gris": "Gris Topo",
        "gris perla": "Gris Perla",
        "gris oscuro": "Gris Topo",
        "gris topo": "Gris Topo",
        "celeste": "Celeste",
        "rosa": "Rosa",
        "verde pistacho": "Verde Pistacho",
        "pistacho": "Verde Pistacho",
        "verde oscuro": "Verde Oscuro",
        "verde osuro": "Verde Oscuro",
        "petroleo": "Petroleo",
        "bordo": "Bordo",
        "violeta": "Violeta",
        "beige": "Beige",
        "marron": "Marron",
        "negro": "Negro",
    }
    return alias_map.get(simplify_color(color), color)


def normalize_existing_restricted_colors(apps, schema_editor):
    Prenda = apps.get_model("prendas", "Prenda")
    pendientes = []

    for prenda in Prenda.objects.filter(categoria__in=RESTRICTED_CATEGORIES).only("id", "categoria", "color"):
        normalized_color = normalize_restricted_color(prenda.color)
        if normalized_color != (prenda.color or ""):
            prenda.color = normalized_color
            pendientes.append(prenda)

    if pendientes:
        Prenda.objects.bulk_update(pendientes, ["color"])


class Migration(migrations.Migration):

    dependencies = [
        ("prendas", "0003_prenda_prendas_pre_categor_0307d1_idx_and_more"),
    ]

    operations = [
        migrations.RunPython(normalize_existing_restricted_colors, migrations.RunPython.noop),
    ]
