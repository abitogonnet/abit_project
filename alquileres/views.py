from urllib.parse import urlencode

from django.contrib import messages
from django.db import transaction
from django.urls import reverse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from prendas.models import Prenda

from .forms import AlquilerEdicionForm, AlquilerForm, VerAlquileresFiltroForm
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
                    "categoria": prenda.get_categoria_display(),
                    "codigo": prenda.codigo,
                    "marca": prenda.marca or "-",
                    "color": prenda.color or "-",
                    "talle": prenda.talle or "-",
                    "ruedo": _texto_ruedo(item) or "Sin ruedo",
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


def _adjuntar_formularios_edicion(alquileres, form_por_alquiler_id=None):
    form_por_alquiler_id = form_por_alquiler_id or {}
    for alquiler in alquileres:
        alquiler.edit_form = form_por_alquiler_id.get(
            alquiler.id,
            AlquilerEdicionForm(instance=alquiler, prefix=f"alq-edit-{alquiler.id}"),
        )


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


def _disponibles_por_categoria():
    return {
        "saco": list(Prenda.objects.filter(categoria=Prenda.C_SACO).exclude(estado=Prenda.E_DAN).order_by("-creado_en", "-codigo")),
        "pantalon": list(Prenda.objects.filter(categoria=Prenda.C_PANTALON).exclude(estado=Prenda.E_DAN).order_by("-creado_en", "-codigo")),
        "camisa": list(Prenda.objects.filter(categoria=Prenda.C_CAMISA).exclude(estado=Prenda.E_DAN).order_by("-creado_en", "-codigo")),
        "chaleco": list(Prenda.objects.filter(categoria=Prenda.C_CHALECO).exclude(estado=Prenda.E_DAN).order_by("-creado_en", "-codigo")),
        "mono": list(Prenda.objects.filter(categoria=Prenda.C_MONO).exclude(estado=Prenda.E_DAN).order_by("-creado_en", "-codigo")),
        "corbata": list(Prenda.objects.filter(categoria=Prenda.C_CORBATA).exclude(estado=Prenda.E_DAN).order_by("-creado_en", "-codigo")),
        "zapatos": list(Prenda.objects.filter(categoria=Prenda.C_ZAPATOS).exclude(estado=Prenda.E_DAN).order_by("-creado_en", "-codigo")),
        "cinturon": list(Prenda.objects.filter(categoria=Prenda.C_CINTURON).exclude(estado=Prenda.E_DAN).order_by("-creado_en", "-codigo")),
    }


