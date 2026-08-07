import re

from prendas.forms import SACO_TALLES, talle_options_for
from prendas.models import Color, Prenda

from .models import Traje


CATEGORIES_BY_MODEL = {
    "chaleco": (Prenda.C_CHALECO,),
    "camisa": (Prenda.C_CAMISA,),
    "zapato": (Prenda.C_ZAPATOS,),
    "corbata": (Prenda.C_CORBATA,),
    "cinturon": (Prenda.C_CINTURON,),
}


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


def talles_stock_por_color(model, colors):
    categories = CATEGORIES_BY_MODEL.get(model._meta.model_name, ())
    result = []
    useful_stock = Prenda.objects.exclude(estado=Prenda.E_DAN)
    category_labels = dict(Prenda.CATEGORIAS)
    for color in colors:
        groups = []
        for category in categories:
            normalized_color = Prenda.normalize_color_value(color.nombre, category)
            sizes = list(useful_stock.filter(
                categoria=category,
                color=normalized_color,
            ).exclude(talle="").values_list("talle", flat=True))
            option_order = {
                value: index
                for index, value in enumerate(talle_options_for(category, ""))
            }
            sizes = sorted(_unique(sizes), key=lambda value: (
                0 if value in option_order else 1,
                option_order.get(value, 0),
                _natural_key(value),
            ))
            if category == Prenda.C_CAMISA:
                children = [
                    size for size in sizes
                    if size.isdigit() and int(size) <= 16
                ]
                adults = [size for size in sizes if size not in children]
                if children:
                    groups.append({"categoria": "Niños", "talles": children})
                if adults:
                    groups.append({"categoria": "Adultos", "talles": adults})
            elif sizes:
                groups.append({
                    "categoria": category_labels.get(category, category.title()),
                    "talles": sizes,
                })
        if groups:
            result.append({"color": color.nombre, "grupos": groups})
    return result


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
