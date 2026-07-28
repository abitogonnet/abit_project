from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("gastos", "0007_informefinancierosemanal"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="movimientofinanciero",
            index=models.Index(
                fields=["informativo", "fecha_hora"],
                name="gastos_mov_info_fecha_idx",
            ),
        ),
    ]
