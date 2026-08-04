from datetime import date, datetime, time, timedelta
from decimal import Decimal
from urllib.parse import urlencode
import uuid

from django.contrib import messages
from django.conf import settings
from django.db import transaction
from django.db.models import Max, Q, Sum
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from alquileres.models import Alquiler
from alquileres.services import regularizar_saldos_de_cerrados
from cuentas.models import Actividad
from cuentas.services import registrar_actividad

from .access import require_finanzas_access
from .forms import DivisionBienesForm, GASTO_CATEGORIAS, GastoForm, RangoInformeSemanalForm
from .models import DivisionBienes, Gasto, InformeFinancieroSemanal, MovimientoFinanciero
from .services import registrar_movimiento, resumen_movimientos
from .weekly_report import (
    datos_informe_semanal,
    enviar_documento_whatsapp,
    generar_pdf,
    nombre_archivo,
    periodo_semanal,
    whatsapp_configurado,
)

MESES_ES = [
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
]


def _first_day_next_month(day: date) -> date:
    if day.month == 12:
        return date(day.year + 1, 1, 1)
    return date(day.year, day.month + 1, 1)


def _month_label(day: date) -> str:
    return f"{MESES_ES[day.month - 1].capitalize()} {day.year}"


def _latest_financial_month_start():
    candidates = [
        Gasto.objects.aggregate(value=Max("fecha"))["value"],
        DivisionBienes.objects.aggregate(value=Max("fecha"))["value"],
        Alquiler.objects.aggregate(value=Max("fecha_reserva"))["value"],
        (
            Alquiler.objects
            .filter(estado_saldo=Alquiler.SAL_PAG, saldo_pagado_en__isnull=False)
            .aggregate(value=Max("saldo_pagado_en"))["value"]
        ),
    ]
    candidates = [item for item in candidates if item]
    if not candidates:
        return None

    latest = max(candidates)
    return date(latest.year, latest.month, 1)


def _resolve_month(request):
    today = timezone.localdate()
    raw = (request.GET.get("ym") or request.POST.get("ym") or "").strip()

    if raw and len(raw) == 7 and raw[4] == "-":
        try:
            year = int(raw[:4])
            month = int(raw[5:7])
            start = date(year, month, 1)
        except Exception:
            start = date(today.year, today.month, 1)
    else:
        start = _latest_financial_month_start() or date(today.year, today.month, 1)

    end = _first_day_next_month(start)
    return {
        "start": start,
        "end": end,
        "ym_value": f"{start.year:04d}-{start.month:02d}",
        "month_label": _month_label(start),
    }


def _redirect_home_with_month(ym_value):
    base_url = reverse("gastos:home")
    if ym_value:
        return redirect(f"{base_url}?{urlencode({'ym': ym_value})}")
    return redirect(base_url)


def _start_of_month(day: date) -> date:
    return date(day.year, day.month, 1)


def _end_of_week(day: date) -> date:
    return day + timedelta(days=(6 - day.weekday()))


def _decimal_or_zero(value):
    return value or Decimal("0")


def _aggregate_period_totals(model, field_name, *, start=None, end=None, account_end=None):
    total_filter = Q()
    if account_end:
        total_filter &= Q(fecha__lt=account_end)

    period_filter = Q()
    if start and end:
        period_filter = Q(fecha__gte=start, fecha__lt=end)

    totals = model.objects.aggregate(
        total_cuenta=Sum(field_name, filter=total_filter) if account_end else Sum(field_name),
        total_periodo=Sum(field_name, filter=period_filter) if start and end else Sum(field_name),
    )
    return {
        "total_cuenta": _decimal_or_zero(totals["total_cuenta"]),
        "total_periodo": _decimal_or_zero(totals["total_periodo"]),
    }


