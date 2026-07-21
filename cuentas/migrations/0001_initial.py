from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(name="PerfilUsuario", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("nombre", models.CharField(max_length=150)),
            ("rol", models.CharField(choices=[("PROPIETARIO", "Propietario"), ("ADMINISTRADOR", "Administrador"), ("EMPLEADO", "Empleado")], default="EMPLEADO", max_length=20)),
            ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="perfil", to=settings.AUTH_USER_MODEL)),
        ]),
        migrations.CreateModel(name="Actividad", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("usuario_nombre", models.CharField(blank=True, max_length=150)),
            ("accion", models.CharField(max_length=120)),
            ("categoria", models.CharField(choices=[("ALQUILER", "Alquileres"), ("ENTREGA", "Entrega"), ("PAGO", "Abonado restante"), ("DEVOLUCION", "Devolución/cierre"), ("STOCK", "Stock"), ("FINANZAS", "Finanzas"), ("USUARIOS", "Usuarios")], db_index=True, max_length=20)),
            ("creado_en", models.DateTimeField(auto_now_add=True, db_index=True)),
            ("tipo_objeto", models.CharField(blank=True, max_length=40)),
            ("objeto_id", models.CharField(blank=True, max_length=64)),
            ("referencia", models.CharField(blank=True, max_length=160)),
            ("detalle", models.CharField(blank=True, max_length=255)),
            ("es_financiera", models.BooleanField(db_index=True, default=False)),
            ("usuario", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="actividades", to=settings.AUTH_USER_MODEL)),
        ], options={"ordering": ["-creado_en", "-id"]}),
    ]
