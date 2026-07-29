import re
import unicodedata

from django.db import migrations, models


def color_key(value):
    clean = " ".join((value or "").split()).casefold()
    clean = "".join(
        char for char in unicodedata.normalize("NFKD", clean)
        if not unicodedata.combining(char)
    )
    if clean in {"gris", "gris oscuro", "gris topo"}:
        return "gris topo"
    return clean


def size_key(value):
    alpha = {
        "XXS": 0, "XS": 1, "S": 2, "M": 3, "L": 4, "XL": 5,
        "2XL": 6, "3XL": 7, "4XL": 8, "5XL": 9,
    }
    if value in alpha:
        return (0, alpha[value], [])
    return (
        1,
        0,
        [
            int(part) if part.isdigit() else part.casefold()
            for part in re.split(r"(\d+)", value)
        ],
    )


def backfill_stock_sizes(apps, schema_editor):
    Traje = apps.get_model("catalogo", "Traje")
    Prenda = apps.get_model("prendas", "Prenda")
    for traje in Traje.objects.exclude(color_stock=None).select_related("color_stock"):
        key = color_key(traje.color_stock.nombre)
        stock = Prenda.objects.exclude(estado="DANADA").filter(
            color__isnull=False,
        )
        sacos = {
            talle for color, talle in stock.filter(categoria="SACO")
            .values_list("color", "talle")
            if color_key(color) == key and talle
        }
        pantalones = {
            talle for color, talle in stock.filter(categoria="PANTALON")
            .values_list("color", "talle")
            if color_key(color) == key and talle
        }
        traje.talles_saco_stock = sorted(sacos, key=size_key)
        traje.talles_pantalon_stock = sorted(pantalones, key=size_key)
        traje.save(update_fields=[
            "talles_saco_stock",
            "talles_pantalon_stock",
        ])


class Migration(migrations.Migration):
    dependencies = [
        ("catalogo", "0007_imagentraje"),
    ]

    operations = [
        migrations.AddField(
            model_name="traje",
            name="talles_saco_stock",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="traje",
            name="talles_pantalon_stock",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.RunPython(backfill_stock_sizes, migrations.RunPython.noop),
    ]
