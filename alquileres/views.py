from datetime import date, timedelta
from decimal import Decimal
from urllib.parse import urlencode
import secrets

from django.contrib import messages
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.http import Http404, JsonResponse
from django.urls import reverse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from prendas.models import Prenda

from .forms import AlquilerEdicionForm, AlquilerForm, SHORT_POR_CATEGORIA, VerAlquileresFiltroForm
from .models import Alquiler, AlquilerItem, Cliente
from .whatsapp import generar_enlace_whatsapp, mensaje_recordatorio
from cuentas.models import Actividad
from cuentas.services import registrar_actividad
from gastos.services import registrar_movimiento, registrar_saldo, registrar_sena, sincronizar_movimientos_alquiler

try:
    from visitas.models import Visita
except Exception:  # pragma: no cover - fallback defensivo si la app no esta disponible
    Visita = None


RUEDOS_MESSAGE_LABELS = {
    Prenda.C_SACO: "SACO",
    Prenda.C_PANTALON: "PANT",
    Prenda.C_CAMISA: "CAMISA",
    Prenda.C_CHALECO: "CHALECO",
    Prenda.C_MONO: "MONO",
    Prenda.C_CORBATA: "CORBATA",
    Prenda.C_ZAPATOS: "ZAPATOS",
    Prenda.C_CINTURON: "CINTURON",
}


def home(request):
    if request.method == "POST":
        alquiler_id = request.POST.get("alq_id")
        alquiler = get_object_or_404(Alquiler, id=alquiler_id)
        accion = request.POST.get("accion", "")

        if _procesar_accion_operativa(request, alquiler, accion):
            if accion == "cerrar_alquiler" and alquiler.estado_alquiler == Alquiler.EST_CERRADO:
                return redirect(f"{reverse('alquileres:home')}?cerrado={alquiler.id}")
            return redirect("alquileres:home")

    hoy = timezone.localdate()
    proximos_siete = hoy + timedelta(days=7)

    alquileres_activos = (
        Alquiler.objects
        .filter(estado_alquiler__in=Alquiler.ESTADOS_ALQUILER_ACTIVOS)
    )
    entregas_hoy_lista = list(
        Alquiler.objects.filter(estado_alquiler__in=[Alquiler.EST_RESERVADO, Alquiler.EST_ENTREGADO], fecha_entrega=hoy)
        .prefetch_related("items__prenda").order_by("id")
    )
    entregas_hoy = len(entregas_hoy_lista)
    devoluciones_hoy_qs = (
        Alquiler.objects
        .filter(estado_alquiler=Alquiler.EST_ENTREGADO, fecha_devolucion=hoy)
        .prefetch_related("items__prenda")
        .order_by("fecha_entrega", "id")
    )
    devoluciones_hoy = list(devoluciones_hoy_qs)
    entregas_pendientes_confirmar = list(
        Alquiler.objects.filter(estado_alquiler=Alquiler.EST_RESERVADO, fecha_entrega__lt=hoy)
        .prefetch_related("items__prenda").order_by("fecha_entrega", "id")
    )
    atrasados_lista = list(
        Alquiler.objects.filter(estado_alquiler=Alquiler.EST_ENTREGADO, fecha_devolucion__lt=hoy)
        .prefetch_related("items__prenda").order_by("fecha_devolucion", "id")
    )
    entregas_semana_lista = list(
        Alquiler.objects.filter(
            estado_alquiler=Alquiler.EST_RESERVADO,
            fecha_entrega__gt=hoy,
            fecha_entrega__lte=proximos_siete,
        ).prefetch_related("items__prenda").order_by("fecha_entrega", "id")
    )
    devoluciones_retrasadas = len(atrasados_lista)
    saldos_pendientes = alquileres_activos.filter(estado_saldo=Alquiler.SAL_PEND, saldo__gt=0).count()
    alquileres_semana = alquileres_activos.filter(
        fecha_entrega__gte=hoy,
        fecha_entrega__lte=proximos_siete,
    ).count()

    stock_disponible = Prenda.objects.filter(estado=Prenda.E_DISP).count()
    pendientes_origen = Prenda.objects.filter(
        categoria__in=[Prenda.C_SACO, Prenda.C_PANTALON],
        origen="",
    ).count()
    ruedos_pendientes = list(
        AlquilerItem.objects.select_related("alquiler", "prenda")
        .filter(
            ruedo_valor__gt=0, ruedo_listo=False,
            alquiler__estado_alquiler__in=Alquiler.ESTADOS_ALQUILER_ACTIVOS,
            alquiler__fecha_entrega__gte=hoy,
            alquiler__fecha_entrega__lte=proximos_siete,
        )
        .order_by("alquiler__fecha_entrega", "prenda__codigo")
    )

    visitas_hoy = 0
    visitas_semana = 0
    if Visita is not None:
        ahora = timezone.localtime()
        inicio_dia = ahora.replace(hour=0, minute=0, second=0, microsecond=0)
        fin_dia = inicio_dia + timedelta(days=1)
        fin_semana = ahora + timedelta(days=7)
        visitas_base = Visita.objects.exclude(estado=Visita.Estado.CANCELADA)
        visitas_hoy = visitas_base.filter(inicio__gte=inicio_dia, inicio__lt=fin_dia).count()
        visitas_semana = visitas_base.filter(inicio__gte=ahora, inicio__lt=fin_semana).count()

    kpis = [
        {
            "label": "Entregas de hoy",
            "value": entregas_hoy,
            "tone": "warn" if entregas_hoy else "neutral",
            "helper": "Lo que se retira o entrega hoy.",
            "href": reverse("alquileres:entregas"),
        },
        {
            "label": "Devoluciones atrasadas",
            "value": devoluciones_retrasadas,
            "tone": "danger" if devoluciones_retrasadas else "neutral",
            "helper": "Alquileres que ya deberian haber vuelto.",
            "href": reverse("alquileres:retrasados"),
        },
        {
            "label": "Saldos pendientes",
            "value": saldos_pendientes,
            "tone": "accent" if saldos_pendientes else "neutral",
            "helper": "Cobros abiertos sobre alquileres activos.",
            "href": reverse("alquileres:ver"),
        },
        {
            "label": "Stock disponible",
            "value": stock_disponible,
            "tone": "neutral",
            "helper": "Prendas listas para volver a salir.",
            "href": reverse("prendas:stock"),
        },
    ]

    prioridades = []
    if getattr(getattr(request.user, "perfil", None), "debe_cambiar_password", False):
        prioridades.insert(0, {
            "kind": "link",
            "title": "Modificar contraseña",
            "description": "Reemplazá la contraseña temporal por una contraseña personal.",
            "href": reverse("cuentas:cambiar_password"),
            "cta": "Modificar contraseña",
            "tone": "warn",
        })
    listas_operativas = [entregas_hoy_lista, devoluciones_hoy, entregas_semana_lista, entregas_pendientes_confirmar, atrasados_lista]
    for lista in listas_operativas:
        _adjuntar_detalle_alquiler(lista)

    cerrado_id = request.GET.get("cerrado", "")
    if cerrado_id.isdigit():
        alquiler_cerrado = Alquiler.objects.filter(
            id=int(cerrado_id),
            estado_alquiler=Alquiler.EST_CERRADO,
        ).first()
        if alquiler_cerrado:
            prioridades.insert(0, {
                "kind": "closed_today",
                "title": alquiler_cerrado.cliente_nombre,
                "description": "Alquiler cerrado correctamente",
                "tone": "ok",
            })
    if pendientes_origen:
        prioridades.insert(0, {
            "kind": "link",
            "title": f"Corregir stock — {pendientes_origen} prendas pendientes",
            "description": f"Quedan {pendientes_origen} prenda{'s' if pendientes_origen != 1 else ''} sin origen cargado.",
            "href": reverse("prendas:stock"),
            "cta": "Corregir stock",
            "tone": "accent",
        })
    prioridades_ruedos = []
    for item in ruedos_pendientes:
        dias = (item.alquiler.fecha_entrega - hoy).days
        urgente = dias <= 3
        prioridades_ruedos.append({
            "kind": "link",
            "title": ("URGENTE — Ruedo pendiente" if urgente else "Ruedo pendiente"),
            "description": f"{item.prenda.codigo} · entrega {item.alquiler.fecha_entrega.strftime('%d/%m/%Y')} · faltan {dias} día{'s' if dias != 1 else ''}.",
            "href": reverse("alquileres:ruedos"),
            "cta": "Ver ruedos",
            "tone": "danger" if urgente else "warn",
        })
    prioridades[0:0] = prioridades_ruedos
    if not prioridades:
        prioridades.append({
            "kind": "link",
            "title": "Todo bajo control",
            "description": "No hay alertas fuertes. Puedes enfocarte en nuevas reservas, stock y seguimiento fino.",
            "href": reverse("alquileres:crear"),
            "cta": "Crear alquiler",
            "tone": "ok",
        })
    prioridades_destacadas = [
        item for item in prioridades
        if item.get("title", "").startswith(("URGENTE", "Ruedo pendiente", "Corregir stock"))
    ]
    prioridades = [item for item in prioridades if item not in prioridades_destacadas]

    flujos = [
        {
            "eyebrow": "Operacion diaria",
            "title": "Alquileres y entregas",
            "description": "Carga nuevas reservas, sigue cobros, prepara entregas y resuelve devoluciones desde un circuito simple.",
            "primary_href": reverse("alquileres:crear"),
            "primary_label": "Nuevo alquiler",
            "secondary_href": reverse("alquileres:ver"),
            "secondary_label": "Ver alquileres",
        },
        {
            "eyebrow": "Inventario",
            "title": "Stock vivo y facil de leer",
            "description": "Filtra, corrige estados y completa datos sin perder tiempo en tablas confusas.",
            "primary_href": reverse("prendas:stock"),
            "primary_label": "Abrir stock",
            "secondary_href": reverse("prendas:buscar_prenda"),
            "secondary_label": "Buscar prenda",
        },
        {
            "eyebrow": "Agenda",
            "title": "Visitas y preparacion comercial",
            "description": "Centraliza las citas y deja visible lo que viene hoy y durante la semana.",
            "primary_href": reverse("visitas:listar"),
            "primary_label": "Ver agenda",
            "secondary_href": reverse("visitas:crear"),
            "secondary_label": "Crear visita",
        },
    ]

    aprendizaje = [
        {
            "step": "1",
            "title": "Empieza por el tablero",
            "description": "La portada prioriza lo urgente para que cualquiera entienda rapido que hay que atender hoy.",
        },
        {
            "step": "2",
            "title": "Carga guiada del alquiler",
            "description": "El alta queda dividida por cliente, prendas y pago en vez de parecer un formulario tecnico.",
        },
        {
            "step": "3",
            "title": "Controla operacion y stock",
            "description": "Despues del alta, el trabajo diario se reparte entre entregas, atrasos, agenda y stock.",
        },
    ]

    proximos_movimientos = list(
        alquileres_activos
        .filter(fecha_entrega__gte=hoy, fecha_entrega__lte=proximos_siete)
        .prefetch_related("items__prenda")
        .order_by("fecha_entrega", "id")
    )
    _adjuntar_detalle_alquiler(proximos_movimientos)
    proximos_movimientos_por_dia = _agrupar_movimientos_por_dia(proximos_movimientos)

    return render(request, "alquileres/home.html", {
        "hoy": hoy,
        "kpis": kpis,
        "prioridades": prioridades,
        "prioridades_destacadas": prioridades_destacadas,
        "entregas_hoy_lista": entregas_hoy_lista,
        "devoluciones_hoy_lista": devoluciones_hoy,
        "entregas_semana_lista": entregas_semana_lista,
        "mostrar_entregas_semana": (not entregas_hoy_lista and not devoluciones_hoy) or (entregas_hoy_lista and devoluciones_hoy),
        "entregas_pendientes_confirmar": entregas_pendientes_confirmar,
        "atrasados_lista": atrasados_lista,
        "flujos": flujos,
        "aprendizaje": aprendizaje,
        "proximos_movimientos": proximos_movimientos,
        "proximos_movimientos_por_dia": proximos_movimientos_por_dia,
        "resumen_operativo": {
            "alquileres_activos": alquileres_activos.count(),
            "alquileres_semana": alquileres_semana,
            "visitas_hoy": visitas_hoy,
            "visitas_semana": visitas_semana,
            "pendientes_origen": pendientes_origen,
        },
    })


