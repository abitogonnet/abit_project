from django.contrib import messages
from django.db import transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from prendas.models import Prenda
from .models import Alquiler, AlquilerItem
from .forms import AlquilerForm


def home(request):
    return render(request, "alquileres/home.html")


def _fmt_date(d):
    if not d:
        return ""
    return d.strftime("%d/%m/%Y")


def _armar_mensaje_cliente(alq: Alquiler) -> str:
    partes = []
    partes.append("FECHAS")
    partes.append(f"- Visita: {_fmt_date(alq.fecha_visita)}")
    partes.append(f"- Reserva: {_fmt_date(alq.fecha_reserva)}")
    partes.append(f"- Entrega: {_fmt_date(alq.fecha_entrega)}")
    partes.append(f"- Devolución: {_fmt_date(alq.fecha_devolucion)}")
    partes.append("")

    partes.append(f"{alq.persona1_nombre}")
    for it in alq.items.filter(persona_num=1).select_related("prenda"):
        p = it.prenda
        extra_ruedo = ""
        if it.ruedo_valor and it.ruedo_tipo:
            extra_ruedo = f" (Ruedo: {it.ruedo_valor} {it.get_ruedo_tipo_display()})"
        partes.append(f"- {p.get_categoria_display()}: {p.color} {p.marca} talle {p.talle} [{p.codigo}]{extra_ruedo}")
    partes.append("")

    if (alq.persona2_nombre or "").strip():
        partes.append(f"{alq.persona2_nombre}")
        for it in alq.items.filter(persona_num=2).select_related("prenda"):
            p = it.prenda
            extra_ruedo = ""
            if it.ruedo_valor and it.ruedo_tipo:
                extra_ruedo = f" (Ruedo: {it.ruedo_valor} {it.get_ruedo_tipo_display()})"
            partes.append(f"- {p.get_categoria_display()}: {p.color} {p.marca} talle {p.talle} [{p.codigo}]{extra_ruedo}")
        partes.append("")

    partes.append("PAGO")
    partes.append(f"- Total: ${alq.total_bruto}")
    if alq.descuento_pct and alq.descuento_pct > 0:
        partes.append(f"- Descuento: {alq.descuento_pct}% ( -${alq.descuento_monto} )")
        partes.append(f"- Total final: ${alq.total_final}")
    else:
        partes.append(f"- Total final: ${alq.total_final}")
    partes.append(f"- Seña: ${alq.sena}")
    partes.append(f"- Resta: ${alq.saldo}")

    return "\n".join(partes)


