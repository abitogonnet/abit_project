from django.contrib import messages
from django.db import IntegrityError, transaction
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_http_methods

from .models import Prenda
from .forms import (
    PrendaForm,
    BRANDS, COLORES_TRAJE, COLORES_ZAPATOS, COLORES_CHALECO,
    GENERIC_NUM, LETRAS_XS_5XL, LETRAS_XS_4XL, TAM_NINO_ADULTO
)

# =========================
# PREFIJOS DE CÓDIGO
# =========================
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


# =========================
# UTILIDADES
# =========================
def _next_codigo(prefijo: str) -> str:
    prefijo = prefijo.upper()
    last = (
        Prenda.objects
        .filter(codigo__startswith=f"{prefijo}-")
        .order_by("-codigo")
        .first()
    )

    if not last:
        n = 0
    else:
        try:
            n = int(last.codigo.split("-")[1])
        except Exception:
            n = 0

    return f"{prefijo}-{n+1:03d}"


def _ctx_lists():
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


# =========================
# CREAR PRENDA
# =========================
def crear_prenda(request):
    return HttpResponse("crear_prenda OK")


# =========================
# STOCK + CAMBIO DE ESTADO
# =========================
@require_http_methods(["GET", "POST"])
def stock(request):
    if request.method == "POST":
        prenda_id = request.POST.get("prenda_id")
        nuevo_estado = request.POST.get("estado")

        pr = get_object_or_404(Prenda, id=prenda_id)

        estados_validos = [e[0] for e in Prenda.ESTADOS]
        if nuevo_estado in estados_validos:
            pr.estado = nuevo_estado
            pr.save(update_fields=["estado"])
            messages.success(
                request,
                f"Estado actualizado: {pr.codigo} → {pr.get_estado_display()}"
            )
        else:
            messages.error(request, "Estado inválido.")

        return redirect("prendas:stock")

    prendas = Prenda.objects.all().order_by("categoria", "codigo")
    return render(request, "prendas/stock.html", {
        "prendas": prendas,
        "estados": Prenda.ESTADOS,
    })


# =========================
# BUSCAR POR CÓDIGO
# =========================
@require_http_methods(["GET"])
def buscar_codigo(request):
    code = (request.GET.get("codigo") or "").strip().upper()

    prenda = None
    alquiler_item = None

    if code:
        import re
        m = re.fullmatch(r"([A-Z]{2})\s*[- ]?\s*(\d{1,3})", code)
        if m:
            pref = m.group(1)
            num = int(m.group(2))
            code = f"{pref}-{num:03d}"

        try:
            prenda = Prenda.objects.get(codigo=code)
        except Prenda.DoesNotExist:
            prenda = None

        if prenda:
            from alquileres.models import AlquilerItem
            alquiler_item = (
                AlquilerItem.objects
                .select_related("alquiler", "prenda")
                .filter(prenda=prenda)
                .order_by("-alquiler__creado_en")
                .first()
            )

    return render(request, "prendas/buscar_codigo.html", {
        "codigo": code,
        "prenda": prenda,
        "alquiler_item": alquiler_item,
    })
