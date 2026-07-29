from django.db import migrations


def normalizar_origen_chalecos(apps, schema_editor):
    Prenda = apps.get_model("prendas", "Prenda")
    Prenda.objects.filter(categoria="CHALECO").exclude(origen="NACIONAL").update(
        origen="NACIONAL",
    )


class Migration(migrations.Migration):
    dependencies = [
        ("prendas", "0008_normalize_automatic_origins"),
    ]

    operations = [
        migrations.RunPython(
            normalizar_origen_chalecos,
            migrations.RunPython.noop,
        ),
    ]
