from django.db import migrations, models


def initialize_password_tasks(apps, schema_editor):
    PerfilUsuario = apps.get_model("cuentas", "PerfilUsuario")
    PerfilUsuario.objects.update(debe_cambiar_password=True)
    PerfilUsuario.objects.filter(user__username__iexact="bautista").update(debe_cambiar_password=False)


class Migration(migrations.Migration):
    dependencies = [("cuentas", "0001_initial")]
    operations = [
        migrations.AddField(
            model_name="perfilusuario",
            name="debe_cambiar_password",
            field=models.BooleanField(default=True),
        ),
        migrations.RunPython(initialize_password_tasks, migrations.RunPython.noop),
    ]
