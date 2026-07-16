from datetime import date, timedelta
from decimal import Decimal
from urllib.parse import urlencode

from django.contrib import messages
from django.db.models import Max, Q, Sum
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from alquileres.models import Alquiler

from .forms import DivisionBienesForm, GastoForm
from .models import DivisionBienes, Gasto


GASTOS_PASSWORD = "Abito2024"
GASTOS_SESSION_KEY = "gastos_access_ok"
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


def _require_gastos_access(request):
    if request.session.get(GASTOS_SESSION_KEY):
        return None

    error_msg = ""
    if request.method == "POST" and request.POST.get("access_action") == "unlock":
        password = (request.POST.get("access_password") or "").strip()
        if password == GASTOS_PASSWORD:
            request.session[GASTOS_SESSION_KEY] = True
            messages.success(request, "Acceso a gastos habilitado.")
            return redirect(request.path)
        error_msg = "Contrasena incorrecta."

    return render(request, "gastos/lock.html", {
        "error_msg": error_msg,
    })


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
    alquiler_totals = _aggregate_alquiler_totals(start=start, end=end, account_end=account_end)
    gasto_totals = _aggregate_period_totals(Gasto, "monto", start=start, end=end, account_end=account_end)
    division_totals = _aggregate_period_totals(DivisionBienes, "monto_total", start=start, end=end, account_end=account_end)

    total_senas_cuenta = alquiler_totals["total_senas_cuenta"]
    total_saldos_pagados_cuenta = alquiler_totals["total_saldos_pagados_cuenta"]
    total_ingresos_cuenta = total_senas_cuenta + total_saldos_pagados_cuenta
    total_gastos_cuenta = gasto_totals["total_cuenta"]
    total_dividido_cuenta = division_totals["total_cuenta"]
    saldo_actual_cuenta = total_ingresos_cuenta - total_gastos_cuenta - total_dividido_cuenta

    total_senas_periodo = alquiler_totals["total_senas_periodo"]
    total_saldos_pagados_periodo = alquiler_totals["total_saldos_pagados_periodo"]
    total_gastos_periodo = gasto_totals["total_periodo"]
    total_dividido_periodo = division_totals["total_periodo"]

    total_ingresos_periodo = total_senas_periodo + total_saldos_pagados_periodo
    saldo_neto_periodo = total_ingresos_periodo - total_gastos_periodo - total_dividido_periodo

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
    hasta = _end_of_week(hoy)
    total = (
        Alquiler.objects
        .exclude(estado_alquiler=Alquiler.EST_CERRADO)
        .filter(
            estado_saldo=Alquiler.SAL_PEND,
            saldo__gt=0,
            fecha_entrega__gte=hoy,
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
    access_response = _require_gastos_access(request)
    if access_response:
        return access_response

    month_ctx = _resolve_month(request)
    gastos = (
        Gasto.objects
        .filter(fecha__gte=month_ctx["start"], fecha__lt=month_ctx["end"])
        .order_by("-fecha", "-creado_en")
    )
    divisiones = (
        DivisionBienes.objects
        .filter(fecha__gte=month_ctx["start"], fecha__lt=month_ctx["end"])
        .order_by("-fecha", "-creado_en")
    )

    resumen_cuenta = _resumen_cuenta(start=month_ctx["start"], end=month_ctx["end"])

    return render(request, "gastos/home.html", {
        "gastos": gastos,
        "divisiones": divisiones,
        "total_gastos_general": resumen_cuenta["total_gastos_cuenta"],
        "total_gastos_mes": resumen_cuenta["total_gastos_periodo"],
        "total_div_general": resumen_cuenta["total_dividido_cuenta"],
        "total_div_mes": resumen_cuenta["total_dividido_periodo"],
        "ym_value": month_ctx["ym_value"],
        "month_label": month_ctx["month_label"],
        **resumen_cuenta,
    })


def crear(request):
    access_response = _require_gastos_access(request)
    if access_response:
        return access_response

    month_ctx = _resolve_month(request)

    if request.method == "POST":
        form = GastoForm(request.POST)
        if form.is_valid():
            form.save()
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
    access_response = _require_gastos_access(request)
    if access_response:
        return access_response

    month_ctx = _resolve_month(request)

    if request.method == "POST":
        form = DivisionBienesForm(request.POST)
        if form.is_valid():
            form.save()
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
