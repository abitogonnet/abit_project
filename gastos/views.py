from decimal import Decimal
from django.contrib import messages
from django.db.models import Sum
from django.shortcuts import render, redirect
from django.utils import timezone

from .forms import (
    GastoForm, DivisionBienesForm,
    GASTO_CATEGORIAS, GASTO_METODOS
)
from .models import Gasto, DivisionBienes


def home(request):
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
    })


def crear(request):
    if request.method == "POST":
        form = GastoForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Gasto guardado.")
            return redirect("gastos:home")
        messages.error(request, "Revisá los campos (hay errores).")
    else:
        form = GastoForm(initial={"fecha": timezone.localdate()})

    return render(request, "gastos/crear.html", {
        "form": form,
        "cats": GASTO_CATEGORIAS,
        "mets": GASTO_METODOS,
    })


def division_bienes(request):
    if request.method == "POST":
        form = DivisionBienesForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "División de bienes guardada.")
            return redirect("gastos:home")
        messages.error(request, "Revisá los campos (hay errores).")
    else:
        form = DivisionBienesForm(initial={"fecha": timezone.localdate()})

    return render(request, "gastos/division.html", {
        "form": form,
    })