def crear(request):
    msg_cliente = request.session.pop("ultimo_mensaje_cliente", None)

    disp = {
        "saco": list(Prenda.objects.filter(categoria=Prenda.C_SACO, estado=Prenda.E_DISP).order_by("codigo")),
        "pantalon": list(Prenda.objects.filter(categoria=Prenda.C_PANTALON, estado=Prenda.E_DISP).order_by("codigo")),
        "camisa": list(Prenda.objects.filter(categoria=Prenda.C_CAMISA, estado=Prenda.E_DISP).order_by("codigo")),
        "chaleco": list(Prenda.objects.filter(categoria=Prenda.C_CHALECO, estado=Prenda.E_DISP).order_by("codigo")),
        "mono": list(Prenda.objects.filter(categoria=Prenda.C_MONO, estado=Prenda.E_DISP).order_by("codigo")),
        "corbata": list(Prenda.objects.filter(categoria=Prenda.C_CORBATA, estado=Prenda.E_DISP).order_by("codigo")),
        "zapatos": list(Prenda.objects.filter(categoria=Prenda.C_ZAPATOS, estado=Prenda.E_DISP).order_by("codigo")),
        "cinturon": list(Prenda.objects.filter(categoria=Prenda.C_CINTURON, estado=Prenda.E_DISP).order_by("codigo")),
    }

    if request.method == "POST":
        form = AlquilerForm(request.POST)
        if form.is_valid():
            selected = form.cleaned_data.get("_selected_prendas", {"p1": [], "p2": []})

            with transaction.atomic():
                alq = form.save(commit=False)
                alq.estado_alquiler = Alquiler.EST_RESERVADO
                alq.estado_saldo = Alquiler.SAL_PEND
                alq.save()

                # ✅ ruedos separados P1
                p1_rp_val = form.cleaned_data.get("p1_ruedo_pantalon_valor")
                p1_rp_tipo = form.cleaned_data.get("p1_ruedo_pantalon_tipo") or ""
                p1_rs_val = form.cleaned_data.get("p1_ruedo_saco_valor")
                p1_rs_tipo = form.cleaned_data.get("p1_ruedo_saco_tipo") or ""

                for pr in selected["p1"]:
                    if pr.categoria == Prenda.C_PANTALON:
                        rv, rt = p1_rp_val, p1_rp_tipo
                    elif pr.categoria == Prenda.C_SACO:
                        rv, rt = p1_rs_val, p1_rs_tipo
                    else:
                        rv, rt = None, ""

                    AlquilerItem.objects.create(
                        alquiler=alq,
                        persona_num=1,
                        prenda=pr,
                        ruedo_valor=rv,
                        ruedo_tipo=rt,
                    )
                    pr.estado = Prenda.E_RES
                    pr.save(update_fields=["estado"])

                # ✅ ruedos separados P2
                p2_rp_val = form.cleaned_data.get("p2_ruedo_pantalon_valor")
                p2_rp_tipo = form.cleaned_data.get("p2_ruedo_pantalon_tipo") or ""
                p2_rs_val = form.cleaned_data.get("p2_ruedo_saco_valor")
                p2_rs_tipo = form.cleaned_data.get("p2_ruedo_saco_tipo") or ""

                if (alq.persona2_nombre or "").strip() or selected["p2"]:
                    for pr in selected["p2"]:
                        if pr.categoria == Prenda.C_PANTALON:
                            rv, rt = p2_rp_val, p2_rp_tipo
                        elif pr.categoria == Prenda.C_SACO:
                            rv, rt = p2_rs_val, p2_rs_tipo
                        else:
                            rv, rt = None, ""

                        AlquilerItem.objects.create(
                            alquiler=alq,
                            persona_num=2,
                            prenda=pr,
                            ruedo_valor=rv,
                            ruedo_tipo=rt,
                        )
                        pr.estado = Prenda.E_RES
                        pr.save(update_fields=["estado"])

                mensaje = _armar_mensaje_cliente(alq)
                request.session["ultimo_mensaje_cliente"] = mensaje

            messages.success(request, "Alquiler creado. Copiá el mensaje para el cliente.")
            return redirect("alquileres:crear")

        messages.error(request, "Revisá los campos (hay errores).")
    else:
        hoy = timezone.localdate()
        form = AlquilerForm(initial={"fecha_reserva": hoy})

    return render(request, "alquileres/crear.html", {
        "form": form,
        "disp": disp,
        "mensaje_cliente": msg_cliente,
    })


def _sync_prendas_por_estado(alq: Alquiler):
    items = alq.items.select_related("prenda").all()
    for it in items:
        p = it.prenda
        if p.estado == Prenda.E_DAN:
            continue
        if alq.estado_alquiler == Alquiler.EST_RESERVADO:
            p.estado = Prenda.E_RES
        elif alq.estado_alquiler == Alquiler.EST_ENTREGADO:
            p.estado = Prenda.E_ENT
        elif alq.estado_alquiler == Alquiler.EST_CERRADO:
            p.estado = Prenda.E_DISP
        p.save(update_fields=["estado"])


def ver(request):
    if request.method == "POST":
        alq_id = request.POST.get("alq_id")
        alq = get_object_or_404(Alquiler, id=alq_id)

        nuevo_saldo = request.POST.get("estado_saldo")
        nuevo_estado = request.POST.get("estado_alquiler")

        changed = False

        if nuevo_saldo in dict(Alquiler.ESTADOS_SALDO):
            if alq.estado_saldo != nuevo_saldo:
                alq.estado_saldo = nuevo_saldo
                changed = True

        if nuevo_estado in dict(Alquiler.ESTADOS_ALQUILER):
            if alq.estado_alquiler != nuevo_estado:
                alq.estado_alquiler = nuevo_estado
                changed = True

        if changed:
            alq.save()
            _sync_prendas_por_estado(alq)
            messages.success(request, f"Alquiler #{alq.id} actualizado.")
        else:
            messages.info(request, "No hubo cambios.")

        return redirect("alquileres:ver")

    alquileres = (Alquiler.objects
                  .all()
                  .order_by("fecha_entrega", "fecha_devolucion", "-creado_en"))

    return render(request, "alquileres/ver.html", {
        "alquileres": alquileres,
        "estados_alquiler": Alquiler.ESTADOS_ALQUILER,
        "estados_saldo": Alquiler.ESTADOS_SALDO,
    })