def crear(request):
    msg_cliente = request.session.pop("ultimo_mensaje_cliente", None)
    disponibles = _disponibles_por_categoria()

    if request.method == "POST":
        form = AlquilerForm(request.POST, disponibles=disponibles)
        if form.is_valid():
            selected = form.cleaned_data.get("_selected_prendas", {"p1": [], "p2": []})
            touched_prendas = []

            with transaction.atomic():
                alquiler = form.save(commit=False)
                alquiler.fecha_visita = alquiler.fecha_reserva
                alquiler.estado_alquiler = Alquiler.EST_RESERVADO
                alquiler.estado_saldo = Alquiler.SAL_PEND
                alquiler.save()

                p1_rp_val = form.cleaned_data.get("p1_ruedo_pantalon_valor")
                p1_rp_tipo = form.cleaned_data.get("p1_ruedo_pantalon_tipo") or ""
                p1_rs_val = form.cleaned_data.get("p1_ruedo_saco_valor")
                p1_rs_tipo = form.cleaned_data.get("p1_ruedo_saco_tipo") or ""

                for prenda in selected["p1"]:
                    if prenda.categoria == Prenda.C_PANTALON:
                        ruedo_valor, ruedo_tipo = p1_rp_val, p1_rp_tipo
                    elif prenda.categoria == Prenda.C_SACO:
                        ruedo_valor, ruedo_tipo = p1_rs_val, p1_rs_tipo
                    else:
                        ruedo_valor, ruedo_tipo = None, ""

                    AlquilerItem.objects.create(
                        alquiler=alquiler,
                        persona_num=1,
                        prenda=prenda,
                        ruedo_valor=ruedo_valor,
                        ruedo_tipo=ruedo_tipo,
                    )
                    touched_prendas.append(prenda)

                p2_rp_val = form.cleaned_data.get("p2_ruedo_pantalon_valor")
                p2_rp_tipo = form.cleaned_data.get("p2_ruedo_pantalon_tipo") or ""
                p2_rs_val = form.cleaned_data.get("p2_ruedo_saco_valor")
                p2_rs_tipo = form.cleaned_data.get("p2_ruedo_saco_tipo") or ""

                if (alquiler.persona2_nombre or "").strip() or selected["p2"]:
                    for prenda in selected["p2"]:
                        if prenda.categoria == Prenda.C_PANTALON:
                            ruedo_valor, ruedo_tipo = p2_rp_val, p2_rp_tipo
                        elif prenda.categoria == Prenda.C_SACO:
                            ruedo_valor, ruedo_tipo = p2_rs_val, p2_rs_tipo
                        else:
                            ruedo_valor, ruedo_tipo = None, ""

                        AlquilerItem.objects.create(
                            alquiler=alquiler,
                            persona_num=2,
                            prenda=prenda,
                            ruedo_valor=ruedo_valor,
                            ruedo_tipo=ruedo_tipo,
                        )
                        touched_prendas.append(prenda)

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
    filtros_form = VerAlquileresFiltroForm(data or None)
    alquileres = (
        Alquiler.objects
        .all()
        .order_by("-fecha_entrega", "-fecha_devolucion", "-id")
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

    resumen = [
        {"label": "Activos", "valor": alquileres.exclude(estado_alquiler=Alquiler.EST_CERRADO).count()},
        {"label": "Reservados", "valor": alquileres.filter(estado_alquiler=Alquiler.EST_RESERVADO).count()},
        {"label": "Entregados", "valor": alquileres.filter(estado_alquiler=Alquiler.EST_ENTREGADO).count()},
        {"label": "Cerrados", "valor": alquileres.filter(estado_alquiler=Alquiler.EST_CERRADO).count()},
    ]

    alquileres = list(alquileres)
    _adjuntar_detalle_alquiler(alquileres)
    _adjuntar_formularios_edicion(alquileres, form_por_alquiler_id=form_por_alquiler_id)

    fecha_desde_valor = filtros_form["fecha_desde"].value() or ""
    fecha_hasta_valor = filtros_form["fecha_hasta"].value() or ""
    for alquiler in alquileres:
        alquiler.edit_hidden_fields = [
            ("fecha_desde", fecha_desde_valor),
            ("fecha_hasta", fecha_hasta_valor),
        ]

    return {
        "alquileres": alquileres,
        "estados_alquiler": Alquiler.ESTADOS_ALQUILER,
        "estados_saldo": Alquiler.ESTADOS_SALDO,
        "metodos_pago": Alquiler.METODOS_PAGO,
        "resumen": resumen,
        "filtros_form": filtros_form,
        "filtros_activos": filtros_activos,
        "edit_open_id": edit_open_id,
    }


def _contexto_entregas(data=None, form_por_alquiler_id=None, edit_open_id=None):
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
    _adjuntar_formularios_edicion(alquileres, form_por_alquiler_id=form_por_alquiler_id)

    hasta_valor = hasta.strftime("%Y-%m-%d")
    for alquiler in alquileres:
        alquiler.edit_hidden_fields = [("hasta", hasta_valor)]

    return {
        "hoy": hoy,
        "hasta": hasta,
        "alquileres": alquileres,
        "edit_open_id": edit_open_id,
    }


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
            edit_form = AlquilerEdicionForm(
                request.POST,
                instance=alquiler,
                prefix=f"alq-edit-{alquiler.id}",
            )
            if edit_form.is_valid():
                edit_form.save()
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

        changed = False

        if nuevo_saldo in dict(Alquiler.ESTADOS_SALDO):
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
            edit_form = AlquilerEdicionForm(
                request.POST,
                instance=alquiler,
                prefix=f"alq-edit-{alquiler.id}",
            )
            if edit_form.is_valid():
                edit_form.save()
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
