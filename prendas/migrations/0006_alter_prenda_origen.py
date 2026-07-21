from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("prendas", "0005_color_catalog")]
    operations = [
        migrations.AlterField(
            model_name="prenda",
            name="origen",
            field=models.CharField(
                blank=True,
                choices=[("NACIONAL", "Nacional"), ("IMPORTADO", "Importada")],
                default="",
                max_length=20,
            ),
        ),
    ]