def _fmt_date(d):
    if not d:
        return ""
    return d.strftime("%d/%m/%Y")


def _descripcion_prenda(prenda: Prenda) -> str:
    partes = []
    if prenda.color:
        partes.append(prenda.color)
    if prenda.talle:
        partes.append(f"talle {prenda.talle}")
    return " ".join(partes)


def _texto_ruedo(item: AlquilerItem) -> str:
    partes = []
    if item.ruedo_valor is not None:
        partes.append(_fmt_decimal_compact(item.ruedo_valor))
    if item.ruedo_tipo:
        partes.append(item.get_ruedo_tipo_display())
    return " ".join(partes)


def _start_of_week(day):
    return day - timedelta(days=day.weekday())


def _week_value(day):
    iso = day.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _parse_week_value(raw, fallback):
    value = (raw or "").strip()
    if not value or "-W" not in value:
        return fallback

    year_text, week_text = value.split("-W", 1)
    try:
        return date.fromisocalendar(int(year_text), int(week_text), 1)
    except Exception:
        return fallback


def _fmt_decimal_compact(value):
    if value is None:
        return ""

    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _texto_ruedo_mensaje(item: AlquilerItem) -> str:
    cantidad = _fmt_decimal_compact(item.ruedo_valor)
    tipo = item.get_ruedo_tipo_display().upper() if item.ruedo_tipo else ""
    if cantidad and tipo:
        return f"{cantidad}{tipo}"
    return cantidad or tipo


def _detalle_prenda_ruedo_tabla(prenda: Prenda) -> str:
    partes = [prenda.get_categoria_display()]
    if prenda.color:
        partes.append(prenda.color)
    if prenda.marca:
        partes.append(prenda.marca)
    if prenda.talle:
        partes.append(f"talle {prenda.talle}")
    if prenda.origen:
        partes.append(prenda.get_origen_display())
    return " ".join(partes)


def _detalle_prenda_ruedo_mensaje(prenda: Prenda) -> str:
    partes = [RUEDOS_MESSAGE_LABELS.get(prenda.categoria, prenda.get_categoria_display().upper())]
    if prenda.color:
        partes.append(prenda.color.upper())
    if prenda.marca:
        partes.append(prenda.marca.upper())
    if prenda.talle:
        partes.append(str(prenda.talle).upper())
    if prenda.origen:
        partes.append(_origen_ruedo_mensaje(prenda))
    return " ".join(partes)


def _origen_ruedo_mensaje(prenda: Prenda) -> str:
    if prenda.origen == Prenda.O_NAC:
        return "TELA MECA"
    if prenda.origen == Prenda.O_IMP:
        return "IMPORTADO"
    return prenda.get_origen_display().upper()


def _agrupar_movimientos_por_dia(alquileres):
    grupos = []
    actual = None

    for alquiler in alquileres:
        if actual is None or actual["fecha"] != alquiler.fecha_entrega:
            actual = {
                "fecha": alquiler.fecha_entrega,
                "alquileres": [],
            }
            grupos.append(actual)
        actual["alquileres"].append(alquiler)

    return grupos


def _armar_mensaje_ruedos(items):
    if not items:
        return ""

    partes = []
    fecha_actual = None
    for item in items:
        if item["fecha_a_hacer"] != fecha_actual:
            if fecha_actual is not None:
                partes.append("")
            partes.append(f'FECHA A HACER {item["fecha_a_hacer"].strftime("%d/%m/%Y")}')
            fecha_actual = item["fecha_a_hacer"]
        partes.append(item["mensaje_linea"])
    return "\n".join(partes)


def _numero_codigo(codigo: str) -> str:
    if not codigo:
        return ""
    if "-" in codigo:
        return codigo.split("-", 1)[1]
    return codigo


def _descripcion_prenda_tabla(item: dict) -> str:
    partes = [item["categoria"]]
    for key in ("color", "marca"):
        valor = (item.get(key) or "").strip()
        if valor and valor != "-":
            partes.append(valor)

    talle = (item.get("talle") or "").strip()
    if talle and talle != "-":
        partes.append(f"talle {talle}")

    origen = (item.get("origen") or "").strip()
    if origen and origen != "-":
        partes.append(origen)

    return " ".join(partes)