def _aggregate_alquiler_totals(*, start=None, end=None, account_end=None):
    reserva_cuenta_filter = Q()
    saldo_pagado_filter = Q(estado_saldo=Alquiler.SAL_PAG)

    if account_end:
        reserva_cuenta_filter = Q(fecha_reserva__lt=account_end)
        saldo_pagado_filter &= Q(saldo_pagado_en__isnull=False, saldo_pagado_en__lt=account_end)

    reserva_periodo_filter = Q()
    saldo_periodo_filter = Q(estado_saldo=Alquiler.SAL_PAG)

    if start and end:
        reserva_periodo_filter = Q(fecha_reserva__gte=start, fecha_reserva__lt=end)
        saldo_periodo_filter = Q(
            estado_saldo=Alquiler.SAL_PAG,
            saldo_pagado_en__isnull=False,
            saldo_pagado_en__gte=start,
            saldo_pagado_en__lt=end,
        )

    totals = Alquiler.objects.aggregate(
        total_senas_cuenta=Sum("sena", filter=reserva_cuenta_filter) if account_end else Sum("sena"),
        total_saldos_pagados_cuenta=Sum("saldo", filter=saldo_pagado_filter),
        total_senas_periodo=Sum("sena", filter=reserva_periodo_filter) if start and end else Sum("sena"),
        total_saldos_pagados_periodo=Sum("saldo", filter=saldo_periodo_filter),
    )

    return {
        "total_senas_cuenta": _decimal_or_zero(totals["total_senas_cuenta"]),
        "total_saldos_pagados_cuenta": _decimal_or_zero(totals["total_saldos_pagados_cuenta"]),
        "total_senas_periodo": _decimal_or_zero(totals["total_senas_periodo"]),
        "total_saldos_pagados_periodo": _decimal_or_zero(totals["total_saldos_pagados_periodo"]),
    }


def _resumen_cuenta(*, start=None, end=None, account_end=None):
    # La cuenta y la planilla usan exactamente el mismo libro mayor.
    alquiler_totals = _aggregate_alquiler_totals(start=start, end=end, account_end=account_end)
    gasto_totals = _aggregate_period_totals(Gasto, "monto", start=start, end=end, account_end=account_end)
    division_totals = _aggregate_period_totals(DivisionBienes, "monto_total", start=start, end=end, account_end=account_end)

    cuenta_qs = MovimientoFinanciero.objects.filter(informativo=False)
    if account_end:
        cuenta_qs = cuenta_qs.filter(fecha_hora__date__lt=account_end)
    cuenta = cuenta_qs.aggregate(i=Sum("ingreso"), e=Sum("egreso"))
    total_ingresos_cuenta = cuenta["i"] or Decimal("0")
    total_egresos_cuenta = cuenta["e"] or Decimal("0")
    saldo_actual_cuenta = total_ingresos_cuenta - total_egresos_cuenta
    total_senas_cuenta = alquiler_totals["total_senas_cuenta"]
    total_saldos_pagados_cuenta = total_ingresos_cuenta - total_senas_cuenta
    total_gastos_cuenta = gasto_totals["total_cuenta"]
    total_dividido_cuenta = division_totals["total_cuenta"]

    periodo = resumen_movimientos(
        desde=start,
        hasta=(end - timedelta(days=1)) if start and end else None,
        incluir_divisiones=False,
    )
    total_senas_periodo = alquiler_totals["total_senas_periodo"]
    total_saldos_pagados_periodo = periodo["ingresos"] - total_senas_periodo
    total_gastos_periodo = gasto_totals["total_periodo"]
    total_dividido_periodo = division_totals["total_periodo"]

    total_ingresos_periodo = periodo["ingresos"]
    saldo_neto_periodo = periodo["saldo"]

    return {
        "saldo_actual_cuenta": saldo_actual_cuenta,
        "total_senas_cuenta": total_senas_cuenta,
        "total_saldos_pagados_cuenta": total_saldos_pagados_cuenta,
        "total_ingresos_alquileres_cuenta": total_ingresos_cuenta,
        "total_gastos_cuenta": total_gastos_cuenta,
        "total_dividido_cuenta": total_dividido_cuenta,
        "total_senas_periodo": total_senas_periodo,
        "total_saldos_pagados_periodo": total_saldos_pagados_periodo,
        "total_ingresos_alquileres_periodo": total_ingresos_periodo,
        "total_gastos_periodo": total_gastos_periodo,
        "total_dividido_periodo": total_dividido_periodo,
        "saldo_neto_periodo": saldo_neto_periodo,
        "total_senas": total_senas_periodo,
        "total_saldos_pagados": total_saldos_pagados_periodo,
        "total_ingresos_alquileres": total_ingresos_periodo,
        "total_gastos_registrados": total_gastos_periodo,
        "total_dividido": total_dividido_periodo,
    }


