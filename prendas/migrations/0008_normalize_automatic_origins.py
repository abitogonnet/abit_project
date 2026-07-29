from django.db import migrations


ORIGEN_POR_CATEGORIA = {
    "CAMISA": "IMPORTADO",
    "ZAPATOS": "NACIONAL",
    "CINTURON": "NACIONAL",
    "CORBATA": "NACIONAL",
}


def normalizar_origenes(apps, schema_editor):
    Prenda = apps.get_model("prendas", "Prenda")
    for categoria, origen in ORIGEN_POR_CATEGORIA.items():
        Prenda.objects.filter(categoria=categoria).exclude(origen=origen).update(
            origen=origen,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("prendas", "0007_alter_prenda_estado"),
    ]

    operations = [
        migrations.RunPython(normalizar_origenes, migrations.RunPython.noop),
    ]
