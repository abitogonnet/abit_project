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


def regularizar_saldos_de_cerrados(usuario=None):
    # Import local para evitar dependencia circular al cargar las apps.
    from gastos.services import registrar_saldo

    alquileres = (
        Alquiler.objects
        .filter(
            Q(estado_alquiler__in=[Alquiler.EST_ENTREGADO, Alquiler.EST_CERRADO])
            | Q(estado_saldo=Alquiler.SAL_PAG)
        )
        .exclude(estado_alquiler=Alquiler.EST_CANCELADO)
    )

    actualizados = 0
    for alquiler in alquileres:
        changed = False

        if alquiler.marcar_completamente_abonado(fecha_referencia_pago_cierre(alquiler)):
            changed = True

        if alquiler.saldo_pagado_en is None:
            alquiler.saldo_pagado_en = fecha_referencia_pago_cierre(alquiler)
            changed = True

        if changed:
            alquiler.save(update_fields=["saldo", "estado_saldo", "saldo_pagado_en"])
            actualizados += 1
        # Un alquiler entregado/cerrado o ya marcado como pagado representa
        # dinero efectivamente cobrado. La clave única evita contabilizarlo
        # más de una vez aunque esta regularización se ejecute repetidamente.
        if (
            alquiler.estado_alquiler in [Alquiler.EST_ENTREGADO, Alquiler.EST_CERRADO]
            or alquiler.estado_saldo == Alquiler.SAL_PAG
        ):
            registrar_saldo(alquiler, usuario)

    return actualizados
