from datetime import timedelta
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import VisitaForm
from .models import Visita

# ✅ Google Calendar
from .google_calendar import create_event, delete_event


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
            v = form.save(commit=False)

            # fin del evento
            end_dt = v.inicio + timedelta(minutes=v.duracion_min)

            summary = f"ABITO Visita - {v.telefono}"
            desc = (
                f"Nombre: {v.nombre or '-'}\n"
                f"Teléfono: {v.telefono}\n"
                f"Personas: {v.personas}\n"
                f"Evento: {v.fecha_evento.strftime('%d/%m/%Y')}\n"
                f"Dirección: 489 entre 23 y 24, N° 2871\n"
            )

            # 1) Intento crear en Google Calendar
            try:
                event_id = create_event(summary, desc, v.inicio, end_dt)
                v.calendar_event_id = event_id
            except Exception as e:
                # guardo igual en DB para no perderlo
                messages.error(request, f"⚠️ No se pudo crear en Google Calendar (se guardó igual): {e}")

            # 2) Guardar en DB
            v.save()

            messages.success(request, "✅ Visita creada.")
            return redirect("visitas:listar")

        messages.error(request, "❌ Revisá los campos del formulario.")
    else:
        form = VisitaForm()

    return render(request, "visitas/crear.html", {"form": form})


def cancelar(request, pk):
    v = get_object_or_404(Visita, pk=pk)

    # Borrar en Google Calendar si existe
    if v.calendar_event_id:
        try:
            delete_event(v.calendar_event_id)
            v.calendar_event_id = ""
        except Exception as e:
            messages.error(request, f"⚠️ No se pudo borrar en Calendar (igual se canceló en la app): {e}")

    v.estado = Visita.Estado.CANCELADA
    v.save(update_fields=["calendar_event_id", "estado", "updated_at"])
    messages.success(request, "🗑️ Visita cancelada.")
    return redirect("visitas:listar")


def confirmar(request, pk):
    v = get_object_or_404(Visita, pk=pk)
    v.estado = Visita.Estado.CONFIRMADA
    v.save(update_fields=["estado", "updated_at"])
    messages.success(request, "✅ Visita confirmada.")
    return redirect("visitas:listar")

