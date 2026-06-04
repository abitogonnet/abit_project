from decimal import Decimal
from urllib.parse import urlencode

from django.contrib import messages
from django.db import transaction
from django.http import Http404
from django.urls import reverse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from prendas.models import Prenda

from .forms import AlquilerEdicionForm, AlquilerForm, SHORT_POR_CATEGORIA, VerAlquileresFiltroForm
from .models import Alquiler, AlquilerItem


def home(request):
    return render(request, "alquileres/home.html")


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
        partes.append(str(item.ruedo_valor))
    if item.ruedo_tipo:
        partes.append(item.get_ruedo_tipo_display())
    return " ".join(partes)


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
    return "secondary"


def _saldo_restante_actual(alquiler: Alquiler) -> Decimal:
    if alquiler.saldo <= 0 or alquiler.estado_saldo == Alquiler.SAL_PAG:
        return Decimal("0.00")
    return alquiler.saldo


def _estado_saldo_actual(alquiler: Alquiler) -> str:
    if alquiler.saldo <= 0:
        return Alquiler.SAL_PAG
    return alquiler.estado_saldo


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


def _adjuntar_detalle_alquiler(alquileres):
    for alquiler in alquileres:
        items = list(alquiler.items.all())
        personas = []

        for persona_num, persona_nombre in (
            (1, alquiler.persona1_nombre),
            (2, alquiler.persona2_nombre),
        ):
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
                        "persona": persona["nombre"],
                        "ruedo": item["ruedo"],
                    })
                if item["categoria_key"] == Prenda.C_PANTALON:
                    alquiler.ruedos_tabla["pantalon"].append({
                        "persona": persona["nombre"],
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
    partes = []
    partes.append("Hola, te mando el detallado de lo que alquilaste:")
    partes.append("")
    partes.append("FECHAS")
    partes.append(f"- Reserva: {_fmt_date(alq.fecha_reserva)}")
    partes.append(f"- Entrega: {_fmt_date(alq.fecha_entrega)}")
    partes.append(f"- Devolucion: {_fmt_date(alq.fecha_devolucion)}")
    partes.append("")

    partes.append(f"{alq.persona1_nombre}")
    for item in alq.items.filter(persona_num=1).select_related("prenda"):
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

    if (alq.persona2_nombre or "").strip():
        partes.append(f"{alq.persona2_nombre}")
        for item in alq.items.filter(persona_num=2).select_related("prenda"):
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
    partes.append(f"- Resta: ${alq.saldo}")

    return "\n".join(partes)


def _refresh_prenda_estado(prenda: Prenda):
    if prenda.estado == Prenda.E_DAN:
        return

    activos = (
        AlquilerItem.objects
        .select_related("alquiler")
        .filter(
            prenda=prenda,
            alquiler__estado_alquiler__in=[Alquiler.EST_RESERVADO, Alquiler.EST_ENTREGADO],
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


def _crear_items_desde_seleccion(alquiler: Alquiler, selected_prendas):
    touched_prendas = []
    for who, prendas in (selected_prendas or {}).items():
        persona_num = 1 if who == "p1" else 2
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
        persona_num = 1 if who == "p1" else 2
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
        .exclude(estado=Prenda.E_DAN)
        .order_by("categoria", "-creado_en", "-codigo")
    )
    for prenda in prendas:
        short = SHORT_POR_CATEGORIA.get(prenda.categoria)
        if short:
            grouped[short].append(prenda)
    return grouped


def crear(request):
    msg_cliente = request.session.pop("ultimo_mensaje_cliente", None)
    disponibles = _disponibles_por_categoria()

    if request.method == "POST":
        form = AlquilerForm(request.POST, disponibles=disponibles)
        if form.is_valid():
            selected = form.cleaned_data.get("_selected_prendas", {"p1": {}, "p2": {}})
            touched_prendas = []

            with transaction.atomic():
                alquiler = form.save(commit=False)
                alquiler.fecha_visita = alquiler.fecha_reserva
                alquiler.estado_alquiler = Alquiler.EST_RESERVADO
                alquiler.estado_saldo = Alquiler.SAL_PEND
                alquiler.save()
                touched_prendas.extend(_crear_items_desde_seleccion(alquiler, selected))

                _refresh_prendas_estado(touched_prendas)
                request.session["ultimo_mensaje_cliente"] = _armar_mensaje_cliente(alquiler)

            messages.success(request, "Alquiler creado. Copia el mensaje para el cliente.")
            return redirect("alquileres:crear")

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
    })


def _sync_prendas_por_estado(alquiler: Alquiler):
    _refresh_prendas_estado(item.prenda for item in alquiler.items.select_related("prenda").all())


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
    alquileres = (
        Alquiler.objects
        .all()
        .order_by("-creado_en", "-id")
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

    alquileres = list(alquileres)
    resumen = [
        {"label": "Activos", "valor": sum(1 for alquiler in alquileres if alquiler.estado_alquiler != Alquiler.EST_CERRADO)},
        {"label": "Reservados", "valor": sum(1 for alquiler in alquileres if alquiler.estado_alquiler == Alquiler.EST_RESERVADO)},
        {"label": "Entregados", "valor": sum(1 for alquiler in alquileres if alquiler.estado_alquiler == Alquiler.EST_ENTREGADO)},
        {"label": "Cerrados", "valor": sum(1 for alquiler in alquileres if alquiler.estado_alquiler == Alquiler.EST_CERRADO)},
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
        "edit_open_id": edit_open_id,
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
        .filter(fecha_entrega__gte=hoy, fecha_entrega__lte=hasta)
        .order_by("fecha_entrega", "fecha_devolucion", "id")
        .prefetch_related("items__prenda")
    )
    alquileres = list(alquileres)
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
        "edit_open_id": edit_open_id,
        "disponibles_json": _disponibles_payload(disponibles),
    }


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
                    touched_ids = _sync_items_alquiler(
                        alquiler,
                        edit_form.cleaned_data.get("_selected_prendas"),
                    )
                    _refresh_prendas_estado_por_ids(touched_ids)
                messages.success(request, f"Alquiler #{alquiler.id} editado.")
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

        nuevo_saldo = request.POST.get("estado_saldo")
        nuevo_estado = request.POST.get("estado_alquiler")
        metodo_saldo = (request.POST.get("metodo_saldo") or "").strip()
        saldo_editable = alquiler.saldo > 0

        changed = False

        if saldo_editable and nuevo_saldo in dict(Alquiler.ESTADOS_SALDO):
            if alquiler.estado_saldo != nuevo_saldo:
                if nuevo_saldo == Alquiler.SAL_PAG:
                    if not metodo_saldo:
                        messages.error(request, "Para marcar saldo como pagado tienes que elegir el metodo de pago.")
                        return _redirect_ver_con_filtros(request)
                    if metodo_saldo not in dict(Alquiler.METODOS_PAGO):
                        messages.error(request, "Metodo de pago invalido.")
                        return _redirect_ver_con_filtros(request)

                    alquiler.metodo_saldo = metodo_saldo
                    alquiler.saldo_pagado_en = timezone.localdate()
                else:
                    alquiler.metodo_saldo = ""
                    alquiler.saldo_pagado_en = None

                alquiler.estado_saldo = nuevo_saldo
                changed = True

        if nuevo_estado in dict(Alquiler.ESTADOS_ALQUILER):
            if alquiler.estado_alquiler != nuevo_estado:
                alquiler.estado_alquiler = nuevo_estado
                changed = True

        if changed:
            alquiler.save()
            _sync_prendas_por_estado(alquiler)
            messages.success(request, f"Alquiler #{alquiler.id} actualizado.")
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
                    touched_ids = _sync_items_alquiler(
                        alquiler,
                        edit_form.cleaned_data.get("_selected_prendas"),
                    )
                    _refresh_prendas_estado_por_ids(touched_ids)
                messages.success(request, f"Alquiler #{alquiler.id} editado.")
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

    return render(request, "alquileres/entregas.html", _contexto_entregas(request.GET or None))


def retrasados(request):
    hoy = timezone.localdate()

    alquileres = (
        Alquiler.objects
        .exclude(estado_alquiler=Alquiler.EST_CERRADO)
        .filter(fecha_devolucion__lt=hoy)
        .order_by("fecha_devolucion", "fecha_entrega", "id")
        .prefetch_related("items__prenda")
    )

    retrasos = []
    for alquiler in alquileres:
        dias = (hoy - alquiler.fecha_devolucion).days
        retrasos.append((alquiler, dias))

    return render(request, "alquileres/retrasados.html", {
        "hoy": hoy,
        "retrasos": retrasos,
    })