def _saldos_pendientes_resto_semana(hoy: date) -> Decimal:
    desde = hoy - timedelta(days=hoy.weekday())
    hasta = _end_of_week(hoy)
    total = (
        Alquiler.objects
        .filter(
            estado_alquiler=Alquiler.EST_RESERVADO,
            estado_saldo=Alquiler.SAL_PEND,
            saldo__gt=0,
            fecha_entrega__gte=desde,
            fecha_entrega__lte=hasta,
        )
        .aggregate(total=Sum("saldo"))["total"]
    )
    return _decimal_or_zero(total)


def _division_cards(month_ctx, hoy):
    is_current_month = month_ctx["start"] == _start_of_month(hoy)

    if is_current_month:
        account_end = hoy + timedelta(days=1)
        month_to_date_end = min(month_ctx["end"], account_end)
        cuenta_actual = _resumen_cuenta(
            start=month_ctx["start"],
            end=month_ctx["end"],
            account_end=account_end,
        )
        mes_en_curso = _resumen_cuenta(
            start=month_ctx["start"],
            end=month_to_date_end,
            account_end=account_end,
        )
        return {
            "mode_label": "Mes actual",
            "cards": [
                {
                    "label": "TOTAL EN CUENTA (ACTUAL)",
                    "value": cuenta_actual["saldo_actual_cuenta"],
                },
                {
                    "label": "TOTAL EN LO QUE VA DEL MES",
                    "value": mes_en_curso["saldo_neto_periodo"],
                },
                {
                    "label": "PLATA A INGRESAR EN LO QUE RESTA DE LA SEMANA",
                    "value": _saldos_pendientes_resto_semana(hoy),
                },
            ],
        }

    resumen_historico = _resumen_cuenta(start=month_ctx["start"], end=month_ctx["end"])
    total_gastado = resumen_historico["total_gastos_periodo"] + resumen_historico["total_dividido_periodo"]
    return {
        "mode_label": "Mes historico",
        "cards": [
            {
                "label": "TOTAL INGRESADO",
                "value": resumen_historico["total_ingresos_alquileres_periodo"],
            },
            {
                "label": "TOTAL GASTADO",
                "value": total_gastado,
            },
            {
                "label": "BALANCE",
                "value": resumen_historico["total_ingresos_alquileres_periodo"] - total_gastado,
            },
        ],
    }


