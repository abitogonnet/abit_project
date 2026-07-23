from datetime import datetime, time
from decimal import Decimal

from django.db import migrations
from django.utils import timezone


def _aware(day):
    value = datetime.combine(day, time(12, 0))
    return timezone.make_aware(value) if timezone.is_naive(value) else value


def forwards(apps, schema_editor):
    Alquiler = apps.get_model("alquileres", "Alquiler")
    Movimiento = apps.get_model("gastos", "MovimientoFinanciero")
    Gasto = apps.get_model("gastos", "Gasto")
    Division = apps.get_model("gastos", "DivisionBienes")

    for alquiler in Alquiler.objects.all().iterator():
        if alquiler.sena > 0:
            Movimiento.objects.get_or_create(
                clave=f"alquiler:{alquiler.pk}:sena",
                defaults={"fecha_hora": alquiler.creado_en, "concepto": "Seña",
                          "referencia": f"Alquiler #{alquiler.pk}", "ingreso": alquiler.sena,
                          "alquiler_id": alquiler.pk, "cliente_id": alquiler.cliente_id},
            )
        contractual = max(
            Decimal("0"),
            alquiler.total_final - alquiler.sena - alquiler.saldo_a_favor_aplicado,
        )
        if contractual > 0 and alquiler.estado_alquiler != "CANCELADO" and (
            alquiler.estado_saldo == "PAGADO" or alquiler.estado_alquiler in ("ENTREGADO", "CERRADO")
        ):
            paid_day = alquiler.saldo_pagado_en or alquiler.fecha_entrega
            Movimiento.objects.get_or_create(
                clave=f"alquiler:{alquiler.pk}:saldo",
                defaults={"fecha_hora": _aware(paid_day), "concepto": "Saldo abonado",
                          "referencia": f"Alquiler #{alquiler.pk}", "ingreso": contractual,
                          "alquiler_id": alquiler.pk, "cliente_id": alquiler.cliente_id},
            )
    for gasto in Gasto.objects.all().iterator():
        Movimiento.objects.get_or_create(
            clave=f"gasto:{gasto.pk}", defaults={"fecha_hora": _aware(gasto.fecha),
            "concepto": f"Gasto {gasto.categoria}", "referencia": f"Gasto #{gasto.pk}",
            "egreso": gasto.monto, "gasto_id": gasto.pk},
        )
    for division in Division.objects.all().iterator():
        Movimiento.objects.get_or_create(
            clave=f"division:{division.pk}", defaults={"fecha_hora": _aware(division.fecha),
            "concepto": "División de bienes", "referencia": f"División #{division.pk}",
            "egreso": division.monto_total, "division_id": division.pk},
        )


class Migration(migrations.Migration):
    dependencies = [
        ("alquileres", "0008_alquiler_credito_cancelacion_generado_and_more"),
        ("gastos", "0005_movimientofinanciero"),
    ]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
