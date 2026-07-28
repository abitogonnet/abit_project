from django.shortcuts import render
from catalogo.models import (
    Camisa,
    Combo,
    Traje,
    Zapato,
)
from prendas.models import Color, Prenda


def _agregar_talles_stock(trajes):
    trajes = list(trajes)
    color_ids = [item.color_stock_id for item in trajes if item.color_stock_id]
    colores = {color.id: color.nombre for color in Color.objects.filter(id__in=color_ids)}
    for traje in trajes:
        color = colores.get(traje.color_stock_id)
        origen = (
            Prenda.O_IMP if traje.linea == traje.LINEA_IMPORTADA else
            Prenda.O_NAC if traje.linea == traje.LINEA_NACIONAL else ""
        )
        qs = Prenda.objects.filter(
            categoria__in=[Prenda.C_SACO, Prenda.C_PANTALON],
            color=color,
        )
        if origen:
            qs = qs.filter(origen=origen)
        rows = qs.values_list("categoria", "talle").distinct()
        traje.talles_stock_saco = sorted({t for c, t in rows if c == Prenda.C_SACO})
        traje.talles_stock_pantalon = sorted({t for c, t in rows if c == Prenda.C_PANTALON})
    return trajes


def home(request):
    trajes_importados = _agregar_talles_stock(
        Traje.objects
        .filter(linea=Traje.LINEA_IMPORTADA, activo=True)
        .prefetch_related("talles")
        .order_by("-creado")
    )

    trajes_nacionales = _agregar_talles_stock(
        Traje.objects
        .filter(linea=Traje.LINEA_NACIONAL, activo=True)
        .prefetch_related("talles")
        .order_by("-creado")
    )

    camisas = (
        Camisa.objects
        .filter(activo=True)
        .prefetch_related("talles")
        .order_by("-creado")
    )

    zapatos = (
        Zapato.objects
        .filter(activo=True)
        .prefetch_related("talles")
        .order_by("-creado")
    )

    combos = (
        Combo.objects
        .filter(activo=True)
        .order_by("orden", "id")
    )

    return render(request, "publico/home.html", {
        "trajes_importados": trajes_importados,
        "trajes_nacionales": trajes_nacionales,
        "camisas": camisas,
        "zapatos": zapatos,
        "combos": combos,
    })