def home(request):
    access_response = require_finanzas_access(request)
    if access_response:
        return access_response

    regularizar_saldos_de_cerrados(request.user)
    month_ctx = _resolve_month(request)
    gastos = list(
        Gasto.objects
        .filter(fecha__gte=month_ctx["start"], fecha__lt=month_ctx["end"])
        .order_by("-fecha", "-creado_en")
    )
    categorias_presentes = []
    for categoria in GASTO_CATEGORIAS + [gasto.categoria for gasto in gastos]:
        if categoria not in categorias_presentes and any(
            gasto.categoria == categoria for gasto in gastos
        ):
            categorias_presentes.append(categoria)
    gastos_agrupados = [
        {
            "categoria": categoria,
            "gastos": [gasto for gasto in gastos if gasto.categoria == categoria],
            "subtotal": sum(
                (gasto.monto for gasto in gastos if gasto.categoria == categoria),
                Decimal("0"),
            ),
        }
        for categoria in categorias_presentes
    ]
    divisiones = (
        DivisionBienes.objects
        .filter(fecha__gte=month_ctx["start"], fecha__lt=month_ctx["end"])
        .order_by("-fecha", "-creado_en")
    )

    hoy = timezone.localdate()
    mes_actual_inicio = _start_of_month(hoy)
    mes_actual_fin = _first_day_next_month(mes_actual_inicio)
    resumen_mes_actual = resumen_movimientos(
        desde=mes_actual_inicio,
        hasta=mes_actual_fin - timedelta(days=1),
        incluir_divisiones=False,
    )
    saldo_total = resumen_movimientos()["saldo"]
    gastos_mes_actual = (
        Gasto.objects.filter(fecha__gte=mes_actual_inicio, fecha__lt=mes_actual_fin)
        .aggregate(total=Sum("monto"))["total"] or Decimal("0")
    )

    return render(request, "gastos/home.html", {
        "gastos": gastos,
        "gastos_agrupados": gastos_agrupados,
        "divisiones": divisiones,
        "ym_value": month_ctx["ym_value"],
        "month_label": month_ctx["month_label"],
        "finanzas_cards": [
            {"label": "SALDO ACTUAL", "value": saldo_total},
            {"label": "SALDO DEL MES", "value": resumen_mes_actual["saldo"]},
            {"label": "A ENTRAR ESTA SEMANA", "value": _saldos_pendientes_resto_semana(hoy)},
            {"label": "GASTOS DEL MES", "value": gastos_mes_actual},
        ],
    })


def crear(request):
    access_response = require_finanzas_access(request)
    if access_response:
        return access_response

    month_ctx = _resolve_month(request)

    if request.method == "POST":
        form = GastoForm(request.POST)
        if form.is_valid():
            gasto = form.save()
            registrar_movimiento(
                clave=f"gasto:{gasto.pk}", concepto=f"Gasto {gasto.categoria}",
                referencia=f"Gasto #{gasto.pk}", egreso=gasto.monto,
                usuario=request.user, gasto=gasto,
            )
            registrar_actividad(request, "Creó gasto", Actividad.FINANZAS, objeto=gasto, referencia=str(gasto), detalle=f"${gasto.monto}", financiera=True)
            messages.success(request, "Gasto guardado.")
            return _redirect_home_with_month(month_ctx["ym_value"])
        messages.error(request, "Revisa los campos del gasto.")
    else:
        initial_date = timezone.localdate()
        if initial_date < month_ctx["start"] or initial_date >= month_ctx["end"]:
            initial_date = month_ctx["start"]
        form = GastoForm(initial={"fecha": initial_date})

    return render(request, "gastos/crear.html", {
        "form": form,
        "ym_value": month_ctx["ym_value"],
        "month_label": month_ctx["month_label"],
    })


def division_bienes(request):
    access_response = require_finanzas_access(request)
    if access_response:
        return access_response

    regularizar_saldos_de_cerrados()
    month_ctx = _resolve_month(request)

    if request.method == "POST":
        form = DivisionBienesForm(request.POST)
        if form.is_valid():
            division = form.save()
            registrar_movimiento(
                clave=f"division:{division.pk}", concepto="División de bienes",
                referencia=f"División #{division.pk}", egreso=division.monto_total,
                usuario=request.user, division=division,
            )
            registrar_actividad(request, "Creó división de bienes", Actividad.FINANZAS, objeto=division, referencia=str(division), financiera=True)
            messages.success(request, "Division de bienes guardada.")
            return _redirect_home_with_month(month_ctx["ym_value"])
        messages.error(request, "Revisa los campos de la division.")
    else:
        initial_date = timezone.localdate()
        if initial_date < month_ctx["start"] or initial_date >= month_ctx["end"]:
            initial_date = month_ctx["start"]
        form = DivisionBienesForm(initial={"fecha": initial_date})

    division_summary = _division_cards(month_ctx, timezone.localdate())

    return render(request, "gastos/division.html", {
        "form": form,
        "ym_value": month_ctx["ym_value"],
        "month_label": month_ctx["month_label"],
        "division_cards": division_summary["cards"],
        "division_mode_label": division_summary["mode_label"],
        **_resumen_cuenta(start=month_ctx["start"], end=month_ctx["end"]),
    })


