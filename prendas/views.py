from django.contrib import messages
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.http import JsonResponse
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from .forms import (
    BRANDS,
    BuscarPrendaForm,
    COLORES_CHALECO,
    COLORES_GENERALES,
    COLORES_RESTRINGIDOS_POR_CATEGORIA,
    COLORES_TRAJE,
    COLORES_ZAPATOS,
    GENERIC_NUM,
    GENERIC_TALLES,
    LETRAS_XS_4XL,
    LETRAS_XS_5XL,
    PrendaForm,
    ColorForm,
    TAM_NINO_ADULTO,
    color_options_for,
    requiere_origen,
    restricted_color_options_for,
    talle_options_for,
)
from .models import Color, Prenda
from cuentas.models import Actividad
from cuentas.access import roles_requeridos
from cuentas.models import PerfilUsuario
from cuentas.services import registrar_actividad


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
        "restrictedColorCategories": list(COLORES_RESTRINGIDOS_POR_CATEGORIA.keys()),
        "restrictedColorsByCategory": {
            cat: restricted_color_options_for(cat)
            for cat, _label in Prenda.CATEGORIAS
            if restricted_color_options_for(cat)
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
            cat: requiere_origen(cat, "")
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
        "corbata_value": Prenda.C_CORBATA,
        "automatic_origin_categories": list(Prenda.ORIGEN_AUTOMATICO_POR_CATEGORIA),
    }


def _categorias_con_origen():
    return [
        value
        for value, _label in Prenda.CATEGORIAS
        if Prenda.requiere_origen_manual(value)
    ]


def _prendas_sin_origen():
    return Prenda.incompletas().order_by("categoria", "marca", "talle", "codigo")


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


def _buscar_por_codigo(q: str):
    codigo = (q or "").strip().upper()
    if not codigo:
        return []

    qs = Prenda.objects.all()
    if "-" in codigo:
        qs = qs.filter(codigo__icontains=codigo)
    else:
        qs = qs.filter(codigo__icontains=codigo)

    prendas = list(qs.order_by("categoria", "codigo")[:20])
    _ocupar_prendas_con_alquiler(prendas)
    return prendas


def crear_prenda(request):
    codigo_preview = None
    embed = request.GET.get("embed") == "1" or request.POST.get("embed") == "1"

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
                            registrar_actividad(request, "Creó prenda", Actividad.STOCK, objeto=obj, referencia=obj.codigo)
                            messages.success(request, f"Prenda creada: {obj.codigo} ({obj.get_categoria_display()})")
                            if embed:
                                return render(request, "prendas/creada_embed.html", {"prenda": obj})
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
    ctx["embed"] = embed
    return render(request, "prendas/crear.html", ctx)


def editar_prenda(request, pk):
    prenda = get_object_or_404(Prenda, pk=pk)

    if request.method == "POST":
        form = PrendaForm(request.POST, instance=prenda)
        if form.is_valid():
            estado_anterior = prenda.estado
            actualizada = form.save()
            actualizada.refresh_from_db()
            registrar_actividad(request, "Modificó prenda", Actividad.STOCK, objeto=prenda, referencia=prenda.codigo)
            if prenda.estado != estado_anterior:
                registrar_actividad(request, "Cambió estado de prenda", Actividad.STOCK, objeto=prenda, referencia=prenda.codigo, detalle=prenda.get_estado_display())
            messages.success(
                request,
                f"Prenda actualizada: {actualizada.codigo}."
                + (" Ya no está incompleta." if actualizada.esta_completa else ""),
            )
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


