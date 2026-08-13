from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("visitas", "0004_preferenciaambovisita_producto_id_and_more")]

    operations = [
        migrations.AddField(
            model_name="bloqueoagenda",
            name="modulos",
            field=models.PositiveSmallIntegerField(
                choices=[(1, "1 módulo"), (2, "2 módulos")], default=2,
            ),
        ),
    ]
