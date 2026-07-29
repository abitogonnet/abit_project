from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("catalogo", "0006_configuracionvisitas_traje_color_stock"),
    ]

    operations = [
        migrations.CreateModel(
            name="ImagenTraje",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("imagen", models.ImageField(upload_to="trajes/galeria/")),
                ("orden", models.PositiveIntegerField(default=0)),
                ("creada", models.DateTimeField(auto_now_add=True)),
                (
                    "traje",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="imagenes_galeria",
                        to="catalogo.traje",
                    ),
                ),
            ],
            options={"ordering": ["orden", "id"]},
        ),
    ]