def _texto_ruedo_categoria(items_persona: list[dict], categoria: str) -> str:
    items_categoria = [item for item in items_persona if item["categoria_key"] == categoria]
    if not items_categoria:
        return "Sin prenda"
    return " / ".join(item["ruedo"] for item in items_categoria) or "Sin ruedo"


def _badge_estado_alquiler(value: str) -> str:
    if value == Alquiler.EST_CANCELADO:
        return "danger"
    if value == Alquiler.EST_CERRADO:
        return "ok"
    if value == Alquiler.EST_ENTREGADO:
        return "warn"
    return "secondary"


def _badge_estado_saldo(value: str) -> str:
    if value == Alquiler.SAL_PAG:
        return "ok"
    return "warn"


def _badge_estado_prenda(value: str) -> str:
    if value == Prenda.E_DISP:
        return "ok"
    if value == Prenda.E_ENT:
        return "warn"
    if value == Prenda.E_DAN:
        return "danger"
    if value == Prenda.E_LAV:
        return "warn"
    return "secondary"


def _orden_entrega_key(alquiler: Alquiler, hoy):
    delta_dias = (alquiler.fecha_entrega - hoy).days
    return (
        alquiler.estado_alquiler in Alquiler.ESTADOS_ALQUILER_FINALES,
        abs(delta_dias),
        delta_dias < 0,
        alquiler.fecha_entrega,
        alquiler.fecha_devolucion,
        alquiler.id,
    )


def _ordenar_alquileres_por_entrega(alquileres, hoy):
    # Se ordena despues del filtrado para evitar SQL especifico de cada motor
    # y mantener la lista rapida y consistente en todas las pantallas.
    return sorted(alquileres, key=lambda alquiler: _orden_entrega_key(alquiler, hoy))


def _saldo_restante_actual(alquiler: Alquiler) -> Decimal:
    return alquiler.saldo_pendiente_actual


def _estado_saldo_actual(alquiler: Alquiler) -> str:
    return Alquiler.SAL_PAG if alquiler.esta_completamente_abonado else Alquiler.SAL_PEND


def _metodos_pago_actuales(alquiler: Alquiler) -> list[str]:
    detalles = []

    if alquiler.sena > 0 and alquiler.metodo_sena:
        etiqueta = "Pago total" if alquiler.saldo <= 0 else "Seña"
        detalles.append(f"{etiqueta}: {alquiler.get_metodo_sena_display()}")

    if alquiler.saldo > 0 and alquiler.estado_saldo == Alquiler.SAL_PAG and alquiler.metodo_saldo:
        detalles.append(f"Saldo: {alquiler.get_metodo_saldo_display()}")

    if not detalles:
        detalles.append("Sin medio cargado")

    return detalles


def _persona_nombre_alquiler(alquiler: Alquiler, persona_num: int) -> str:
    return alquiler.persona_nombre(persona_num).strip()


def _armar_mensaje_cliente_con_items(alq: Alquiler, items) -> str:
    partes = []
    partes.append("Hola, te mando el detallado de lo que alquilaste:")
    partes.append("")
    partes.append("FECHAS")
    partes.append(f"- Reserva: {_fmt_date(alq.fecha_reserva)}")
    partes.append(f"- Entrega: {_fmt_date(alq.fecha_entrega)}")
    partes.append(f"- Devolucion: {_fmt_date(alq.fecha_devolucion)}")
    partes.append("")

    for persona_num in range(1, Alquiler.MAX_PERSONAS + 1):
        items_persona = [item for item in items if item.persona_num == persona_num]
        persona_nombre = _persona_nombre_alquiler(alq, persona_num)
        if not (persona_nombre or items_persona):
            continue

        partes.append(persona_nombre or f"Persona {persona_num}")
        for item in items_persona:
            prenda = item.prenda
            detalle_prenda = _descripcion_prenda(prenda)
            extra_ruedo = ""
            if item.ruedo_valor and item.ruedo_tipo:
                extra_ruedo = f" (Ruedo: {item.ruedo_valor} {item.get_ruedo_tipo_display()})"
            if detalle_prenda:
                partes.append(f"- {prenda.get_categoria_display()}: {detalle_prenda}{extra_ruedo}")
            else:
                partes.append(f"- {prenda.get_categoria_display()}{extra_ruedo}")
        partes.append("")

    partes.append("PAGO")
    partes.append(f"- Total: ${alq.total_bruto}")
    if alq.descuento_pct and alq.descuento_pct > 0:
        partes.append(f"- Descuento: {alq.descuento_pct}% (-${alq.descuento_monto})")
        partes.append(f"- Total final: ${alq.total_final}")
    else:
        partes.append(f"- Total final: ${alq.total_final}")
    partes.append(f"- Sena: ${alq.sena}")
    if not alq.esta_completamente_abonado:
        partes.append(f"- Resta: ${alq.saldo_pendiente_actual}")

    return "\n".join(partes)


