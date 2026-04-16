from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("prendas", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="prenda",
            name="origen",
            field=models.CharField(blank=True, choices=[("NACIONAL", "Nacional"), ("IMPORTADO", "Importado")], default="", max_length=20),
        ),
    ]
