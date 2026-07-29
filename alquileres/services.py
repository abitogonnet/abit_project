from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from cuentas.models import Actividad
from prendas.models import Prenda

from .models import Alquiler, AlquilerItem


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


@transaction.atomic
def cerrar_alquiler(alquiler_id, usuario=None):
    """Única operación persistente para cerrar un alquiler desde cualquier vista."""
    from gastos.services import registrar_saldo

    alquiler = (
        Alquiler.objects.select_for_update()
        .get(pk=alquiler_id)
    )
    if alquiler.estado_alquiler == Alquiler.EST_CERRADO:
        return alquiler, False

    prenda_ids = list(
        alquiler.items.select_for_update().values_list("prenda_id", flat=True)
    )
    alquiler.estado_alquiler = Alquiler.EST_CERRADO
    alquiler.marcar_completamente_abonado()
    alquiler.cerrado_en = timezone.now()
    alquiler.cerrado_por = (
        usuario if getattr(usuario, "is_authenticated", False) else None
    )
    alquiler.save(update_fields=[
        "estado_alquiler", "estado_saldo", "saldo", "saldo_pagado_en",
        "cerrado_en", "cerrado_por", "actualizado_en",
    ])

    # La clave única del movimiento garantiza que el saldo restante se cobre
    # una sola vez, incluso si el cierre se vuelve a solicitar.
    registrar_saldo(alquiler, usuario)

    for prenda_id in set(prenda_ids):
        tiene_otro_alquiler_activo = AlquilerItem.objects.filter(
            prenda_id=prenda_id,
            alquiler__estado_alquiler__in=Alquiler.ESTADOS_ALQUILER_ACTIVOS,
        ).exists()
        Prenda.objects.filter(pk=prenda_id).update(
            estado=Prenda.E_RES if tiene_otro_alquiler_activo else Prenda.E_DISP
        )

    nombre = (
        getattr(getattr(usuario, "perfil", None), "nombre", "")
        or getattr(usuario, "get_full_name", lambda: "")()
        or getattr(usuario, "username", "")
    )
    Actividad.objects.create(
        usuario=usuario if getattr(usuario, "is_authenticated", False) else None,
        usuario_nombre=nombre,
        accion="Alquiler cerrado",
        categoria=Actividad.DEVOLUCION,
        tipo_objeto="Alquiler",
        objeto_id=str(alquiler.pk),
        referencia=f"Alquiler #{alquiler.pk}",
    )
    return alquiler, True