def _adjuntar_detalle_alquiler(alquileres):
    for alquiler in alquileres:
        items = list(alquiler.items.all())
        personas = []

        for persona_num in range(1, Alquiler.MAX_PERSONAS + 1):
            persona_nombre = _persona_nombre_alquiler(alquiler, persona_num)
            items_persona = []
            for item in items:
                if item.persona_num != persona_num:
                    continue

                prenda = item.prenda
                items_persona.append({
                    "categoria_key": prenda.categoria,
                    "categoria": prenda.get_categoria_display(),
                    "codigo": prenda.codigo,
                    "codigo_numero": _numero_codigo(prenda.codigo),
                    "marca": prenda.marca or "-",
                    "color": prenda.color or "-",
                    "talle": prenda.talle or "-",
                    "origen": prenda.get_origen_display() or "-",
                    "ruedo": _texto_ruedo(item) or "Sin ruedo",
                    "estado_prenda": prenda.estado,
                    "estado_prenda_display": prenda.get_estado_display(),
                    "notas": item.notas or prenda.notas or "",
                })

            if not ((persona_nombre or "").strip() or items_persona):
                continue

            personas.append({
                "numero": persona_num,
                "nombre": (persona_nombre or "").strip() or f"Persona {persona_num}",
                "cantidad": len(items_persona),
                "codigos": ", ".join(item["codigo"] for item in items_persona),
                "items": items_persona,
            })

        alquiler.detalle_personas = personas
        alquiler.total_prendas_detalle = sum(persona["cantidad"] for persona in personas)
        alquiler.personas_resumen = ", ".join(persona["nombre"] for persona in personas)

        alquiler.prendas_tabla = []
        alquiler.ruedos_tabla = {
            "saco": [],
            "pantalon": [],
        }
        estados_prenda_count = {}

        for persona in personas:
            alquiler.prendas_tabla.append({
                "persona": persona["nombre"],
                "items": [
                    {
                        "titulo": f'{item["categoria"]} {item["codigo_numero"]}'.strip(),
                        "descripcion": _descripcion_prenda_tabla(item),
                    }
                    for item in persona["items"]
                ],
                "ruedo_saco": _texto_ruedo_categoria(persona["items"], Prenda.C_SACO),
                "ruedo_pantalon": _texto_ruedo_categoria(persona["items"], Prenda.C_PANTALON),
            })

            for item in persona["items"]:
                estado_actual = item["estado_prenda"]
                if estado_actual not in estados_prenda_count:
                    estados_prenda_count[estado_actual] = {
                        "value": estado_actual,
                        "label": item["estado_prenda_display"],
                        "count": 0,
                        "badge_class": _badge_estado_prenda(estado_actual),
                    }
                estados_prenda_count[estado_actual]["count"] += 1

                if item["categoria_key"] == Prenda.C_SACO:
                    alquiler.ruedos_tabla["saco"].append({
                        "categoria": item["categoria"],
                        "ruedo": item["ruedo"],
                    })
                if item["categoria_key"] == Prenda.C_PANTALON:
                    alquiler.ruedos_tabla["pantalon"].append({
                        "categoria": item["categoria"],
                        "ruedo": item["ruedo"],
                    })

        alquiler.estado_prendas = [
            estados_prenda_count[value]
            for value, _ in Prenda.ESTADOS
            if value in estados_prenda_count
        ]

        alquiler.saldo_restante_actual = _saldo_restante_actual(alquiler)
        alquiler.abono_actual = alquiler.total_final - alquiler.saldo_restante_actual
        alquiler.estado_saldo_actual = _estado_saldo_actual(alquiler)
        alquiler.estado_saldo_actual_label = dict(Alquiler.ESTADOS_SALDO)[alquiler.estado_saldo_actual]
        alquiler.metodos_pago_actuales = _metodos_pago_actuales(alquiler)
        alquiler.estado_alquiler_badge = _badge_estado_alquiler(alquiler.estado_alquiler)
        alquiler.estado_saldo_badge = _badge_estado_saldo(alquiler.estado_saldo_actual)
        alquiler.saldo_editable = alquiler.saldo > 0
        alquiler.mensaje_cliente = _armar_mensaje_cliente_con_items(alquiler, items)
        alquiler.whatsapp_url = generar_enlace_whatsapp(alquiler.cliente_telefono, alquiler.mensaje_cliente)
        alquiler.recordatorio_whatsapp_url = generar_enlace_whatsapp(alquiler.cliente_telefono, mensaje_recordatorio(alquiler))
        alquiler.ver_url = f"{reverse('alquileres:ver')}#alquiler-{alquiler.id}"
        alquiler.esta_finalizado = alquiler.estado_alquiler in Alquiler.ESTADOS_ALQUILER_FINALES
        alquiler.puede_marcar_entregado = alquiler.estado_alquiler == Alquiler.EST_RESERVADO
        alquiler.puede_cerrar = alquiler.estado_alquiler in Alquiler.ESTADOS_ALQUILER_ACTIVOS
        alquiler.puede_cancelar = alquiler.estado_alquiler == Alquiler.EST_RESERVADO
        alquiler.puede_toggle_saldo = alquiler.saldo > 0 and not alquiler.esta_finalizado

        if alquiler.estado_alquiler == Alquiler.EST_CANCELADO:
            alquiler.accion_entrega_label = "Cancelado"
            alquiler.accion_entrega_clase = "danger"
            alquiler.accion_entrega_deshabilitada = True
        elif alquiler.estado_alquiler == Alquiler.EST_CERRADO:
            alquiler.accion_entrega_label = "Cerrado"
            alquiler.accion_entrega_clase = "ok"
            alquiler.accion_entrega_deshabilitada = True
        elif alquiler.estado_alquiler == Alquiler.EST_ENTREGADO:
            alquiler.accion_entrega_label = "Entregado"
            alquiler.accion_entrega_clase = "warn"
            alquiler.accion_entrega_deshabilitada = True
        else:
            alquiler.accion_entrega_label = "Entregado"
            alquiler.accion_entrega_clase = "neutral"
            alquiler.accion_entrega_deshabilitada = False

        if alquiler.estado_saldo_actual == Alquiler.SAL_PAG or alquiler.saldo <= 0:
            alquiler.accion_saldo_clase = "ok"
            alquiler.accion_saldo_deshabilitada = not alquiler.puede_toggle_saldo
        else:
            alquiler.accion_saldo_clase = "neutral"
            alquiler.accion_saldo_deshabilitada = not alquiler.puede_toggle_saldo

        if alquiler.estado_alquiler == Alquiler.EST_CANCELADO:
            alquiler.accion_cierre_label = "Cancelado"
            alquiler.accion_cierre_clase = "danger"
            alquiler.accion_cierre_deshabilitada = True
        elif alquiler.estado_alquiler == Alquiler.EST_CERRADO:
            alquiler.accion_cierre_label = "Cerrado"
            alquiler.accion_cierre_clase = "ok"
            alquiler.accion_cierre_deshabilitada = True
        else:
            alquiler.accion_cierre_label = "Cerrar"
            alquiler.accion_cierre_clase = "ok-soft"
            alquiler.accion_cierre_deshabilitada = False

        if alquiler.estado_alquiler == Alquiler.EST_CANCELADO:
            alquiler.accion_cancelar_label = "Cancelado"
            alquiler.accion_cancelar_clase = "danger"
            alquiler.accion_cancelar_deshabilitada = True
        elif alquiler.estado_alquiler == Alquiler.EST_CERRADO:
            alquiler.accion_cancelar_label = "Cancelado"
            alquiler.accion_cancelar_clase = "neutral"
            alquiler.accion_cancelar_deshabilitada = True
        else:
            alquiler.accion_cancelar_label = "Cancelado"
            alquiler.accion_cancelar_clase = "danger-soft"
            alquiler.accion_cancelar_deshabilitada = not alquiler.puede_cancelar


def _adjuntar_formularios_edicion(alquileres, disponibles, form_por_alquiler_id=None):
    form_por_alquiler_id = form_por_alquiler_id or {}
    for alquiler in alquileres:
        alquiler.edit_form = form_por_alquiler_id.get(
            alquiler.id,
            AlquilerEdicionForm(
                instance=alquiler,
                prefix=f"alq-edit-{alquiler.id}",
                disponibles=disponibles,
            ),
        )


def _hidden_field_pairs(data, keys):
    return [
        (key, value)
        for key in keys
        if (value := (data.get(key) or "").strip())
    ]


def _querystring_from_hidden_fields(hidden_fields):
    params = {key: value for key, value in hidden_fields if value}
    return urlencode(params)


def _panel_url(alquiler_id, panel_name, hidden_fields=None):
    url = reverse("alquileres:panel", args=[alquiler_id, panel_name])
    querystring = _querystring_from_hidden_fields(hidden_fields or [])
    if querystring:
        return f"{url}?{querystring}"
    return url


def _preparar_formulario_edicion(alquiler, disponibles, hidden_fields=None, edit_form=None):
    alquiler.edit_hidden_fields = list(hidden_fields or [])
    alquiler.edit_querystring = _querystring_from_hidden_fields(alquiler.edit_hidden_fields)
    alquiler.edit_panel_url = _panel_url(alquiler.id, "edit", alquiler.edit_hidden_fields)
    alquiler.edit_form = edit_form or AlquilerEdicionForm(
        instance=alquiler,
        prefix=f"alq-edit-{alquiler.id}",
        disponibles=disponibles,
    )


def _label_opcion_prenda(prenda: Prenda) -> str:
    return f"{prenda.codigo} - {prenda.color} {prenda.marca} talle {prenda.talle}".strip()


def _disponibles_payload(disponibles):
    payload = {}
    for short, prendas in disponibles.items():
        payload[short] = [
            {
                "value": prenda.codigo,
                "label": _label_opcion_prenda(prenda),
            }
            for prenda in prendas
        ]
    return payload


def _armar_mensaje_cliente(alq: Alquiler) -> str:
    items = list(alq.items.select_related("prenda").all())
    return _armar_mensaje_cliente_con_items(alq, items)


def _vincular_cliente(alquiler, dni):
    cliente = Cliente.objects.filter(dni=dni).first()
    recurrente = cliente is not None
    if cliente is None:
        try:
            with transaction.atomic():
                cliente = Cliente.objects.create(
                    dni=dni,
                    nombre=alquiler.cliente_nombre,
                    telefono=alquiler.cliente_telefono,
                )
        except IntegrityError:
            cliente = Cliente.objects.get(dni=dni)
            recurrente = True
    else:
        cambios = []
        if cliente.nombre != alquiler.cliente_nombre:
            cliente.nombre = alquiler.cliente_nombre
            cambios.append("nombre")
        if cliente.telefono != alquiler.cliente_telefono:
            cliente.telefono = alquiler.cliente_telefono
            cambios.append("telefono")
        if cambios:
            cambios.append("actualizado_en")
            cliente.save(update_fields=cambios)
    alquiler.cliente = cliente
    return recurrente


def _refresh_prenda_estado(prenda: Prenda):
    if prenda.estado in {Prenda.E_DAN, Prenda.E_LAV}:
        return

    activos = (
        AlquilerItem.objects
        .select_related("alquiler")
        .filter(
            prenda=prenda,
            alquiler__estado_alquiler__in=Alquiler.ESTADOS_ALQUILER_ACTIVOS,
        )
    )

    if activos.filter(alquiler__estado_alquiler=Alquiler.EST_ENTREGADO).exists():
        nuevo_estado = Prenda.E_ENT
    elif activos.exists():
        nuevo_estado = Prenda.E_RES
    else:
        nuevo_estado = Prenda.E_DISP

    if prenda.estado != nuevo_estado:
        prenda.estado = nuevo_estado
        prenda.save(update_fields=["estado"])