@roles_requeridos(
    PerfilUsuario.PROPIETARIO,
    PerfilUsuario.ADMINISTRADOR,
    PerfilUsuario.EMPLEADO,
)
def detalle_prenda(request, pk):
    from alquileres.models import Alquiler, AlquilerItem

    prenda = get_object_or_404(Prenda, pk=pk)
    items = list(
        AlquilerItem.objects
        .filter(prenda=prenda)
        .select_related("alquiler")
        .order_by("-alquiler__fecha_entrega", "-alquiler__id", "id")
    )

    usos = []
    alquileres_vistos = set()
    for item in items:
        alquiler = item.alquiler
        if alquiler.pk in alquileres_vistos:
            continue
        alquileres_vistos.add(alquiler.pk)
        persona = alquiler.persona_nombre(item.persona_num).strip()
        usos.append({
            "alquiler": alquiler,
            "persona": persona or alquiler.cliente_nombre,
            "persona_exacta": bool(persona),
            "ver_url": (
                f"{reverse('alquileres:ver')}?buscar={alquiler.pk}"
                f"#alquiler-{alquiler.pk}"
            ),
            "es_actual": alquiler.estado_alquiler in Alquiler.ESTADOS_ALQUILER_ACTIVOS,
            "cuenta_como_uso": alquiler.estado_alquiler in {
                Alquiler.EST_ENTREGADO,
                Alquiler.EST_CERRADO,
            },
        })

    usos_actuales = [uso for uso in usos if uso["es_actual"]]
    usos_historicos = sum(1 for uso in usos if uso["cuenta_como_uso"])
    categorias_sin_origen = {
        Prenda.C_CAMISA,
        Prenda.C_CORBATA,
        Prenda.C_CINTURON,
        Prenda.C_ZAPATOS,
    }
    return render(request, "prendas/detalle.html", {
        "prenda": prenda,
        "usos": usos,
        "usos_actuales": usos_actuales,
        "usos_historicos": usos_historicos,
        "mostrar_origen": prenda.categoria not in categorias_sin_origen,
    })


@require_http_methods(["GET", "POST"])
def stock(request):
    if request.method == "POST":
        accion = request.POST.get("accion", "actualizar")

        if accion == "agregar_color":
            color_form = ColorForm(request.POST)
            if color_form.is_valid():
                color = color_form.save()
                registrar_actividad(request, "Agregó color", Actividad.STOCK, objeto=color, referencia=color.nombre)
                messages.success(request, f'Color agregado: {color.nombre}.')
            else:
                messages.error(request, " ".join(error for errors in color_form.errors.values() for error in errors))
            return redirect("prendas:stock")

        if accion == "guardar_origenes":
            origenes_validos = {value for value, _label in Prenda.ORIGENES}
            cambios = {}

            for key, value in request.POST.items():
                if not key.startswith("origen_"):
                    continue
                try:
                    prenda_id = int(key.split("_", 1)[1])
                except (IndexError, ValueError):
                    continue
                nuevo_origen = (value or "").strip()
                if nuevo_origen in origenes_validos:
                    cambios[prenda_id] = nuevo_origen

            prendas = list(
                Prenda.objects.filter(
                    id__in=cambios.keys(),
                    categoria__in=_categorias_con_origen(),
                )
            )
            actualizadas = []
            for prenda in prendas:
                nuevo_origen = cambios.get(prenda.id, "")
                if nuevo_origen and prenda.origen != nuevo_origen:
                    prenda.origen = nuevo_origen
                    actualizadas.append(prenda)

            if actualizadas:
                Prenda.objects.bulk_update(actualizadas, ["origen"])
                for actualizada in actualizadas:
                    registrar_actividad(request, "Modificó prenda", Actividad.STOCK, objeto=actualizada, referencia=actualizada.codigo, detalle="Origen actualizado")
                total = len(actualizadas)
                messages.success(
                    request,
                    f"Origen actualizado en {total} prenda{'s' if total != 1 else ''}.",
                )
            else:
                messages.info(request, "No se guardaron cambios de origen.")
            return redirect("prendas:stock")

        prenda_id = request.POST.get("prenda_id")
        prenda = get_object_or_404(Prenda, id=prenda_id)

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
            estado_anterior = prenda.estado
            prenda.estado = nuevo_estado
            prenda.save(update_fields=["estado"])
            if estado_anterior != nuevo_estado:
                anterior_label = dict(Prenda.ESTADOS).get(estado_anterior, estado_anterior)
                registrar_actividad(request, "Cambió estado de prenda", Actividad.STOCK, objeto=prenda, referencia=prenda.codigo, detalle=f"{anterior_label} → {prenda.get_estado_display()}")
            messages.success(request, f"Estado actualizado: {prenda.codigo} -> {prenda.get_estado_display()}")
        else:
            messages.error(request, "Estado invalido.")

        return redirect("prendas:stock")

    prendas = list(Prenda.objects.all().order_by("categoria", "-creado_en", "-codigo"))
    _ocupar_prendas_con_alquiler(prendas)
    prendas_sin_origen = list(_prendas_sin_origen())
    resumen = [
        {"label": "Total", "valor": len(prendas)},
        {"label": "Disponibles", "valor": sum(1 for prenda in prendas if prenda.estado == Prenda.E_DISP)},
        {"label": "Reservadas", "valor": sum(1 for prenda in prendas if prenda.estado == Prenda.E_RES)},
        {"label": "Entregadas", "valor": sum(1 for prenda in prendas if prenda.estado == Prenda.E_ENT)},
        {"label": "Lavandería", "valor": sum(1 for prenda in prendas if prenda.estado == Prenda.E_LAV)},
        {"label": "Danadas", "valor": sum(1 for prenda in prendas if prenda.estado == Prenda.E_DAN)},
        {"label": "Sin origen", "valor": len(prendas_sin_origen)},
    ]

    return render(request, "prendas/stock.html", {
        "prendas": prendas,
        "prendas_sin_origen": prendas_sin_origen,
        "estados": Prenda.ESTADOS,
        "origenes": Prenda.ORIGENES,
        "resumen": resumen,
        "categorias": Prenda.CATEGORIAS,
        "color_form": ColorForm(),
    })


