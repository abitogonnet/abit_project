from django.contrib import messages
from django.db import IntegrityError, transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_http_methods

from alquileres.models import Alquiler, AlquilerItem
from .models import Prenda
from .forms import (
    PrendaForm,
    BRANDS, COLORES_TRAJE, COLORES_ZAPATOS, COLORES_CHALECO,
    GENERIC_NUM, LETRAS_XS_5XL, LETRAS_XS_4XL, TAM_NINO_ADULTO
)

# Prefijo (2 letras) para el código
PREFIJOS = {
    Prenda.C_SACO: "SA",
    Prenda.C_PANTALON: "PA",
    Prenda.C_CAMISA: "CA",
    Prenda.C_CHALECO: "CH",
    Prenda.C_MONO: "MO",
    Prenda.C_CORBATA: "CO",
    Prenda.C_ZAPATOS: "ZA",
    Prenda.C_CINTURON: "CI",
}

def _next_codigo(prefijo: str) -> str:
    prefijo = prefijo.upper()
    last = (Prenda.objects
            .filter(codigo__startswith=f"{prefijo}-")
            .order_by("-codigo")
            .first())
    if not last:
        n = 0
    else:
        try:
            n = int(last.codigo.split("-")[1])
        except Exception:
            n = 0
    return f"{prefijo}-{n+1:03d}"

def _ctx_lists():
    # Para los datalist del template (SIN split en template)
    talles_letras = []
    for t in (LETRAS_XS_5XL + LETRAS_XS_4XL):
        if t not in talles_letras:
            talles_letras.append(t)

    return {
        "brands": BRANDS,
        "colores_traje": COLORES_TRAJE,
        "colores_zapatos": COLORES_ZAPATOS,
        "colores_chaleco": COLORES_CHALECO,
        "talles_nums": GENERIC_NUM,
        "talles_letras": talles_letras,
        "tam_nino_adulto": TAM_NINO_ADULTO,
    }

def crear_prenda(request):
    """
    Proceso 1:
      - Completar datos
      - Botón "Crear código" (preview)
      - Botón "Confirmar prenda" (guarda)
    """
    codigo_preview = None

    if request.method == "POST":
        accion = request.POST.get("accion", "generar")
        form = PrendaForm(request.POST)

        if form.is_valid():
            cat = form.cleaned_data["categoria"]
            pref = PREFIJOS.get(cat, "XX")

            if accion == "generar":
                codigo_preview = _next_codigo(pref)
                messages.info(request, f"Código generado: {codigo_preview}. Ahora confirmá para guardar.")
                ctx = {"form": form, "codigo_preview": codigo_preview}
                ctx.update(_ctx_lists())
                return render(request, "prendas/crear.html", ctx)

            if accion == "confirmar":
                with transaction.atomic():
                    for _ in range(15):
                        codigo = _next_codigo(pref)
                        obj = form.save(commit=False)
                        obj.codigo = codigo
                        try:
                            obj.save()
                            messages.success(request, f"Prenda creada: {obj.codigo} ({obj.get_categoria_display()})")
                            return redirect("prendas:stock")
                        except IntegrityError:
                            continue
                messages.error(request, "No se pudo generar un código único. Probá de nuevo.")
        else:
            messages.error(request, "Revisá los campos marcados (deben elegirse del desplegable).")
    else:
        form = PrendaForm()

    ctx = {"form": form, "codigo_preview": codigo_preview}
    ctx.update(_ctx_lists())
    return render(request, "prendas/crear.html", ctx)

@require_http_methods(["GET", "POST"])
def stock(request):
    """
    Ver stock y cambiar estado con desplegable.
    """
    if request.method == "POST":
        prenda_id = request.POST.get("prenda_id")
        nuevo_estado = request.POST.get("estado")
        pr = get_object_or_404(Prenda, id=prenda_id)

        estados_validos = [e[0] for e in Prenda.ESTADOS]
        if nuevo_estado in estados_validos:
            pr.estado = nuevo_estado
            pr.save(update_fields=["estado"])
            messages.success(request, f"Estado actualizado: {pr.codigo} → {pr.get_estado_display()}")
        else:
            messages.error(request, "Estado inválido.")

        return redirect("prendas:stock")

    prendas = Prenda.objects.all().order_by("categoria", "codigo")
    return render(request, "prendas/stock.html", {
        "prendas": prendas,
        "estados": Prenda.ESTADOS,
    })


# =========================
# NUEVO: BUSCAR POR CODIGO (prefijo + 3 dígitos)
# =========================
@require_http_methods(["GET"])
def buscar_codigo(request):
    prefijo = (request.GET.get("prefijo") or "SA").strip().upper()
    num_raw = (request.GET.get("num") or "").strip()

    # Normalizar num: puede venir "1" "01" "001"
    num_digits = "".join([c for c in num_raw if c.isdigit()])[:3]

    codigo = ""
    if num_digits:
        codigo = f"{prefijo}-{int(num_digits):03d}"

    prenda = None
    alquiler_activo = None
    alquiler_item = None

    if num_raw and not num_digits:
        messages.error(request, "El número debe ser 1–3 dígitos (ej: 1, 01 o 001).")

    if codigo:
        try:
            prenda = Prenda.objects.get(codigo__iexact=codigo)
        except Prenda.DoesNotExist:
            prenda = None
            messages.error(request, f"No se encontró una prenda con código {codigo}.")

        if prenda:
            alquiler_item = (AlquilerItem.objects
                             .select_related("alquiler", "prenda")
                             .filter(prenda=prenda)
                             .exclude(alquiler__estado_alquiler=Alquiler.EST_CERRADO)
                             .order_by("-alquiler__fecha_entrega", "-alquiler__id")
                             .first())
            if alquiler_item:
                alquiler_activo = alquiler_item.alquiler

    return render(request, "prendas/buscar_codigo.html", {
        "prefijo": prefijo,
        "num": num_raw,
        "codigo": codigo,
        "prenda": prenda,
        "alquiler_activo": alquiler_activo,
        "alquiler_item": alquiler_item,
    })
