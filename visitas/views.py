from datetime import datetime, time

from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from alquileres.models import Cliente
from cuentas.models import Actividad
from cuentas.services import registrar_actividad

from .forms import BloqueoAgendaForm, VisitaForm, VisitaInternaForm
from .models import AgendaDia, BloqueoAgenda, Visita


HORARIOS_BASE = [
    time(17, 0),
    time(17, 30),
    time(18, 0),
    time(18, 30),
    time(19, 0),
    time(19, 30),
]

HORARIOS_INDEX = {hora: idx for idx, hora in enumerate(HORARIOS_BASE)}


def _fmt_hora(hora):
    return hora.strftime("%H:%M")


def _bloqueos_para_fecha(fecha_visita):
    return list(
        BloqueoAgenda.objects
        .filter(fecha=fecha_visita, activo=True)
        .order_by("hora_inicio", "id")
    )


def _hora_bloqueada(hora, bloqueos):
    for bloqueo in bloqueos:
        if bloqueo.hora_inicio is None or bloqueo.hora_fin is None:
            return True

        if bloqueo.hora_inicio <= hora < bloqueo.hora_fin:
            return True

    return False


def _capacidad_por_horario(fecha_visita, visitas_dia=None, bloqueos=None):
    if visitas_dia is None:
        visitas_dia = (
            Visita.objects
            .filter(
                fecha_visita=fecha_visita,
                estado=Visita.ESTADO_CONFIRMADA,
            )
            .order_by("hora_visita", "created_at")
        )

    if bloqueos is None:
        bloqueos = _bloqueos_para_fecha(fecha_visita)

    capacidad = {
        hora: 0 if _hora_bloqueada(hora, bloqueos) else 2
        for hora in HORARIOS_BASE
    }

    for visita in visitas_dia:
        hora = visita.hora_visita
        personas = visita.cantidad_personas

        if hora not in capacidad:
            continue

        if personas == 1:
            capacidad[hora] = max(capacidad[hora] - 1, 0)

        elif personas == 2:
            capacidad[hora] = max(capacidad[hora] - 2, 0)

        elif personas == 3:
            capacidad[hora] = max(capacidad[hora] - 2, 0)

            idx = HORARIOS_INDEX[hora]
            if idx + 1 < len(HORARIOS_BASE):
                siguiente = HORARIOS_BASE[idx + 1]
                capacidad[siguiente] = max(capacidad[siguiente] - 1, 0)

    return capacidad


def _horario_admite_reserva(capacidad, hora, cantidad_personas):
    if hora not in capacidad:
        return False

    idx = HORARIOS_INDEX[hora]
    libres_en_bloque = capacidad[hora]

    if cantidad_personas == 1:
        return libres_en_bloque >= 1

    if cantidad_personas == 2:
        return libres_en_bloque >= 2

    if cantidad_personas == 3:
        if idx + 1 >= len(HORARIOS_BASE):
            return False

        siguiente = HORARIOS_BASE[idx + 1]
        libres_siguiente = capacidad[siguiente]

        return libres_en_bloque >= 2 and libres_siguiente >= 1

    return False


def _horarios_disponibles_para_fecha(fecha_visita, cantidad_personas):
    bloqueos = _bloqueos_para_fecha(fecha_visita)
    capacidad = _capacidad_por_horario(
        fecha_visita,
        bloqueos=bloqueos,
    )
    horarios_disponibles = []

    for hora in HORARIOS_BASE:
        if _horario_admite_reserva(capacidad, hora, cantidad_personas):
            horarios_disponibles.append(hora)

    return horarios_disponibles


def _paso_inicial(form):
    if not form.errors:
        return 1

    if any(campo in form.errors for campo in ["nombre", "telefono", "dni"]):
        return 5

    if any(
        campo in form.errors
        for campo in [
            "vio_prendas_catalogo",
            "preferencia_1_traje",
            "preferencia_1_color",
            "preferencia_1_talle_saco",
            "preferencia_1_talle_pantalon",
            "preferencia_2_traje",
            "preferencia_2_color",
            "preferencia_2_talle_saco",
            "preferencia_2_talle_pantalon",
            "preferencia_3_traje",
            "preferencia_3_color",
            "preferencia_3_talle_saco",
            "preferencia_3_talle_pantalon",
        ]
    ):
        return 4

    if "hora_visita" in form.errors:
        return 3

    if "fecha_visita" in form.errors:
        return 2

    return 1