def _refresh_prendas_estado(prendas):
    vistos = set()
    for prenda in prendas:
        if not prenda or prenda.id in vistos:
            continue
        vistos.add(prenda.id)
        _refresh_prenda_estado(prenda)


def _refresh_prendas_estado_por_ids(prenda_ids):
    prendas = Prenda.objects.filter(id__in=set(prenda_ids))
    _refresh_prendas_estado(prendas)


def _actualizar_estado_operativo(
    alquiler: Alquiler,
    *,
    nuevo_estado: str = "",
    nuevo_saldo: str = "",
    metodo_saldo: str = "",
    auto_pagar_al_entregar: bool = False,
    auto_pagar_al_cerrar: bool = False,
    permitir_pago_sin_metodo: bool = False,
):
    saldo_editable = alquiler.saldo_contractual > 0
    changed = False
    auto_pago = False

    if nuevo_estado in dict(Alquiler.ESTADOS_ALQUILER):
        if auto_pagar_al_entregar and nuevo_estado == Alquiler.EST_ENTREGADO:
            if saldo_editable and not alquiler.esta_completamente_abonado:
                nuevo_saldo = Alquiler.SAL_PAG
                auto_pago = True
        if auto_pagar_al_cerrar and nuevo_estado == Alquiler.EST_CERRADO:
            if saldo_editable and not alquiler.esta_completamente_abonado:
                nuevo_saldo = Alquiler.SAL_PAG
                auto_pago = True

        if alquiler.estado_alquiler != nuevo_estado:
            alquiler.estado_alquiler = nuevo_estado
            changed = True

    if saldo_editable and nuevo_saldo in dict(Alquiler.ESTADOS_SALDO):
        if nuevo_saldo == Alquiler.SAL_PAG:
            if metodo_saldo and metodo_saldo not in dict(Alquiler.METODOS_PAGO):
                return False, "Metodo de pago invalido."

            requires_method = (
                alquiler.estado_saldo != Alquiler.SAL_PAG
                and not auto_pago
                and not permitir_pago_sin_metodo
                and not metodo_saldo
            )
            if requires_method:
                return False, "Para marcar saldo como pagado tienes que elegir el metodo de pago."

            if alquiler.marcar_completamente_abonado():
                changed = True

            if metodo_saldo and alquiler.metodo_saldo != metodo_saldo:
                alquiler.metodo_saldo = metodo_saldo
                changed = True

            if alquiler.saldo_pagado_en is None:
                alquiler.saldo_pagado_en = timezone.localdate()
                changed = True
        else:
            if alquiler.marcar_saldo_pendiente():
                changed = True

    return changed, ""


def _toggle_saldo_pagado(alquiler: Alquiler):
    if alquiler.saldo_contractual <= 0:
        return False, "", f"Saldo del alquiler #{alquiler.id} ya esta completo."

    if _estado_saldo_actual(alquiler) == Alquiler.SAL_PAG:
        return False, "", f"Saldo del alquiler #{alquiler.id} ya está abonado."

    changed, error = _actualizar_estado_operativo(
        alquiler,
        nuevo_saldo=Alquiler.SAL_PAG,
        permitir_pago_sin_metodo=True,
    )
    return changed, error, f"Saldo del alquiler #{alquiler.id} marcado como abonado."


def _procesar_accion_operativa(request, alquiler: Alquiler, accion: str) -> bool:
    estado_anterior = alquiler.estado_alquiler
    saldo_anterior = alquiler.estado_saldo
    importe_saldo_antes = alquiler.saldo_pendiente_actual
    changed = False
    error = ""
    success_message = ""

    if accion == "cerrar_alquiler":
        changed, error = _actualizar_estado_operativo(
            alquiler,
            nuevo_estado=Alquiler.EST_CERRADO,
            auto_pagar_al_cerrar=True,
        )
        success_message = f"Alquiler #{alquiler.id} cerrado."
    elif accion == "marcar_entregado":
        changed, error = _actualizar_estado_operativo(
            alquiler,
            nuevo_estado=Alquiler.EST_ENTREGADO,
            auto_pagar_al_entregar=True,
        )
        success_message = f"Alquiler #{alquiler.id} marcado como entregado."
    elif accion in {"marcar_saldo_pagado", "toggle_saldo_pagado"}:
        changed, error, success_message = _toggle_saldo_pagado(alquiler)
    elif accion == "cancelar_alquiler":
        changed, error = _actualizar_estado_operativo(
            alquiler,
            nuevo_estado=Alquiler.EST_CANCELADO,
        )
        success_message = f"Alquiler #{alquiler.id} cancelado."
    else:
        return False

    if error:
        messages.error(request, error)
    elif changed:
        alquiler.save()
        if alquiler.estado_saldo == Alquiler.SAL_PAG and saldo_anterior != Alquiler.SAL_PAG:
            registrar_saldo(alquiler, request.user)
        if alquiler.estado_alquiler == Alquiler.EST_CANCELADO and not alquiler.credito_cancelacion_generado:
            if alquiler.cliente_id and alquiler.sena > 0:
                cliente = Cliente.objects.get(pk=alquiler.cliente_id)
                cliente.saldo_a_favor += alquiler.sena
                cliente.save(update_fields=["saldo_a_favor"])
                alquiler.credito_cancelacion_generado = True
                alquiler.save(update_fields=["credito_cancelacion_generado"])
                registrar_movimiento(
                    clave=f"alquiler:{alquiler.pk}:credito-cancelacion",
                    concepto="Saldo transferido a favor del cliente",
                    referencia=f"Alquiler #{alquiler.pk}", cliente=cliente,
                    alquiler=alquiler, usuario=request.user, informativo=True,
                )
        _sync_prendas_por_estado(alquiler)
        if alquiler.estado_alquiler != estado_anterior:
            eventos = {
                Alquiler.EST_ENTREGADO: ("Marcó alquiler como entregado", Actividad.ENTREGA),
                Alquiler.EST_CERRADO: ("Marcó alquiler como devuelto/cerrado", Actividad.DEVOLUCION),
                Alquiler.EST_CANCELADO: ("Canceló alquiler", Actividad.ALQUILER),
            }
            if alquiler.estado_alquiler in eventos:
                nombre, categoria = eventos[alquiler.estado_alquiler]
                registrar_actividad(request, nombre, categoria, objeto=alquiler, referencia=f"Alquiler #{alquiler.id}")
        if alquiler.estado_saldo == Alquiler.SAL_PAG and saldo_anterior != Alquiler.SAL_PAG:
            registrar_actividad(request, "Marcó abonado restante", Actividad.PAGO, objeto=alquiler, referencia=f"Alquiler #{alquiler.id}", detalle=f"${importe_saldo_antes}")
        messages.success(request, success_message)
    else:
        messages.info(request, "No hubo cambios.")

    return True


def _crear_items_desde_seleccion(alquiler: Alquiler, selected_prendas):
    touched_prendas = []
    for who, prendas in (selected_prendas or {}).items():
        persona_num = int(str(who).replace("p", "") or 1)
        for data in prendas.values():
            prenda = data["prenda"]
            AlquilerItem.objects.create(
                alquiler=alquiler,
                persona_num=persona_num,
                prenda=prenda,
                ruedo_valor=data.get("ruedo_valor"),
                ruedo_tipo=data.get("ruedo_tipo") or "",
            )
            touched_prendas.append(prenda)
    return touched_prendas


