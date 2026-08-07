from django.shortcuts import render
from catalogo.models import (
    Camisa,
    Chaleco,
    Cinturon,
    Combo,
    Corbata,
    Traje,
    Zapato,
)


def home(request):
    trajes_importados = (
        Traje.objects
        .filter(linea=Traje.LINEA_IMPORTADA, activo=True)
        .select_related("color_stock")
        .prefetch_related("imagenes_galeria")
        .order_by("-creado")
    )

    trajes_nacionales = (
        Traje.objects
        .filter(linea=Traje.LINEA_NACIONAL, activo=True)
        .select_related("color_stock")
        .prefetch_related("imagenes_galeria")
        .order_by("-creado")
    )

    camisas = (
        Camisa.objects
        .filter(activo=True)
        .prefetch_related("colores_stock")
        .order_by("-creado")
    )

    zapatos = (
        Zapato.objects
        .filter(activo=True)
        .prefetch_related("colores_stock")
        .order_by("-creado")
    )

    otros_productos = []
    for model, tipo in ((Chaleco, "Chaleco"), (Corbata, "Corbata"), (Cinturon, "Cinturón")):
        for producto in model.objects.filter(activo=True).prefetch_related("colores_stock").order_by("-creado"):
            producto.tipo_publico = tipo
            otros_productos.append(producto)

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
        "otros_productos": otros_productos,
    })
