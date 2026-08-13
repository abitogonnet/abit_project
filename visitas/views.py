import calendar
from datetime import date, datetime, time, timedelta

from django.contrib import messages
from django.db import transaction
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from alquileres.models import Cliente
from alquileres.whatsapp import generar_enlace_whatsapp
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


def _recordatorio_whatsapp(visita):
    if visita.fecha_visita != timezone.localdate() or not visita.hora_visita:
        return ""
    horario = visita.hora_visita.strftime("%H:%M")
    mensaje = (
        f"Hola, te hablo de Abito para confirmar el turno de hoy a las {horario}. "
        "Recordá asistir de manera puntual."
    )
    return generar_enlace_whatsapp(visita.telefono, mensaje)


def _fmt_hora(hora):
    return hora.strftime("%H:%M")


def _bloqueos_para_fecha(fecha_visita):
    return list(
        BloqueoAgenda.objects
        .filter(fecha=fecha_visita, activo=True)
        .order_by("hora_inicio", "id")
    )


def _modulos_bloqueados(hora, bloqueos):
    total = 0
    for bloqueo in bloqueos:
        if bloqueo.hora_inicio is None or bloqueo.hora_fin is None:
            total += bloqueo.modulos

        elif bloqueo.hora_inicio <= hora < bloqueo.hora_fin:
            total += bloqueo.modulos

    return min(total, 2)


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

    capacidad = {hora: 2 - _modulos_bloqueados(hora, bloqueos) for hora in HORARIOS_BASE}

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
    for key, nombre, producto in form.productos_catalogo:
        preferencias_catalogo.append(
            {
                "id": key,
                "nombre": nombre,
                "colores": [color.nombre for color in producto.colores_disponibles] if hasattr(producto, "colores_disponibles") else [],
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
    if alcance == "proximas":
        return calendario_visitas(request)
    qs = Visita.objects.select_related("cliente", "alquiler")
    if alcance == "hoy":
        qs = qs.filter(fecha_visita=hoy)
    elif alcance == "historial":
        qs = qs.filter(fecha_visita__lt=hoy)
    else:
        qs = qs.filter(fecha_visita__gte=hoy)
    visitas = list(qs.order_by("fecha_visita", "hora_visita"))
    for visita in visitas:
        visita.recordatorio_whatsapp_url = _recordatorio_whatsapp(visita)
    return render(request, "visitas/gestion_listar.html", {
        "visitas": visitas,
        "alcance": alcance,
        "visitas_hoy": Visita.objects.filter(
            fecha_visita=hoy, estado=Visita.ESTADO_CONFIRMADA
        ).count(),
    })


def _mes_calendario(request):
    raw = (request.GET.get("mes") or "").strip()
    try:
        year, month = (int(part) for part in raw.split("-", 1))
        return date(year, month, 1)
    except (TypeError, ValueError):
        hoy = timezone.localdate()
        return date(hoy.year, hoy.month, 1)


def _sumar_mes(day, delta):
    month_index = day.year * 12 + day.month - 1 + delta
    return date(month_index // 12, month_index % 12 + 1, 1)


def calendario_visitas(request):
    hoy = timezone.localdate()
    mes = _mes_calendario(request)
    mes_siguiente = _sumar_mes(mes, 1)
    conteos = dict(
        Visita.objects.exclude(estado=Visita.ESTADO_CANCELADA)
        .filter(fecha_visita__gte=mes, fecha_visita__lt=mes_siguiente)
        .values("fecha_visita")
        .annotate(total=Count("id"))
        .values_list("fecha_visita", "total")
    )
    bloqueos = set(
        BloqueoAgenda.objects.filter(
            activo=True, fecha__gte=mes, fecha__lt=mes_siguiente
        ).values_list("fecha", flat=True)
    )
    semanas = []
    cal = calendar.Calendar(firstweekday=0)
    for semana in cal.monthdatescalendar(mes.year, mes.month):
        semanas.append([
            {
                "fecha": dia,
                "en_mes": dia.month == mes.month,
                "es_hoy": dia == hoy,
                "total": conteos.get(dia, 0),
                "bloqueado": dia in bloqueos,
            }
            for dia in semana
        ])
    return render(request, "visitas/calendario.html", {
        "semanas": semanas,
        "mes": mes,
        "mes_anterior": _sumar_mes(mes, -1).strftime("%Y-%m"),
        "mes_siguiente": mes_siguiente.strftime("%Y-%m"),
        "visitas_hoy": Visita.objects.filter(
            fecha_visita=hoy, estado=Visita.ESTADO_CONFIRMADA
        ).count(),
    })


def dia(request, fecha):
    try:
        fecha_seleccionada = datetime.strptime(fecha, "%Y-%m-%d").date()
    except ValueError:
        from django.http import Http404
        raise Http404
    visitas = list(
        Visita.objects.select_related("cliente", "alquiler")
        .prefetch_related("preferencias_ambos")
        .filter(fecha_visita=fecha_seleccionada)
        .order_by("hora_visita", "pk")
    )
    for visita in visitas:
        visita.recordatorio_whatsapp_url = _recordatorio_whatsapp(visita)
    return render(request, "visitas/dia.html", {
        "fecha_seleccionada": fecha_seleccionada,
        "visitas": visitas,
        "bloqueos": BloqueoAgenda.objects.filter(
            fecha=fecha_seleccionada, activo=True
        ).order_by("hora_inicio"),
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
    visita.recordatorio_whatsapp_url = _recordatorio_whatsapp(visita)
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
        if form.cleaned_data["tipo_bloqueo"] == BloqueoAgendaForm.TIPO_DIA:
            bloqueos_creados = [form.save()]
        else:
            bloqueos_creados = []
            for seleccion in form.cleaned_data["modulos_horarios"]:
                hora_texto, _modulo = seleccion.split("|", 1)
                hora_inicio = datetime.strptime(hora_texto, "%H:%M").time()
                hora_fin = (datetime.combine(date.today(), hora_inicio) + timedelta(minutes=30)).time()
                bloqueos_creados.append(BloqueoAgenda.objects.create(
                    fecha=form.cleaned_data["fecha"],
                    hora_inicio=hora_inicio,
                    hora_fin=hora_fin,
                    modulos=1,
                    motivo=form.cleaned_data["motivo"],
                ))
        registrar_actividad(request, "Bloqueó agenda", Actividad.ALQUILER, objeto=bloqueos_creados[0])
        messages.success(request, "Bloqueo guardado.")
        return redirect("visitas:bloqueos")
    return render(request, "visitas/bloqueos.html", {
        "form": form,
        "bloqueos": BloqueoAgenda.objects.filter(
            fecha__gte=timezone.localdate(),
            activo=True,
        ).order_by("fecha", "hora_inicio"),
    })


def eliminar_bloqueo(request, pk):
    bloqueo = get_object_or_404(BloqueoAgenda, pk=pk)
    if request.method == "POST":
        bloqueo.activo = False
        bloqueo.save(update_fields=["activo"])
        registrar_actividad(request, "Desbloqueó agenda", Actividad.ALQUILER, objeto=bloqueo)
        messages.success(request, "Turno desbloqueado.")
    return redirect("visitas:bloqueos")