def movimientos(request):
    access_response = require_finanzas_access(request)
    if access_response:
        return access_response
    qs = MovimientoFinanciero.objects.select_related("usuario", "usuario__perfil", "alquiler", "gasto", "division")
    desde, hasta = request.GET.get("desde", ""), request.GET.get("hasta", "")
    tipo, usuario, q = request.GET.get("tipo", ""), request.GET.get("usuario", ""), (request.GET.get("q") or "").strip()
    if desde: qs = qs.filter(fecha_hora__date__gte=desde)
    if hasta: qs = qs.filter(fecha_hora__date__lte=hasta)
    if tipo == "ingresos": qs = qs.filter(ingreso__gt=0)
    if tipo == "egresos": qs = qs.filter(egreso__gt=0)
    if usuario.isdigit(): qs = qs.filter(usuario_id=int(usuario))
    if q: qs = qs.filter(Q(concepto__icontains=q) | Q(referencia__icontains=q))
    rows = list(qs.order_by("fecha_hora", "id"))
    # El acumulado pertenece al libro mayor completo. Los filtros deciden qué
    # filas se muestran, pero nunca deben reiniciar ni alterar el saldo real.
    saldo_por_movimiento = {}
    saldo = Decimal("0")
    for row in MovimientoFinanciero.objects.order_by(
        "fecha_hora", "id"
    ).only("id", "ingreso", "egreso", "informativo"):
        if not row.informativo:
            saldo += row.ingreso - row.egreso
        saldo_por_movimiento[row.pk] = saldo
    for row in rows:
        row.saldo_acumulado = saldo_por_movimiento.get(row.pk, saldo)
    rows.reverse()
    from django.contrib.auth.models import User
    return render(request, "gastos/movimientos.html", {
        "movimientos": rows, "saldo_actual": resumen_movimientos()["saldo"],
        "usuarios": User.objects.filter(movimientofinanciero__isnull=False).distinct(),
        "filtros": request.GET,
    })


def _rango_informe(form):
    desde_fecha = form.cleaned_data.get("desde")
    hasta_fecha = form.cleaned_data.get("hasta")
    if not desde_fecha and not hasta_fecha:
        return periodo_semanal()
    zona = timezone.get_current_timezone()
    return (
        timezone.make_aware(datetime.combine(desde_fecha, time.min), zona),
        timezone.make_aware(datetime.combine(hasta_fecha, time.max), zona),
    )


