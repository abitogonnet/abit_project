from decimal import Decimal
from django.db.models import Sum
from django.utils import timezone
from .models import MovimientoFinanciero


def registrar_movimiento(*, clave, concepto, referencia, ingreso=0, egreso=0,
                         usuario=None, alquiler=None, gasto=None, division=None,
                         cliente=None, informativo=False, fecha_hora=None):
    defaults = {
        "fecha_hora": fecha_hora or timezone.now(), "concepto": concepto,
        "referencia": referencia, "ingreso": Decimal(ingreso or 0),
        "egreso": Decimal(egreso or 0),
        "usuario": usuario if getattr(usuario, "is_authenticated", False) else None,
        "alquiler": alquiler, "gasto": gasto, "division": division,
        "cliente": cliente, "informativo": informativo,
    }
    return MovimientoFinanciero.objects.get_or_create(clave=clave, defaults=defaults)


def registrar_sena(alquiler, usuario=None):
    if alquiler.sena <= 0:
        return None, False
    return registrar_movimiento(
        clave=f"alquiler:{alquiler.pk}:sena", concepto="Seña",
        referencia=f"Alquiler #{alquiler.pk}", ingreso=alquiler.sena,
        usuario=usuario, alquiler=alquiler, cliente=alquiler.cliente,
        fecha_hora=alquiler.creado_en,
    )


def registrar_saldo(alquiler, usuario=None):
    importe = alquiler.saldo_contractual
    if importe <= 0:
        return None, False
    return registrar_movimiento(
        clave=f"alquiler:{alquiler.pk}:saldo", concepto="Saldo abonado",
        referencia=f"Alquiler #{alquiler.pk}", ingreso=importe,
        usuario=usuario, alquiler=alquiler, cliente=alquiler.cliente,
    )


def sincronizar_movimientos_alquiler(alquiler, usuario=None):
    sena, _ = registrar_sena(alquiler, usuario)
    if sena:
        sena.ingreso = alquiler.sena
        sena.cliente = alquiler.cliente
        sena.save(update_fields=["ingreso", "cliente"])
    saldo = MovimientoFinanciero.objects.filter(clave=f"alquiler:{alquiler.pk}:saldo").first()
    if saldo:
        saldo.ingreso = alquiler.saldo_contractual
        saldo.cliente = alquiler.cliente
        saldo.save(update_fields=["ingreso", "cliente"])


def resumen_movimientos(*, desde=None, hasta=None, incluir_divisiones=True):
    qs = MovimientoFinanciero.objects.filter(informativo=False)
    if not incluir_divisiones:
        qs = qs.filter(division__isnull=True)
    if desde:
        qs = qs.filter(fecha_hora__date__gte=desde)
    if hasta:
        qs = qs.filter(fecha_hora__date__lte=hasta)
    data = qs.aggregate(ingresos=Sum("ingreso"), egresos=Sum("egreso"))
    ingresos = data["ingresos"] or Decimal("0")
    egresos = data["egresos"] or Decimal("0")
    return {"ingresos": ingresos, "egresos": egresos, "saldo": ingresos - egresos}
