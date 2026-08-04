from prendas.models import Color, Prenda


CATEGORY_BY_MODEL = {
    "traje": (Prenda.C_SACO, Prenda.C_PANTALON),
    "camisa": (Prenda.C_CAMISA,),
    "zapato": (Prenda.C_ZAPATOS,),
    "chaleco": (Prenda.C_CHALECO,),
    "corbata": (Prenda.C_CORBATA,),
    "cinturon": (Prenda.C_CINTURON,),
}


def stock_colors_for_model(model):
    categories = CATEGORY_BY_MODEL.get(model._meta.model_name, ())
    raw = Prenda.objects.filter(categoria__in=categories).exclude(color="").values_list("color", "categoria")
    keys = set()
    for value, category in raw:
        normalized = Prenda.normalize_color_value(value, category)
        keys.add(Color.normalizar_clave(normalized))
        Color.objects.get_or_create(clave_normalizada=Color.normalizar_clave(normalized), defaults={"nombre": normalized})
    return Color.objects.filter(clave_normalizada__in=keys).order_by("nombre")