def _sync_items_alquiler(alquiler: Alquiler, selected_prendas):
    existentes = {}
    duplicados = []

    for item in alquiler.items.select_related("prenda"):
        short = SHORT_POR_CATEGORIA.get(item.prenda.categoria)
        key = (item.persona_num, short)
        if not short:
            continue
        if key in existentes:
            duplicados.append(item)
            continue
        existentes[key] = item

    touched_ids = set()
    for who, prendas in (selected_prendas or {}).items():
        persona_num = int(str(who).replace("p", "") or 1)
        for short, data in prendas.items():
            key = (persona_num, short)
            prenda = data["prenda"]
            ruedo_valor = data.get("ruedo_valor")
            ruedo_tipo = data.get("ruedo_tipo") or ""
            touched_ids.add(prenda.id)

            item = existentes.pop(key, None)
            if item:
                changed_fields = []
                if item.prenda_id != prenda.id:
                    touched_ids.add(item.prenda_id)
                    item.prenda = prenda
                    changed_fields.append("prenda")
                if item.ruedo_valor != ruedo_valor:
                    item.ruedo_valor = ruedo_valor
                    changed_fields.append("ruedo_valor")
                if item.ruedo_tipo != ruedo_tipo:
                    item.ruedo_tipo = ruedo_tipo
                    changed_fields.append("ruedo_tipo")
                if changed_fields:
                    item.save(update_fields=changed_fields)
                continue

            AlquilerItem.objects.create(
                alquiler=alquiler,
                persona_num=persona_num,
                prenda=prenda,
                ruedo_valor=ruedo_valor,
                ruedo_tipo=ruedo_tipo,
            )

    for item in existentes.values():
        touched_ids.add(item.prenda_id)
        item.delete()

    for item in duplicados:
        touched_ids.add(item.prenda_id)
        item.delete()

    return touched_ids


def _disponibles_por_categoria():
    grouped = {short: [] for short in SHORT_POR_CATEGORIA.values()}
    prendas = (
        Prenda.objects
        .exclude(estado__in=[Prenda.E_DAN, Prenda.E_LAV])
        .order_by("categoria", "-creado_en", "-codigo")
    )
    for prenda in prendas:
        short = SHORT_POR_CATEGORIA.get(prenda.categoria)
        if short:
            grouped[short].append(prenda)
    return grouped


def crear(request):
    msg_cliente = request.session.pop("ultimo_mensaje_cliente", None)
    whatsapp_url = request.session.pop("ultimo_whatsapp_url", "")
    cliente_recurrente = request.session.pop("cliente_recurrente", False)
    disponibles = _disponibles_por_categoria()
    creation_token = request.session.get("alquiler_creation_token")
    if not creation_token:
        creation_token = secrets.token_urlsafe(24)
        request.session["alquiler_creation_token"] = creation_token

    if request.method == "POST":
        supplied_token = request.POST.get("creation_token", "")
        if supplied_token and supplied_token != creation_token:
            messages.info(request, "Ese alquiler ya fue procesado.")
            return redirect("alquileres:ver")
        form = AlquilerForm(request.POST, disponibles=disponibles)
        if form.is_valid():
            selected = form.cleaned_data.get(
                "_selected_prendas",
                {f"p{persona_num}": {} for persona_num in range(1, Alquiler.MAX_PERSONAS + 1)},
            )
            touched_prendas = []

            with transaction.atomic():
                alquiler = form.save(commit=False)
                alquiler.fecha_visita = alquiler.fecha_reserva
                alquiler.estado_alquiler = Alquiler.EST_RESERVADO
                alquiler.estado_saldo = Alquiler.SAL_PEND
                recurrente = _vincular_cliente(alquiler, form.cleaned_data["cliente_dni"])
                if form.cleaned_data.get("aplicar_saldo_a_favor"):
                    cliente = Cliente.objects.select_for_update().get(pk=alquiler.cliente_id)
                    credito = form.cleaned_data["monto_saldo_a_favor"]
                    if credito > cliente.saldo_a_favor:
                        raise IntegrityError("Saldo a favor insuficiente.")
                    cliente.saldo_a_favor -= credito
                    cliente.save(update_fields=["saldo_a_favor"])
                    alquiler.saldo_a_favor_aplicado = credito
                alquiler.save()
                registrar_sena(alquiler, request.user)
                if alquiler.saldo_a_favor_aplicado:
                    registrar_movimiento(
                        clave=f"alquiler:{alquiler.pk}:credito-aplicado",
                        concepto="Aplicación de saldo a favor", referencia=f"Alquiler #{alquiler.pk}",
                        usuario=request.user, alquiler=alquiler, cliente=alquiler.cliente,
                        informativo=True,
                    )
                    registrar_actividad(
                        request, "Aplicó saldo a favor", Actividad.PAGO, objeto=alquiler,
                        referencia=f"Alquiler #{alquiler.pk}",
                        detalle=f"${alquiler.saldo_a_favor_aplicado}",
                    )
                touched_prendas.extend(_crear_items_desde_seleccion(alquiler, selected))

                _refresh_prendas_estado(touched_prendas)
                request.session["ultimo_mensaje_cliente"] = _armar_mensaje_cliente(alquiler)
                request.session["ultimo_whatsapp_url"] = generar_enlace_whatsapp(alquiler.cliente_telefono, request.session["ultimo_mensaje_cliente"])
                request.session["cliente_recurrente"] = recurrente
                request.session.pop("alquiler_creation_token", None)

            registrar_actividad(request, "Creó alquiler", Actividad.ALQUILER, objeto=alquiler, referencia=f"Alquiler #{alquiler.id}", detalle=f"Seña: ${alquiler.sena}")

            messages.success(request, "Alquiler creado correctamente.")
            return redirect(f"{reverse('alquileres:ver')}?buscar={alquiler.id}")

        messages.error(request, "Revisa los campos del formulario.")
    else:
        hoy = timezone.localdate()
        form = AlquilerForm(
            disponibles=disponibles,
            initial={
                "fecha_reserva": hoy,
                "fecha_entrega": hoy,
                "fecha_devolucion": hoy,
            },
        )

    return render(request, "alquileres/crear.html", {
        "form": form,
        "mensaje_cliente": msg_cliente,
        "whatsapp_url": whatsapp_url,
        "cliente_recurrente": cliente_recurrente,
        "creation_token": creation_token,
    })


def _sync_prendas_por_estado(alquiler: Alquiler):
    prendas = [item.prenda for item in alquiler.items.select_related("prenda").all()]
    if alquiler.estado_alquiler == Alquiler.EST_CERRADO:
        for prenda in prendas:
            if prenda.estado != Prenda.E_DISP:
                prenda.estado = Prenda.E_DISP
                prenda.save(update_fields=["estado"])
        return
    _refresh_prendas_estado(prendas)


def _redirect_ver_con_filtros(request):
    params = {}
    for key in ["fecha_desde", "fecha_hasta"]:
        value = (request.POST.get(key) or "").strip()
        if value:
            params[key] = value

    url = reverse("alquileres:ver")
    if params:
        url = f"{url}?{urlencode(params)}"
    return redirect(url)


def _redirect_entregas_con_filtro(request):
    hasta = (request.POST.get("hasta") or "").strip()
    url = reverse("alquileres:entregas")
    if hasta:
        url = f"{url}?{urlencode({'hasta': hasta})}"
    return redirect(url)


