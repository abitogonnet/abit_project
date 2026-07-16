from django.db.models import Q
from django.utils import timezone

from .models import Alquiler


def fecha_referencia_pago_cierre(alquiler: Alquiler):
    return (
        alquiler.saldo_pagado_en
        or alquiler.fecha_devolucion
        or alquiler.fecha_entrega
        or alquiler.fecha_reserva
        or timezone.localdate()
    )


def regularizar_saldos_de_cerrados():
    alquileres = (
        Alquiler.objects
        .filter(estado_alquiler=Alquiler.EST_CERRADO, saldo__gt=0)
        .filter(
            Q(estado_saldo=Alquiler.SAL_PEND)
            | Q(saldo_pagado_en__isnull=True)
        )
    )

    actualizados = 0
    for alquiler in alquileres:
        changed = False

        if alquiler.estado_saldo != Alquiler.SAL_PAG:
            alquiler.estado_saldo = Alquiler.SAL_PAG
            changed = True

        if alquiler.saldo_pagado_en is None:
            alquiler.saldo_pagado_en = fecha_referencia_pago_cierre(alquiler)
            changed = True

        if changed:
            alquiler.save(update_fields=["estado_saldo", "saldo_pagado_en"])
            actualizados += 1

    return actualizados