def reservar(request):
    if request.method == "POST":
        form = VisitaForm(request.POST)

        if form.is_valid():
            fecha_visita = form.cleaned_data["fecha_visita"]
            hora_visita = form.cleaned_data["hora_visita"]
            cantidad_personas = form.cleaned_data["cantidad_personas"]

            with transaction.atomic():
                AgendaDia.objects.get_or_create(fecha=fecha_visita)
                AgendaDia.objects.select_for_update().get(fecha=fecha_visita)
                visitas_dia = list(
                    Visita.objects
                    .select_for_update()
                    .filter(
                        fecha_visita=fecha_visita,
                        estado=Visita.ESTADO_CONFIRMADA,
                    )
                    .order_by("hora_visita", "created_at")
                )
                bloqueos = _bloqueos_para_fecha(fecha_visita)
                capacidad = _capacidad_por_horario(
                    fecha_visita,
                    visitas_dia=visitas_dia,
                    bloqueos=bloqueos,
                )

                if not _horario_admite_reserva(capacidad, hora_visita, cantidad_personas):
                    form.add_error(
                        "hora_visita",
                        "Ese horario esta lleno, bloqueado o no tiene cupo suficiente. Elegi otro.",
                    )
                else:
                    dni = "".join(char for char in form.cleaned_data["dni"] if char.isdigit())
                    cliente, creado = Cliente.objects.select_for_update().get_or_create(
                        dni=dni,
                        defaults={
                            "nombre": form.cleaned_data["nombre"].strip(),
                            "telefono": form.cleaned_data["telefono"].strip(),
                        },
                    )
                    if not creado:
                        changed = []
                        nombre = form.cleaned_data["nombre"].strip()
                        telefono = form.cleaned_data["telefono"].strip()
                        if nombre and cliente.nombre != nombre:
                            cliente.nombre = nombre
                            changed.append("nombre")
                        if telefono and cliente.telefono != telefono:
                            cliente.telefono = telefono
                            changed.append("telefono")
                        if changed:
                            cliente.save(update_fields=changed + ["actualizado_en"])
                    visita = form.save(commit=False)
                    visita.dni = dni
                    visita.cliente = cliente
                    visita.estado = Visita.ESTADO_CONFIRMADA
                    visita.origen = Visita.ORIGEN_WEB
                    visita.save()
                    form.save_preferencias(visita)
                    request.session["ultima_visita_id"] = visita.id
                    return redirect("visitas:confirmada")
    else:
        form = VisitaForm()

    preferencias_catalogo = []
    for traje in form.trajes_catalogo:
        preferencias_catalogo.append(
            {
                "id": traje.id,
                "nombre": f"{traje.get_linea_display()} - {traje.tela}",
                "colores": list(
                    dict.fromkeys(variante.color for variante in traje.talles.all())
                ),
            }
        )

    return render(
        request,
        "visitas/reservar.html",
        {
            "form": form,
            "initial_step": _paso_inicial(form),
            "preferencias_catalogo": preferencias_catalogo,
        },
    )


def confirmada(request):
    visita_id = request.session.get("ultima_visita_id")

    if not visita_id:
        return redirect("visitas:reservar")

    visita = get_object_or_404(
        Visita.objects.prefetch_related("preferencias_ambos"),
        pk=visita_id,
    )

    return render(
        request,
        "visitas/confirmada.html",
        {
            "visita": visita,
        },
    )


def horarios_disponibles(request):
    fecha_str = request.GET.get("fecha")
    personas_str = request.GET.get("personas")

    if not fecha_str or not personas_str:
        return JsonResponse({"horarios": []})

    try:
        fecha_visita = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        cantidad_personas = int(personas_str)
    except (ValueError, TypeError):
        return JsonResponse({"horarios": []})

    if cantidad_personas not in [1, 2, 3]:
        return JsonResponse({"horarios": []})

    if fecha_visita < timezone.localdate() or fecha_visita.weekday() > 4:
        return JsonResponse({"horarios": []})

    horarios = _horarios_disponibles_para_fecha(
        fecha_visita,
        cantidad_personas,
    )

    return JsonResponse({
        "horarios": [_fmt_hora(h) for h in horarios],
    })


def listar(request):
    hoy = timezone.localdate()
    alcance = request.GET.get("alcance", "proximas")
    qs = Visita.objects.select_related("cliente", "alquiler")
    if alcance == "hoy":
        qs = qs.filter(fecha_visita=hoy)
    elif alcance == "historial":
        qs = qs.filter(fecha_visita__lt=hoy)
    else:
        qs = qs.filter(fecha_visita__gte=hoy)
    return render(request, "visitas/gestion_listar.html", {
        "visitas": qs.order_by("fecha_visita", "hora_visita"),
        "alcance": alcance,
        "visitas_hoy": Visita.objects.filter(
            fecha_visita=hoy, estado=Visita.ESTADO_CONFIRMADA
        ).count(),
    })


def detalle(request, pk):
    visita = get_object_or_404(
        Visita.objects.select_related("cliente", "alquiler").prefetch_related("preferencias_ambos"),
        pk=pk,
    )
    if request.method == "POST":
        form = VisitaInternaForm(request.POST, instance=visita)
        if form.is_valid():
            form.save()
            registrar_actividad(request, "Actualizó visita", Actividad.ALQUILER, objeto=visita)
            messages.success(request, "Visita actualizada.")
            return redirect("visitas:detalle", pk=pk)
    else:
        form = VisitaInternaForm(instance=visita)
    return render(request, "visitas/detalle.html", {"visita": visita, "form": form})


def crear_alquiler(request, pk):
    visita = get_object_or_404(Visita.objects.select_related("cliente", "alquiler"), pk=pk)
    if visita.alquiler_id:
        return redirect(f"{reverse('alquileres:ver')}?buscar={visita.alquiler_id}")
    request.session["visita_para_alquiler"] = visita.pk
    return redirect("alquileres:crear")


def bloqueos(request):
    form = BloqueoAgendaForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        bloqueo = form.save()
        registrar_actividad(request, "Bloqueó agenda", Actividad.ALQUILER, objeto=bloqueo)
        messages.success(request, "Bloqueo guardado.")
        return redirect("visitas:bloqueos")
    return render(request, "visitas/bloqueos.html", {
        "form": form,
        "bloqueos": BloqueoAgenda.objects.filter(fecha__gte=timezone.localdate()).order_by("fecha", "hora_inicio"),
    })


def eliminar_bloqueo(request, pk):
    bloqueo = get_object_or_404(BloqueoAgenda, pk=pk)
    if request.method == "POST":
        bloqueo.activo = False
        bloqueo.save(update_fields=["activo"])
        messages.success(request, "Bloqueo desactivado.")
    return redirect("visitas:bloqueos")
