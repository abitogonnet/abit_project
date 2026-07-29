from django.shortcuts import render
from catalogo.models import (
    Camisa,
    Combo,
    Traje,
    Zapato,
)


def _preparar_trajes_catalogo(trajes):
    trajes = list(trajes)
    for traje in trajes:
        filas = list(traje.talles.all())
        traje.colores_catalogo = list(dict.fromkeys(fila.color for fila in filas))
        traje.talles_saco_catalogo = list(
            dict.fromkeys(fila.talle_saco for fila in filas)
        )
        traje.talles_pantalon_catalogo = list(
            dict.fromkeys(fila.talle_pantalon for fila in filas)
        )
    return trajes


def home(request):
    trajes_importados = _preparar_trajes_catalogo(
        Traje.objects
        .filter(linea=Traje.LINEA_IMPORTADA, activo=True)
        .prefetch_related("talles", "imagenes_galeria")
        .order_by("-creado")
    )

    trajes_nacionales = _preparar_trajes_catalogo(
        Traje.objects
        .filter(linea=Traje.LINEA_NACIONAL, activo=True)
        .prefetch_related("talles", "imagenes_galeria")
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
