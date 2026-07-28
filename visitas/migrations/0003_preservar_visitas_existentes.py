from django.db import migrations


def forwards(apps, schema_editor):
    Visita = apps.get_model("visitas", "Visita")
    estados = {
        "pendiente": "CONFIRMADA",
        "confirmada": "CONFIRMADA",
        "cancelada": "CANCELADA",
    }
    for visita in Visita.objects.filter(fecha_visita__isnull=True).iterator():
        if visita.inicio:
            visita.fecha_visita = visita.inicio.date()
            visita.hora_visita = visita.inicio.time().replace(second=0, microsecond=0)
        visita.cantidad_personas = visita.personas or 1
        visita.estado = estados.get(visita.estado, visita.estado)
        visita.origen = "MANUAL"
        visita.save(update_fields=[
            "fecha_visita", "hora_visita", "cantidad_personas", "estado", "origen",
        ])


class Migration(migrations.Migration):
    dependencies = [("visitas", "0002_agendadia_bloqueoagenda_preferenciaambovisita_and_more")]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
