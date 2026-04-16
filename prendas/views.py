from django.contrib import messages
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .forms import (
    BRANDS,
    BuscarPrendaForm,
    COLORES_CHALECO,
    COLORES_GENERALES,
    COLORES_TRAJE,
    COLORES_ZAPATOS,
    GENERIC_NUM,
    GENERIC_TALLES,
    LETRAS_XS_4XL,
    LETRAS_XS_5XL,
    PrendaForm,
    TAM_NINO_ADULTO,
    color_options_for,
    requiere_origen,
    talle_options_for,
)
from .models import Prenda


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

    return f"{prefijo}-{n + 1:03d}"


def _mixed_sort(values):
    def sort_key(value):
        text = (value or "").strip()
        if text.isdigit():
            return (0, int(text), "")
        return (1, text.casefold(), text)

    clean = []
    for value in values:
        text = (value or "").strip()
        if text and text not in clean:
            clean.append(text)
    return sorted(clean, key=sort_key)


def _prenda_lookups():
    talles_letras = []
    for talle in LETRAS_XS_5XL + LETRAS_XS_4XL:
        if talle not in talles_letras:
            talles_letras.append(talle)

    return {
        "brands": BRANDS,
        "colorsByCategory": {
            cat: color_options_for(cat)
            for cat, _label in Prenda.CATEGORIAS
        },
        "tallesByCategory": {
            cat: {
                "__default": talle_options_for(cat, ""),
                "boiler": talle_options_for(cat, "Boiler"),
                "aires modernos": talle_options_for(cat, "Aires Modernos"),
            }
            for cat, _label in Prenda.CATEGORIAS
        },
        "origenes": [{"value": value, "label": label} for value, label in Prenda.ORIGENES],
        "requiresOrigen": {
            cat: {
                brand.casefold(): requiere_origen(cat, brand)
                for brand in BRANDS
            }
            for cat, _label in Prenda.CATEGORIAS
        },
        "allColors": COLORES_GENERALES,
        "allNumericTalles": GENERIC_NUM,
        "allLetterTalles": talles_letras,
        "tamNinoAdulto": TAM_NINO_ADULTO,
        "colorsTraje": COLORES_TRAJE,
        "colorsZapatos": COLORES_ZAPATOS,
        "colorsChaleco": COLORES_CHALECO,
        "categories": [{"value": value, "label": label} for value, label in Prenda.CATEGORIAS],
    }


def _prenda_form_context(form, *, titulo, subtitulo, accion_label, cancel_url, show_generate, codigo_preview=None, prenda=None):
    return {
        "form": form,
        "titulo": titulo,
        "subtitulo": subtitulo,
        "accion_label": accion_label,
        "cancel_url": cancel_url,
        "show_generate": show_generate,
        "codigo_preview": codigo_preview,
        "prenda": prenda,
        "prenda_lookups": _prenda_lookups(),
    }


def _ocupar_prendas_con_alquiler(prendas):
    if not prendas:
        return

    from alquileres.models import Alquiler, AlquilerItem

    activos = (
        AlquilerItem.objects
        .select_related("alquiler")
        .filter(
            prenda_id__in=[prenda.id for prenda in prendas],
            alquiler__estado_alquiler__in=[Alquiler.EST_RESERVADO, Alquiler.EST_ENTREGADO],
        )
        .order_by("alquiler__fecha_entrega", "alquiler__fecha_devolucion", "alquiler__id")
    )

    ocupacion_por_prenda = {}
    vistos_por_prenda = {}
    for item in activos:
        vistos = vistos_por_prenda.setdefault(item.prenda_id, set())
        if item.alquiler_id in vistos:
            continue
        vistos.add(item.alquiler_id)
        ocupacion_por_prenda.setdefault(item.prenda_id, []).append(item.alquiler)

    for prenda in prendas:
        alquileres_activos = ocupacion_por_prenda.get(prenda.id, [])
        prenda.alquileres_activos = alquileres_activos
        prenda.alquiler_activo = alquileres_activos[0] if alquileres_activos else None


def crear_prenda(request):
    codigo_preview = None

    if request.method == "POST":
        accion = request.POST.get("accion", "generar")
        form = PrendaForm(request.POST)

        if form.is_valid():
            categoria = form.cleaned_data["categoria"]
            prefijo = PREFIJOS.get(categoria, "XX")

            if accion == "generar":
                codigo_preview = _next_codigo(prefijo)
                messages.info(request, f"Codigo sugerido: {codigo_preview}. Si esta bien, guarda la prenda.")
            else:
                with transaction.atomic():
                    for _ in range(15):
                        codigo = _next_codigo(prefijo)
                        obj = form.save(commit=False)
                        obj.codigo = codigo
                        try:
                            obj.save()
                            messages.success(request, f"Prenda creada: {obj.codigo} ({obj.get_categoria_display()})")
                            return redirect("prendas:stock")
                        except IntegrityError:
                            continue
                messages.error(request, "No se pudo generar un codigo unico.")
        else:
            messages.error(request, "Revisa los campos marcados.")
    else:
        form = PrendaForm()

    ctx = _prenda_form_context(
        form,
        titulo="Crear prenda",
        subtitulo="Carga rapida con menus desplegables y codigo automatico",
        accion_label="Guardar prenda",
        cancel_url="prendas:stock",
        show_generate=True,
        codigo_preview=codigo_preview,
    )
    return render(request, "prendas/crear.html", ctx)


