from datetime import date
from decimal import Decimal
from urllib.parse import urlencode

from django.contrib import messages
from django.db.models import Sum
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
        start = date(today.year, today.month, 1)

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


def _resumen_cuenta(*, start=None, end=None):
    total_senas_cuenta = Alquiler.objects.aggregate(total=Sum("sena"))["total"] or Decimal("0")
    total_saldos_pagados_cuenta = (
        Alquiler.objects
        .filter(estado_saldo=Alquiler.SAL_PAG)
        .aggregate(total=Sum("saldo"))["total"]
        or Decimal("0")
    )
    total_ingresos_cuenta = total_senas_cuenta + total_saldos_pagados_cuenta
    total_gastos_cuenta = Gasto.objects.aggregate(total=Sum("monto"))["total"] or Decimal("0")
    total_dividido_cuenta = DivisionBienes.objects.aggregate(total=Sum("monto_total"))["total"] or Decimal("0")
    saldo_actual_cuenta = total_ingresos_cuenta - total_gastos_cuenta - total_dividido_cuenta

    if start and end:
        total_senas_periodo = (
            Alquiler.objects
            .filter(fecha_reserva__gte=start, fecha_reserva__lt=end)
            .aggregate(total=Sum("sena"))["total"]
            or Decimal("0")
        )
        total_saldos_pagados_periodo = (
            Alquiler.objects
            .filter(estado_saldo=Alquiler.SAL_PAG, saldo_pagado_en__isnull=False)
            .filter(saldo_pagado_en__gte=start, saldo_pagado_en__lt=end)
            .aggregate(total=Sum("saldo"))["total"]
            or Decimal("0")
        )
        total_gastos_periodo = (
            Gasto.objects
            .filter(fecha__gte=start, fecha__lt=end)
            .aggregate(total=Sum("monto"))["total"]
            or Decimal("0")
        )
        total_dividido_periodo = (
            DivisionBienes.objects
            .filter(fecha__gte=start, fecha__lt=end)
            .aggregate(total=Sum("monto_total"))["total"]
            or Decimal("0")
        )
    else:
        total_senas_periodo = total_senas_cuenta
        total_saldos_pagados_periodo = total_saldos_pagados_cuenta
        total_gastos_periodo = total_gastos_cuenta
        total_dividido_periodo = total_dividido_cuenta

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

    return render(request, "gastos/home.html", {
        "gastos": gastos,
        "divisiones": divisiones,
        "total_gastos_general": Gasto.objects.aggregate(s=Sum("monto"))["s"] or Decimal("0"),
        "total_gastos_mes": gastos.aggregate(s=Sum("monto"))["s"] or Decimal("0"),
        "total_div_general": DivisionBienes.objects.aggregate(s=Sum("monto_total"))["s"] or Decimal("0"),
        "total_div_mes": divisiones.aggregate(s=Sum("monto_total"))["s"] or Decimal("0"),
        "ym_value": month_ctx["ym_value"],
        "month_label": month_ctx["month_label"],
        **_resumen_cuenta(start=month_ctx["start"], end=month_ctx["end"]),
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

    return render(request, "gastos/division.html", {
        "form": form,
        "ym_value": month_ctx["ym_value"],
        "month_label": month_ctx["month_label"],
        **_resumen_cuenta(start=month_ctx["start"], end=month_ctx["end"]),
    })