def _contexto_ver_alquileres(data=None, form_por_alquiler_id=None, edit_open_id=None):
    disponibles = _disponibles_por_categoria()
    form_por_alquiler_id = form_por_alquiler_id or {}
    filtros_form = VerAlquileresFiltroForm(data or None)
    hoy = timezone.localdate()
    alquileres = (
        Alquiler.objects
        .all()
        .prefetch_related("items__prenda")
    )

    filtros_activos = False
    if filtros_form.is_bound and filtros_form.is_valid():
        fecha_desde = filtros_form.cleaned_data.get("fecha_desde")
        fecha_hasta = filtros_form.cleaned_data.get("fecha_hasta")

        if fecha_desde:
            alquileres = alquileres.filter(fecha_entrega__gte=fecha_desde)
            filtros_activos = True
        if fecha_hasta:
            alquileres = alquileres.filter(fecha_entrega__lte=fecha_hasta)
            filtros_activos = True
        buscar = (filtros_form.cleaned_data.get("buscar") or "").strip()
        if buscar:
            query = Q(cliente_nombre__icontains=buscar) | Q(cliente__dni__icontains=buscar)
            if buscar.isdigit():
                query |= Q(id=int(buscar))
            alquileres = alquileres.filter(query)
            filtros_activos = True

    alquileres = _ordenar_alquileres_por_entrega(list(alquileres), hoy)
    resumen = [
        {"label": "Activos", "valor": sum(1 for alquiler in alquileres if alquiler.estado_alquiler in Alquiler.ESTADOS_ALQUILER_ACTIVOS)},
        {"label": "Reservados", "valor": sum(1 for alquiler in alquileres if alquiler.estado_alquiler == Alquiler.EST_RESERVADO)},
        {"label": "Entregados", "valor": sum(1 for alquiler in alquileres if alquiler.estado_alquiler == Alquiler.EST_ENTREGADO)},
        {"label": "Finalizados", "valor": sum(1 for alquiler in alquileres if alquiler.estado_alquiler in Alquiler.ESTADOS_ALQUILER_FINALES)},
    ]
    _adjuntar_detalle_alquiler(alquileres)

    hidden_fields = _hidden_field_pairs({
        "fecha_desde": filtros_form["fecha_desde"].value() or "",
        "fecha_hasta": filtros_form["fecha_hasta"].value() or "",
    }, ["fecha_desde", "fecha_hasta"])

    alquileres_por_id = {}
    for alquiler in alquileres:
        alquiler.edit_panel_url = _panel_url(alquiler.id, "edit", hidden_fields)
        alquileres_por_id[alquiler.id] = alquiler

    if edit_open_id in alquileres_por_id:
        _preparar_formulario_edicion(
            alquileres_por_id[edit_open_id],
            disponibles,
            hidden_fields=hidden_fields,
            edit_form=form_por_alquiler_id.get(edit_open_id),
        )

    return {
        "alquileres": alquileres,
        "estados_alquiler": Alquiler.ESTADOS_ALQUILER,
        "estados_saldo": Alquiler.ESTADOS_SALDO,
        "metodos_pago": Alquiler.METODOS_PAGO,
        "resumen": resumen,
        "filtros_form": filtros_form,
        "filtros_activos": filtros_activos,
        "buscar": filtros_form["buscar"].value() or "",
        "edit_open_id": edit_open_id,
        "filter_hidden_fields": hidden_fields,
        "disponibles_json": _disponibles_payload(disponibles),
    }


def _contexto_entregas(data=None, form_por_alquiler_id=None, edit_open_id=None):
    disponibles = _disponibles_por_categoria()
    form_por_alquiler_id = form_por_alquiler_id or {}
    hoy = timezone.localdate()
    hasta_str = ""
    if data is not None:
        hasta_str = (data.get("hasta") or "").strip()

    try:
        if hasta_str:
            hasta = timezone.datetime.strptime(hasta_str, "%Y-%m-%d").date()
        else:
            hasta = hoy + timezone.timedelta(days=7)
    except Exception:
        hasta = hoy + timezone.timedelta(days=7)

    if hasta < hoy:
        hasta = hoy

    alquileres = (
        Alquiler.objects
        .filter(
            fecha_entrega__gte=hoy,
            fecha_entrega__lte=hasta,
            estado_alquiler__in=Alquiler.ESTADOS_ALQUILER_ACTIVOS,
        )
        .prefetch_related("items__prenda")
    )
    alquileres = _ordenar_alquileres_por_entrega(list(alquileres), hoy)
    _adjuntar_detalle_alquiler(alquileres)

    hidden_fields = _hidden_field_pairs({
        "hasta": hasta.strftime("%Y-%m-%d"),
    }, ["hasta"])

    alquileres_por_id = {}
    for alquiler in alquileres:
        alquiler.edit_panel_url = _panel_url(alquiler.id, "edit", hidden_fields)
        alquiler.detail_panel_url = _panel_url(alquiler.id, "detalle")
        alquileres_por_id[alquiler.id] = alquiler

    if edit_open_id in alquileres_por_id:
        _preparar_formulario_edicion(
            alquileres_por_id[edit_open_id],
            disponibles,
            hidden_fields=hidden_fields,
            edit_form=form_por_alquiler_id.get(edit_open_id),
        )

    return {
        "hoy": hoy,
        "hasta": hasta,
        "alquileres": alquileres,
        "estados_alquiler": Alquiler.ESTADOS_ALQUILER,
        "estados_saldo": Alquiler.ESTADOS_SALDO,
        "metodos_pago": Alquiler.METODOS_PAGO,
        "edit_open_id": edit_open_id,
        "filter_hidden_fields": hidden_fields,
        "disponibles_json": _disponibles_payload(disponibles),
    }


def ruedos(request):
    if request.method == "POST":
        item = get_object_or_404(AlquilerItem.objects.select_related("prenda"), pk=request.POST.get("item_id"))
        if item.ruedo_valor and not item.ruedo_listo:
            item.ruedo_listo = True
            item.ruedo_listo_en = timezone.now()
            item.ruedo_listo_por = request.user
            item.save(update_fields=["ruedo_listo", "ruedo_listo_en", "ruedo_listo_por"])
            registrar_actividad(request, f"Marcó listo el ruedo de {item.prenda.codigo}",
                                Actividad.STOCK, objeto=item, referencia=item.prenda.codigo)
            messages.success(request, "Ruedo marcado como listo.")
        return redirect(f"{reverse('alquileres:ruedos')}?semana={request.POST.get('semana', '')}&estado={request.POST.get('estado', 'pendientes')}")
    hoy = timezone.localdate()
    semana_actual = _start_of_week(hoy)
    semana_inicio = _parse_week_value(request.GET.get("semana"), semana_actual)
    semana_fin = semana_inicio + timedelta(days=6)
    estado_ruedo = request.GET.get("estado", "pendientes")

    items_qs = (
        AlquilerItem.objects
        .select_related("alquiler", "prenda")
        .filter(
            alquiler__fecha_entrega__gte=semana_inicio,
            alquiler__fecha_entrega__lte=semana_fin,
            ruedo_valor__gt=0,
        )
        .order_by(
            "alquiler__fecha_entrega",
            "alquiler__cliente_nombre",
            "persona_num",
            "prenda__codigo",
        )
    )
    if estado_ruedo == "pendientes":
        items_qs = items_qs.filter(ruedo_listo=False)
    elif estado_ruedo == "listos":
        items_qs = items_qs.filter(ruedo_listo=True)
    items = list(items_qs)

    ruedos_items = []
    for item in items:
        alquiler = item.alquiler
        prenda = item.prenda
        persona_nombre = _persona_nombre_alquiler(alquiler, item.persona_num)
        fecha_a_hacer = alquiler.fecha_entrega - timedelta(days=1)
        mensaje_linea = f"{_detalle_prenda_ruedo_mensaje(prenda)}, {_texto_ruedo_mensaje(item)}".strip()

        ruedos_items.append({
            "id": item.id,
            "listo": item.ruedo_listo,
            "listo_en": item.ruedo_listo_en,
            "fecha_retiro": alquiler.fecha_entrega,
            "fecha_a_hacer": fecha_a_hacer,
            "cliente_nombre": alquiler.cliente_nombre,
            "persona_nombre": persona_nombre or f"Persona {item.persona_num}",
            "codigo": prenda.codigo,
            "detalle": _detalle_prenda_ruedo_tabla(prenda),
            "ruedo": _texto_ruedo(item) or "-",
            "mensaje_linea": mensaje_linea,
        })

    mensaje_ruedos = _armar_mensaje_ruedos(ruedos_items)

    return render(request, "alquileres/ruedos.html", {
        "hoy": hoy,
        "semana_inicio": semana_inicio,
        "semana_fin": semana_fin,
        "semana_value": _week_value(semana_inicio),
        "semana_anterior": _week_value(semana_inicio - timedelta(days=7)),
        "semana_siguiente": _week_value(semana_inicio + timedelta(days=7)),
        "semana_actual": _week_value(semana_actual),
        "estado_ruedo": estado_ruedo,
        "ruedos_items": ruedos_items,
        "mensaje_ruedos": mensaje_ruedos,
        "resumen_ruedos": [
            {"label": "Prendas con ruedo", "value": len(ruedos_items)},
            {"label": "Clientes", "value": len({item["cliente_nombre"] for item in ruedos_items})},
            {"label": "Fechas a hacer", "value": len({item["fecha_a_hacer"] for item in ruedos_items})},
        ],
    })


