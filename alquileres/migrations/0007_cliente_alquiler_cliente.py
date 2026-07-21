from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("alquileres", "0006_normalize_payment_balances")]
    operations = [
        migrations.CreateModel(
            name="Cliente",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nombre", models.CharField(max_length=80)),
                ("dni", models.CharField(db_index=True, max_length=12, unique=True)),
                ("telefono", models.CharField(max_length=30)),
                ("creado_en", models.DateTimeField(auto_now_add=True)),
                ("actualizado_en", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.AddField(
            model_name="alquiler",
            name="cliente",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="alquileres", to="alquileres.cliente"),
        ),
    ]
