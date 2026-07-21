from decimal import Decimal, ROUND_HALF_UP

from django.db import migrations


def q2(value):
    return Decimal(value or 0).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def normalize_payment_balances(apps, schema_editor):
    Alquiler = apps.get_model("alquileres", "Alquiler")
    for alquiler in Alquiler.objects.all().iterator():
        bruto = q2(alquiler.total_bruto)
        pct = min(max(Decimal(alquiler.descuento_pct or 0), Decimal("0")), Decimal("100"))
        descuento = q2(bruto * pct / Decimal("100"))
        total_final = q2(bruto - descuento)
        sena = min(max(q2(alquiler.sena), Decimal("0")), total_final)
        contractual = q2(total_final - sena)
        pagado = (
            contractual <= 0
            or alquiler.estado_saldo == "PAGADO"
            or alquiler.estado_alquiler in ("ENTREGADO", "CERRADO")
        )
        alquiler.descuento_monto = descuento
        alquiler.total_final = total_final
        alquiler.sena = sena
        alquiler.saldo = Decimal("0.00") if pagado else contractual
        alquiler.estado_saldo = "PAGADO" if pagado else "PENDIENTE"
        if pagado and alquiler.saldo_pagado_en is None:
            alquiler.saldo_pagado_en = alquiler.fecha_entrega or alquiler.fecha_reserva
        alquiler.save(update_fields=[
            "descuento_monto", "total_final", "sena", "saldo", "estado_saldo", "saldo_pagado_en"
        ])


class Migration(migrations.Migration):
    dependencies = [("alquileres", "0005_alter_alquiler_estado_alquiler")]
    operations = [migrations.RunPython(normalize_payment_balances, migrations.RunPython.noop)]