def descargar_informe_semanal(request):
    access_response = require_finanzas_access(request)
    if access_response:
        return access_response
    regularizar_saldos_de_cerrados(request.user)
    rango_form = RangoInformeSemanalForm(request.GET)
    if not rango_form.is_valid():
        messages.error(request, "Revisá el rango de fechas antes de descargar.")
        return redirect("gastos:enviar_informe_semanal")
    desde, hasta = _rango_informe(rango_form)
    datos = datos_informe_semanal(desde, hasta)
    response = HttpResponse(generar_pdf(datos), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{nombre_archivo(datos)}"'
    return response


def enviar_informe_semanal(request):
    access_response = require_finanzas_access(request)
    if access_response:
        return access_response
    regularizar_saldos_de_cerrados(request.user)
    rango_form = RangoInformeSemanalForm(request.POST if request.method == "POST" else None)
    desde, hasta = periodo_semanal()
    resultado_actual = None

    if request.method == "POST":
        if not rango_form.is_valid():
            desde, hasta = periodo_semanal()
        else:
            desde, hasta = _rango_informe(rango_form)
        if not rango_form.is_valid():
            return render(request, "gastos/informe_semanal.html", {
                "desde": desde, "hasta": hasta,
                "rango_form": rango_form,
                "clave_solicitud": str(uuid.uuid4()),
                "whatsapp_configurado": whatsapp_configurado(),
                "resultado_actual": None,
                "informes_recientes": InformeFinancieroSemanal.objects.select_related("usuario", "usuario__perfil")[:10],
            })
        try:
            clave = uuid.UUID(request.POST.get("clave_solicitud", ""))
        except (ValueError, TypeError, AttributeError):
            messages.error(request, "La confirmación venció. Volvé a intentar.")
            return redirect("gastos:enviar_informe_semanal")

        destinatarios = settings.WEEKLY_REPORT_RECIPIENTS
        if not whatsapp_configurado():
            messages.warning(
                request,
                "WhatsApp Business todavía no está configurado para envíos automáticos. "
                "Podés descargar el PDF.",
            )
        else:
            with transaction.atomic():
                informe, _ = InformeFinancieroSemanal.objects.get_or_create(
                    clave_solicitud=clave,
                    defaults={
                        "periodo_desde": desde,
                        "periodo_hasta": hasta,
                        "usuario": request.user,
                        "destinatarios": destinatarios,
                    },
                )
                informe = InformeFinancieroSemanal.objects.select_for_update().get(pk=informe.pk)
                datos = datos_informe_semanal(informe.periodo_desde, informe.periodo_hasta)
                pdf = generar_pdf(datos)
                archivo = nombre_archivo(datos)
                caption = (
                    "Informe financiero semanal de Abito\n"
                    f"Período: {timezone.localtime(informe.periodo_desde):%d/%m/%Y} – "
                    f"{timezone.localtime(informe.periodo_hasta):%d/%m/%Y}"
                )
                resultados = dict(informe.resultados)
                for nombre, telefono in informe.destinatarios.items():
                    if resultados.get(nombre, {}).get("estado") == "enviado":
                        continue
                    resultados[nombre] = enviar_documento_whatsapp(
                        pdf, archivo, telefono, caption
                    )
                informe.resultados = resultados
                informe.save(update_fields=["resultados", "actualizado_en"])
                resultado_actual = informe

            enviados = [
                nombre for nombre, dato in resultado_actual.resultados.items()
                if dato.get("estado") == "enviado"
            ]
            fallidos = [
                nombre for nombre, dato in resultado_actual.resultados.items()
                if dato.get("estado") != "enviado"
            ]
            if enviados:
                registrar_actividad(
                    request,
                    "Informe financiero semanal enviado",
                    Actividad.FINANZAS,
                    objeto=resultado_actual,
                    referencia=f"{desde:%d/%m/%Y} - {hasta:%d/%m/%Y}",
                    detalle=f"Enviados: {', '.join(enviados)}"
                    + (f". Fallaron: {', '.join(fallidos)}" if fallidos else ""),
                    financiera=True,
                )
            if fallidos:
                messages.error(
                    request,
                    f"No se pudo enviar a: {', '.join(fallidos)}. "
                    "Los destinatarios que ya lo recibieron no se reenviarán al reintentar.",
                )
            else:
                messages.success(request, "Informe enviado correctamente a Bauti y Tadeo.")

    return render(request, "gastos/informe_semanal.html", {
        "desde": desde,
        "hasta": hasta,
        "rango_form": rango_form,
        "clave_solicitud": str(uuid.uuid4()),
        "whatsapp_configurado": whatsapp_configurado(),
        "resultado_actual": resultado_actual,
        "informes_recientes": InformeFinancieroSemanal.objects.select_related(
            "usuario", "usuario__perfil"
        )[:10],
    })
