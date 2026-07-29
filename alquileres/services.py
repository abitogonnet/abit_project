from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from cuentas.models import Actividad
from prendas.models import Prenda

from .models import Alquiler, AlquilerItem, Cliente


class TransicionAlquilerInvalida(ValueError):
    pass


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


@transaction.atomic
def cancelar_alquiler(alquiler_id, usuario=None):
    """Cancela un reservado y acredita su seña exactamente una vez."""
    from gastos.services import registrar_movimiento

    alquiler = (
        Alquiler.objects.select_for_update()
        .select_related("cliente")
        .get(pk=alquiler_id)
    )
    if alquiler.estado_alquiler == Alquiler.EST_CANCELADO:
        return alquiler, False
    if alquiler.estado_alquiler != Alquiler.EST_RESERVADO:
        raise TransicionAlquilerInvalida(
            "Solo se puede cancelar un alquiler reservado."
        )

    cliente = None
    if alquiler.cliente_id:
        cliente = Cliente.objects.select_for_update().get(pk=alquiler.cliente_id)

    prenda_ids = list(
        alquiler.items.select_for_update().values_list("prenda_id", flat=True)
    )
    prendas = {
        prenda.pk: prenda
        for prenda in Prenda.objects.select_for_update().filter(
            pk__in=set(prenda_ids)
        )
    }

    if (
        cliente is not None
        and alquiler.sena > 0
        and not alquiler.credito_cancelacion_generado
    ):
        cliente.saldo_a_favor += alquiler.sena
        cliente.save(update_fields=["saldo_a_favor", "actualizado_en"])
        alquiler.credito_cancelacion_generado = True
        registrar_movimiento(
            clave=f"alquiler:{alquiler.pk}:credito-cancelacion",
            concepto="Saldo transferido a favor del cliente",
            referencia=f"Alquiler #{alquiler.pk}",
            cliente=cliente,
            alquiler=alquiler,
            usuario=usuario,
            informativo=True,
        )

    alquiler.estado_alquiler = Alquiler.EST_CANCELADO
    alquiler.cancelado_en = timezone.now()
    alquiler.cancelado_por = (
        usuario if getattr(usuario, "is_authenticated", False) else None
    )
    alquiler.save(update_fields=[
        "estado_alquiler",
        "credito_cancelacion_generado",
        "cancelado_en",
        "cancelado_por",
        "actualizado_en",
    ])

    for prenda_id, prenda in prendas.items():
        if prenda.estado in {Prenda.E_DAN, Prenda.E_LAV}:
            continue
        otros = AlquilerItem.objects.filter(
            prenda_id=prenda_id,
            alquiler__estado_alquiler__in=Alquiler.ESTADOS_ALQUILER_ACTIVOS,
        )
        if otros.filter(
            alquiler__estado_alquiler=Alquiler.EST_ENTREGADO
        ).exists():
            nuevo_estado = Prenda.E_ENT
        elif otros.exists():
            nuevo_estado = Prenda.E_RES
        else:
            nuevo_estado = Prenda.E_DISP
        if prenda.estado != nuevo_estado:
            prenda.estado = nuevo_estado
            prenda.save(update_fields=["estado"])

    nombre = (
        getattr(getattr(usuario, "perfil", None), "nombre", "")
        or getattr(usuario, "get_full_name", lambda: "")()
        or getattr(usuario, "username", "")
    )
    Actividad.objects.create(
        usuario=usuario if getattr(usuario, "is_authenticated", False) else None,
        usuario_nombre=nombre,
        accion="Canceló alquiler",
        categoria=Actividad.ALQUILER,
        tipo_objeto="Alquiler",
        objeto_id=str(alquiler.pk),
        referencia=f"Alquiler #{alquiler.pk}",
    )
    return alquiler, True
