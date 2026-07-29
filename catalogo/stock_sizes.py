import re

from prendas.forms import SACO_TALLES
from prendas.models import Color, Prenda

from .models import Traje


def _unique(values):
    return list(dict.fromkeys(value for value in values if value))


def _natural_key(value):
    return [
        int(part) if part.isdigit() else part.casefold()
        for part in re.split(r"(\d+)", value)
    ]


def ordenar_talles_saco(values):
    known_order = {value: index for index, value in enumerate(SACO_TALLES)}
    return sorted(
        _unique(values),
        key=lambda value: (
            0 if value in known_order else 1,
            known_order.get(value, 0),
            _natural_key(value),
        ),
    )


def ordenar_talles_pantalon(values):
    return sorted(_unique(values), key=_natural_key)


def talles_stock_para_color(color):
    if not color:
        return {"sacos": [], "pantalones": []}

    color_saco = Prenda.normalize_color_value(color.nombre, Prenda.C_SACO)
    color_pantalon = Prenda.normalize_color_value(
        color.nombre, Prenda.C_PANTALON
    )
    prendas = Prenda.objects.exclude(estado=Prenda.E_DAN)
    sacos = prendas.filter(
        categoria=Prenda.C_SACO,
        color=color_saco,
    ).values_list("talle", flat=True)
    pantalones = prendas.filter(
        categoria=Prenda.C_PANTALON,
        color=color_pantalon,
    ).values_list("talle", flat=True)
    return {
        "sacos": ordenar_talles_saco(sacos),
        "pantalones": ordenar_talles_pantalon(pantalones),
    }


def actualizar_talles_traje(traje):
    talles = talles_stock_para_color(traje.color_stock)
    Traje.objects.filter(pk=traje.pk).update(
        talles_saco_stock=talles["sacos"],
        talles_pantalon_stock=talles["pantalones"],
    )
    traje.talles_saco_stock = talles["sacos"]
    traje.talles_pantalon_stock = talles["pantalones"]
    return talles


def actualizar_trajes_por_nombres_color(*nombres):
    claves = {
        Color.normalizar_clave(
            Prenda.normalize_color_value(nombre, Prenda.C_SACO)
        )
        for nombre in nombres
        if nombre
    }
    if not claves:
        return
    for traje in Traje.objects.exclude(color_stock=None).select_related("color_stock"):
        clave_traje = Color.normalizar_clave(
            Prenda.normalize_color_value(
                traje.color_stock.nombre,
                Prenda.C_SACO,
            )
        )
        if clave_traje in claves:
            actualizar_talles_traje(traje)
