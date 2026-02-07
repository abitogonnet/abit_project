from datetime import timedelta
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import VisitaForm
from .models import Visita

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
    if not show_canceladas:
        qs = qs.exclude(estado=Visita.Estado.CANCELADA)

    return render(request, "visitas/listar.html", {
        "visitas": qs,
        "r": r,
        "show_canceladas": show_canceladas,
    })

def crear(request):
    if request.method == "POST":
        form = VisitaForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "✅ Visita creada.")
            return redirect("visitas:listar")
        messages.error(request, "❌ Revisá los campos del formulario.")
    else:
        form = VisitaForm()

    return render(request, "visitas/crear.html", {"form": form})

def cancelar(request, pk):
    v = get_object_or_404(Visita, pk=pk)
    v.estado = Visita.Estado.CANCELADA
    v.save(update_fields=["estado", "updated_at"])
    messages.success(request, "🗑️ Visita cancelada.")
    return redirect("visitas:listar")

def confirmar(request, pk):
    v = get_object_or_404(Visita, pk=pk)
    v.estado = Visita.Estado.CONFIRMADA
    v.save(update_fields=["estado", "updated_at"])
    messages.success(request, "✅ Visita confirmada.")
    return redirect("visitas:listar")
