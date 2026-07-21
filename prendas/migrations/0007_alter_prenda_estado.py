from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("prendas", "0006_alter_prenda_origen")]
    operations = [
        migrations.AlterField(
            model_name="prenda",
            name="estado",
            field=models.CharField(
                choices=[
                    ("DISPONIBLE", "Disponible"), ("RESERVADO", "Reservado"),
                    ("ENTREGADO", "Entregado"), ("LAVANDERIA", "Lavandería"),
                    ("DANADA", "Dañada"),
                ], default="DISPONIBLE", max_length=20,
            ),
        ),
    ]