def editar_prenda(request, pk):
    prenda = get_object_or_404(Prenda, pk=pk)

    if request.method == "POST":
        form = PrendaForm(request.POST, instance=prenda)
        if form.is_valid():
            form.save()
            messages.success(request, f"Prenda actualizada: {prenda.codigo}.")
            return redirect("prendas:stock")
        messages.error(request, "Revisa los campos marcados.")
    else:
        form = PrendaForm(instance=prenda)

    ctx = _prenda_form_context(
        form,
        titulo="Modificar prenda",
        subtitulo=f"Edita los datos de {prenda.codigo} sin cambiar el codigo",
        accion_label="Guardar cambios",
        cancel_url="prendas:stock",
        show_generate=False,
        codigo_preview=prenda.codigo,
        prenda=prenda,
    )
    return render(request, "prendas/crear.html", ctx)


@require_http_methods(["GET", "POST"])
def stock(request):
    if request.method == "POST":
        prenda_id = request.POST.get("prenda_id")
        prenda = get_object_or_404(Prenda, id=prenda_id)
        accion = request.POST.get("accion", "actualizar")

        if accion == "eliminar":
            codigo = prenda.codigo
            try:
                prenda.delete()
                messages.success(request, f"Prenda eliminada: {codigo}.")
            except ProtectedError:
                messages.error(
                    request,
                    f"No se puede eliminar {codigo} porque ya esta asociada a uno o mas alquileres.",
                )
            return redirect("prendas:stock")

        nuevo_estado = request.POST.get("estado")
        estados_validos = [estado for estado, _label in Prenda.ESTADOS]

        if nuevo_estado in estados_validos:
            prenda.estado = nuevo_estado
            prenda.save(update_fields=["estado"])
            messages.success(request, f"Estado actualizado: {prenda.codigo} -> {prenda.get_estado_display()}")
        else:
            messages.error(request, "Estado invalido.")

        return redirect("prendas:stock")

    prendas = Prenda.objects.all().order_by("categoria", "-creado_en", "-codigo")
    resumen = [
        {"label": "Total", "valor": prendas.count()},
        {"label": "Disponibles", "valor": prendas.filter(estado=Prenda.E_DISP).count()},
        {"label": "Reservadas", "valor": prendas.filter(estado=Prenda.E_RES).count()},
        {"label": "Entregadas", "valor": prendas.filter(estado=Prenda.E_ENT).count()},
        {"label": "Danadas", "valor": prendas.filter(estado=Prenda.E_DAN).count()},
    ]

    return render(request, "prendas/stock.html", {
        "prendas": prendas,
        "estados": Prenda.ESTADOS,
        "resumen": resumen,
        "categorias": Prenda.CATEGORIAS,
    })


@require_http_methods(["GET"])
def buscar_prenda(request):
    marcas_db = _mixed_sort(Prenda.objects.exclude(marca="").values_list("marca", flat=True).distinct())
    talles_db = _mixed_sort(Prenda.objects.exclude(talle="").values_list("talle", flat=True).distinct())

    marcas = _mixed_sort(BRANDS + marcas_db)
    talles = talles_db

    form = BuscarPrendaForm(request.GET or None, marcas=marcas, talles=talles)
    prendas = []
    buscado = False

    if form.is_bound and form.is_valid():
        marca = form.cleaned_data.get("marca") or ""
        talle = form.cleaned_data.get("talle") or ""
        origen = form.cleaned_data.get("origen") or ""
        buscado = bool(marca or talle or origen)

        if buscado:
            qs = Prenda.objects.all()
            if marca:
                qs = qs.filter(marca=marca)
            if talle:
                qs = qs.filter(talle=talle)
            if marca.casefold() == "aires modernos" and origen:
                qs = qs.filter(origen=origen)
            prendas = list(qs.order_by("categoria", "-codigo"))
            _ocupar_prendas_con_alquiler(prendas)

    return render(request, "prendas/buscar_codigo.html", {
        "form": form,
        "prendas": prendas,
        "buscado": buscado,
        "show_origen": (form["marca"].value() or "").strip().casefold() == "aires modernos",
    })