@require_http_methods(["GET"])
def buscar_prenda(request):
    marcas_db = _mixed_sort(Prenda.objects.exclude(marca="").values_list("marca", flat=True).distinct())
    colores_db = _mixed_sort(Prenda.objects.exclude(color="").values_list("color", flat=True).distinct())
    talles_db = _mixed_sort(Prenda.objects.exclude(talle="").values_list("talle", flat=True).distinct())

    marcas = _mixed_sort(BRANDS + marcas_db)
    colores = colores_db
    talles = talles_db

    form = BuscarPrendaForm(request.GET or None, marcas=marcas, colores=colores, talles=talles)
    prendas = []
    prendas_por_codigo = []
    buscado = False
    codigo_buscado = (request.GET.get("codigo") or "").strip().upper()

    if form.is_bound and form.is_valid():
        categoria = form.cleaned_data.get("categoria") or ""
        marca = form.cleaned_data.get("marca") or ""
        color = form.cleaned_data.get("color") or ""
        talle = form.cleaned_data.get("talle") or ""
        origen = form.cleaned_data.get("origen") or ""
        buscado = bool(categoria or marca or color or talle or origen)

        if buscado:
            qs = Prenda.objects.all()
            if categoria:
                qs = qs.filter(categoria=categoria)
            if marca:
                qs = qs.filter(marca=marca)
            if color:
                qs = qs.filter(color=color)
            if talle:
                qs = qs.filter(talle=talle)
            if origen:
                qs = qs.filter(origen=origen)
            prendas = list(qs.order_by("categoria", "-codigo"))
            _ocupar_prendas_con_alquiler(prendas)

    if codigo_buscado:
        prendas_por_codigo = _buscar_por_codigo(codigo_buscado)

    return render(request, "prendas/buscar_codigo.html", {
        "form": form,
        "prendas": prendas,
        "prendas_por_codigo": prendas_por_codigo,
        "buscado": buscado,
        "codigo_buscado": codigo_buscado,
        "embed": request.GET.get("embed") == "1",
    })


def disponibles_api(request):
    prendas = Prenda.objects.exclude(estado__in=[Prenda.E_DAN, Prenda.E_LAV]).order_by("categoria", "codigo")
    return JsonResponse({"prendas": [
        {
            "codigo": p.codigo, "categoria": p.categoria,
            "label": f"{p.codigo} - {p.color} {p.marca} talle {p.talle}".strip(),
        }
        for p in prendas
    ]})
