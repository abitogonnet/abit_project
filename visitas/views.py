from datetime import timedelta

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import VisitaForm
from .models import Visita


def _rango_label(r):
    if r == "today":
        return "Solo hoy"
    if r == "all":
        return "Agenda completa"
    return "Proximos 7 dias"


def listar(request):
    r = request.GET.get("r", "week").lower()
    now = timezone.localtime()

    qs = Visita.objects.all()

    if r == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        qs = qs.filter(inicio__gte=start, inicio__lt=end)
    elif r == "week":
        start = now
        end = now + timedelta(days=7)
        qs = qs.filter(inicio__gte=start, inicio__lt=end)

    show_canceladas = request.GET.get("canceladas", "0") == "1"
    resumen_base = qs
    if not show_canceladas:
        qs = qs.exclude(estado=Visita.Estado.CANCELADA)

    visitas = list(qs.order_by("inicio", "pk"))
    proxima_visita = visitas[0] if visitas else None

    return render(request, "visitas/listar.html", {
        "visitas": visitas,
        "r": r,
        "show_canceladas": show_canceladas,
        "range_label": _rango_label(r),
        "summary": [
            {"label": "Visitas visibles", "value": len(visitas)},
            {
                "label": "Confirmadas",
                "value": resumen_base.filter(estado=Visita.Estado.CONFIRMADA).count(),
            },
            {
                "label": "Pendientes",
                "value": resumen_base.filter(estado=Visita.Estado.PENDIENTE).count(),
            },
            {
                "label": "Canceladas",
                "value": resumen_base.filter(estado=Visita.Estado.CANCELADA).count(),
            },
        ],
        "proxima_visita": proxima_visita,
    })


def crear(request):
    if request.method == "POST":
        form = VisitaForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Visita creada.")
            return redirect("visitas:listar")
        messages.error(request, "Revisa los campos del formulario.")
    else:
        ahora = timezone.localtime()
        inicio_sugerido = ahora.replace(minute=0, second=0, microsecond=0)
        form = VisitaForm(initial={
            "fecha_evento": timezone.localdate(),
            "inicio": inicio_sugerido.strftime("%Y-%m-%dT%H:%M"),
        })

    return render(request, "visitas/crear.html", {"form": form})


def cancelar(request, pk):
    visita = get_object_or_404(Visita, pk=pk)
    visita.estado = Visita.Estado.CANCELADA
    visita.save(update_fields=["estado", "updated_at"])
    messages.success(request, "Visita cancelada.")
    return redirect("visitas:listar")


def confirmar(request, pk):
    visita = get_object_or_404(Visita, pk=pk)
    visita.estado = Visita.Estado.CONFIRMADA
    visita.save(update_fields=["estado", "updated_at"])
    messages.success(request, "Visita confirmada.")
    return redirect("visitas:listar")