def panel(request, alquiler_id, panel_name):
    alquiler = get_object_or_404(
        Alquiler.objects.prefetch_related("items__prenda"),
        id=alquiler_id,
    )

    if panel_name == "edit":
        disponibles = _disponibles_por_categoria()
        hidden_fields = _hidden_field_pairs(request.GET, ["fecha_desde", "fecha_hasta", "hasta"])
        _preparar_formulario_edicion(alquiler, disponibles, hidden_fields=hidden_fields)
        return render(request, "alquileres/_editar_alquiler.html", {
            "alquiler": alquiler,
        })

    if panel_name == "detalle":
        _adjuntar_detalle_alquiler([alquiler])
        return render(request, "alquileres/_detalle_personas.html", {
            "alquiler": alquiler,
        })

    raise Http404("Panel inexistente")


def ver(request):
    if request.method == "POST":
        alquiler_id = request.POST.get("alq_id")
        alquiler = get_object_or_404(Alquiler, id=alquiler_id)
        accion = request.POST.get("accion", "actualizar")

        if accion == "eliminar":
            with transaction.atomic():
                prenda_ids = list(alquiler.items.values_list("prenda_id", flat=True))
                alquiler.delete()
                _refresh_prendas_estado_por_ids(prenda_ids)
            messages.success(request, f"Alquiler #{alquiler_id} eliminado.")
            registrar_actividad(request, "Canceló/eliminó alquiler", Actividad.ALQUILER, referencia=f"Alquiler #{alquiler_id}")
            return _redirect_ver_con_filtros(request)

        if accion == "editar":
            disponibles = _disponibles_por_categoria()
            edit_form = AlquilerEdicionForm(
                request.POST,
                instance=alquiler,
                prefix=f"alq-edit-{alquiler.id}",
                disponibles=disponibles,
            )
            if edit_form.is_valid():
                with transaction.atomic():
                    alquiler = edit_form.save()
                    sincronizar_movimientos_alquiler(alquiler, request.user)
                    dni = edit_form.cleaned_data.get("cliente_dni")
                    if dni:
                        _vincular_cliente(alquiler, dni)
                        alquiler.save(update_fields=["cliente"])
                    touched_ids = _sync_items_alquiler(
                        alquiler,
                        edit_form.cleaned_data.get("_selected_prendas"),
                    )
                    _refresh_prendas_estado_por_ids(touched_ids)
                messages.success(request, f"Alquiler #{alquiler.id} editado.")
                registrar_actividad(request, "Modificó alquiler", Actividad.ALQUILER, objeto=alquiler, referencia=f"Alquiler #{alquiler.id}")
                return _redirect_ver_con_filtros(request)

            messages.error(request, "Revisa los datos del alquiler antes de guardar.")
            return render(
                request,
                "alquileres/ver.html",
                _contexto_ver_alquileres(
                    request.POST,
                    form_por_alquiler_id={alquiler.id: edit_form},
                    edit_open_id=alquiler.id,
                ),
            )

        if _procesar_accion_operativa(request, alquiler, accion):
            return _redirect_ver_con_filtros(request)

        changed, error = _actualizar_estado_operativo(
            alquiler,
            nuevo_estado=request.POST.get("estado_alquiler", ""),
            nuevo_saldo=request.POST.get("estado_saldo", ""),
            metodo_saldo=(request.POST.get("metodo_saldo") or "").strip(),
            auto_pagar_al_entregar=True,
            auto_pagar_al_cerrar=True,
        )
        if error:
            messages.error(request, error)
            return _redirect_ver_con_filtros(request)

        if changed:
            alquiler.save()
            _sync_prendas_por_estado(alquiler)
            messages.success(request, f"Alquiler #{alquiler.id} actualizado.")
            registrar_actividad(request, "Modificó alquiler", Actividad.ALQUILER, objeto=alquiler, referencia=f"Alquiler #{alquiler.id}")
        else:
            messages.info(request, "No hubo cambios.")

        return _redirect_ver_con_filtros(request)

    return render(request, "alquileres/ver.html", _contexto_ver_alquileres(request.GET or None))


def entregas(request):
    if request.method == "POST":
        alquiler_id = request.POST.get("alq_id")
        alquiler = get_object_or_404(Alquiler, id=alquiler_id)
        accion = request.POST.get("accion", "editar")

        if accion == "eliminar":
            with transaction.atomic():
                prenda_ids = list(alquiler.items.values_list("prenda_id", flat=True))
                alquiler.delete()
                _refresh_prendas_estado_por_ids(prenda_ids)
            messages.success(request, f"Alquiler #{alquiler_id} eliminado.")
            registrar_actividad(request, "Canceló/eliminó alquiler", Actividad.ALQUILER, referencia=f"Alquiler #{alquiler_id}")
            return _redirect_entregas_con_filtro(request)

        if accion == "editar":
            disponibles = _disponibles_por_categoria()
            edit_form = AlquilerEdicionForm(
                request.POST,
                instance=alquiler,
                prefix=f"alq-edit-{alquiler.id}",
                disponibles=disponibles,
            )
            if edit_form.is_valid():
                with transaction.atomic():
                    alquiler = edit_form.save()
                    sincronizar_movimientos_alquiler(alquiler, request.user)
                    dni = edit_form.cleaned_data.get("cliente_dni")
                    if dni:
                        _vincular_cliente(alquiler, dni)
                        alquiler.save(update_fields=["cliente"])
                    touched_ids = _sync_items_alquiler(
                        alquiler,
                        edit_form.cleaned_data.get("_selected_prendas"),
                    )
                    _refresh_prendas_estado_por_ids(touched_ids)
                messages.success(request, f"Alquiler #{alquiler.id} editado.")
                registrar_actividad(request, "Modificó alquiler", Actividad.ALQUILER, objeto=alquiler, referencia=f"Alquiler #{alquiler.id}")
                return _redirect_entregas_con_filtro(request)

            messages.error(request, "Revisa los datos del alquiler antes de guardar.")
            return render(
                request,
                "alquileres/entregas.html",
                _contexto_entregas(
                    request.POST,
                    form_por_alquiler_id={alquiler.id: edit_form},
                    edit_open_id=alquiler.id,
                ),
            )

        if _procesar_accion_operativa(request, alquiler, accion):
            return _redirect_entregas_con_filtro(request)

    return render(request, "alquileres/entregas.html", _contexto_entregas(request.GET or None))


def retrasados(request):
    hoy = timezone.localdate()

    if request.method == "POST":
        alquiler_id = request.POST.get("alq_id")
        alquiler = get_object_or_404(Alquiler, id=alquiler_id)
        accion = request.POST.get("accion", "")

        if _procesar_accion_operativa(request, alquiler, accion):
            return redirect("alquileres:retrasados")

    alquileres = list(
        Alquiler.objects
        .filter(
            fecha_devolucion__lt=hoy,
            estado_alquiler__in=Alquiler.ESTADOS_ALQUILER_ACTIVOS,
        )
        .order_by("fecha_devolucion", "fecha_entrega", "id")
        .prefetch_related("items__prenda")
    )
    _adjuntar_detalle_alquiler(alquileres)

    retrasos = []
    for alquiler in alquileres:
        dias = (hoy - alquiler.fecha_devolucion).days
        retrasos.append((alquiler, dias))

    return render(request, "alquileres/retrasados.html", {
        "hoy": hoy,
        "retrasos": retrasos,
    })


def clientes(request):
    query = (request.GET.get("q") or "").strip()
    qs = Cliente.objects.annotate(total_alquileres=Count("alquileres")).order_by("nombre", "dni")
    if query:
        qs = qs.filter(Q(nombre__icontains=query) | Q(dni__icontains=query))
    return render(request, "alquileres/clientes.html", {"clientes": qs, "query": query})


def cliente_detalle(request, pk):
    cliente = get_object_or_404(Cliente, pk=pk)
    alquileres = list(cliente.alquileres.prefetch_related("items__prenda").order_by("-fecha_reserva", "-id"))
    _adjuntar_detalle_alquiler(alquileres)
    return render(request, "alquileres/cliente_detalle.html", {"cliente": cliente, "alquileres": alquileres})


def cliente_por_dni(request):
    dni = "".join(c for c in request.GET.get("dni", "") if c.isdigit())
    cliente = Cliente.objects.filter(dni=dni).first()
    if not cliente:
        return JsonResponse({"encontrado": False})
    return JsonResponse({
        "encontrado": True, "nombre": cliente.nombre, "telefono": cliente.telefono,
        "saldo_a_favor": str(cliente.saldo_a_favor),
        "recurrente": cliente.alquileres.exists(),
    })
