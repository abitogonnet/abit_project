from decimal import Decimal

from django.contrib import messages
from django.db.models import Sum
from django.shortcuts import redirect, render
from django.utils import timezone

from alquileres.models import Alquiler

from .forms import DivisionBienesForm, GastoForm
from .models import DivisionBienes, Gasto


GASTOS_PASSWORD = "Abito2024"
GASTOS_SESSION_KEY = "gastos_access_ok"


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


def _resumen_cuenta():
    total_senas = Alquiler.objects.aggregate(total=Sum("sena"))["total"] or Decimal("0")
    total_saldos_pagados = (
        Alquiler.objects
        .filter(estado_saldo=Alquiler.SAL_PAG)
        .aggregate(total=Sum("saldo"))["total"]
        or Decimal("0")
    )
    total_ingresos_alquileres = total_senas + total_saldos_pagados
    total_gastos = Gasto.objects.aggregate(total=Sum("monto"))["total"] or Decimal("0")
    total_dividido = DivisionBienes.objects.aggregate(total=Sum("monto_total"))["total"] or Decimal("0")
    saldo_actual_cuenta = total_ingresos_alquileres - total_gastos - total_dividido

    return {
        "total_senas": total_senas,
        "total_saldos_pagados": total_saldos_pagados,
        "total_ingresos_alquileres": total_ingresos_alquileres,
        "total_gastos_registrados": total_gastos,
        "total_dividido": total_dividido,
        "saldo_actual_cuenta": saldo_actual_cuenta,
    }


def home(request):
    access_response = _require_gastos_access(request)
    if access_response:
        return access_response

    hoy = timezone.localdate()

    gastos = Gasto.objects.all().order_by("-fecha", "-creado_en")
    divisiones = DivisionBienes.objects.all().order_by("-fecha", "-creado_en")

    total_gastos_general = gastos.aggregate(s=Sum("monto"))["s"] or Decimal("0")
    gastos_mes = gastos.filter(fecha__year=hoy.year, fecha__month=hoy.month)
    total_gastos_mes = gastos_mes.aggregate(s=Sum("monto"))["s"] or Decimal("0")

    total_div_general = divisiones.aggregate(s=Sum("monto_total"))["s"] or Decimal("0")
    div_mes = divisiones.filter(fecha__year=hoy.year, fecha__month=hoy.month)
    total_div_mes = div_mes.aggregate(s=Sum("monto_total"))["s"] or Decimal("0")

    return render(request, "gastos/home.html", {
        "gastos": gastos,
        "divisiones": divisiones,
        "total_gastos_general": total_gastos_general,
        "total_gastos_mes": total_gastos_mes,
        "total_div_general": total_div_general,
        "total_div_mes": total_div_mes,
        **_resumen_cuenta(),
    })


def crear(request):
    access_response = _require_gastos_access(request)
    if access_response:
        return access_response

    if request.method == "POST":
        form = GastoForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Gasto guardado.")
            return redirect("gastos:home")
        messages.error(request, "Revisa los campos del gasto.")
    else:
        form = GastoForm(initial={"fecha": timezone.localdate()})

    return render(request, "gastos/crear.html", {"form": form})


def division_bienes(request):
    access_response = _require_gastos_access(request)
    if access_response:
        return access_response

    if request.method == "POST":
        form = DivisionBienesForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Division de bienes guardada.")
            return redirect("gastos:home")
        messages.error(request, "Revisa los campos de la division.")
    else:
        form = DivisionBienesForm(initial={"fecha": timezone.localdate()})

    return render(request, "gastos/division.html", {
        "form": form,
        **_resumen_cuenta(),
    })
