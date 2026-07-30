import logging

from django.contrib import messages
from django.core.files.storage import default_storage
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from cuentas.access import roles_requeridos
from cuentas.models import PerfilUsuario

from .forms import MODEL_FORMS
from .models import Camisa, Chaleco, Cinturon, Color, Combo, Corbata, Traje, Zapato
from .stock_sizes import talles_stock_para_color

logger = logging.getLogger(__name__)

MODELOS = {
    model._meta.model_name: model
    for model in (Traje, Chaleco, Cinturon, Corbata, Camisa, Zapato, Combo)
}
permitido = roles_requeridos(PerfilUsuario.PROPIETARIO, PerfilUsuario.ADMINISTRADOR)


def _log_upload_diagnostics(request, tipo):
    logger.info(
        "Carga catálogo: tipo=%s post_keys=%s file_keys=%s storage=%s",
        tipo,
        sorted(request.POST.keys()),
        sorted(request.FILES.keys()),
        f"{default_storage.__class__.__module__}."
        f"{default_storage.__class__.__name__}",
    )
    for field_name, files in request.FILES.lists():
        for uploaded in files:
            name = str(getattr(uploaded, "name", ""))
            logger.info(
                "Archivo recibido: campo=%s nombre=%r content_type=%r "
                "tamaño=%r extensión=%r",
                field_name,
                name,
                getattr(uploaded, "content_type", ""),
                getattr(uploaded, "size", None),
                name.rsplit(".", 1)[-1].lower() if "." in name else "",
            )


def _verify_received_images(form, received_fields):
    instance = form.instance
    failures = []
    for field_name in ("foto_modelo", "foto_colgado"):
        if field_name not in received_fields:
            continue
        image = getattr(instance, field_name, None)
        name = getattr(image, "name", "")
        try:
            url = image.url if name else ""
            exists = bool(name and image.storage.exists(name))
        except Exception:
            logger.exception(
                "No se pudo resolver imagen guardada: producto=%s campo=%s "
                "nombre=%r",
                instance.pk,
                field_name,
                name,
            )
            url = ""
            exists = False
        logger.info(
            "Imagen post-guardado: producto=%s campo=%s nombre=%r url=%r "
            "existe=%s storage=%s",
            instance.pk,
            field_name,
            name,
            url,
            exists,
            image.storage.__class__.__name__ if image else "sin imagen",
        )
        if not exists:
            failures.append(field_name)

    if "imagenes_galeria" in received_fields:
        expected = len(form.cleaned_data.get("imagenes_galeria") or [])
        gallery = list(instance.imagenes_galeria.order_by("-id")[:expected])
        if len(gallery) != expected:
            failures.append("imagenes_galeria")
        for gallery_image in gallery:
            image = gallery_image.imagen
            try:
                url = image.url
                exists = image.storage.exists(image.name)
            except Exception:
                logger.exception(
                    "No se pudo resolver imagen de galería: producto=%s "
                    "imagen=%s nombre=%r",
                    instance.pk,
                    gallery_image.pk,
                    image.name,
                )
                url = ""
                exists = False
            logger.info(
                "Galería post-guardado: producto=%s imagen=%s nombre=%r "
                "url=%r existe=%s storage=%s",
                instance.pk,
                gallery_image.pk,
                image.name,
                url,
                exists,
                image.storage.__class__.__name__,
            )
            if not exists:
                failures.append("imagenes_galeria")

    if failures:
        labels = {
            "foto_modelo": "la foto principal",
            "foto_colgado": "la foto colgado",
            "imagenes_galeria": "una imagen de la galería",
        }
        failed_labels = ", ".join(
            labels[name] for name in dict.fromkeys(failures)
        )
        raise OSError(
            f"No pudimos guardar {failed_labels}. "
            "El almacenamiento no confirmó el archivo."
        )


@permitido
def gestion(request):
    grupos = [
        {"slug": slug, "label": model._meta.verbose_name_plural.title(), "items": model.objects.all()}
        for slug, model in MODELOS.items()
    ]
    return render(request, "catalogo/gestion.html", {"grupos": grupos})


@permitido
def editar(request, tipo, pk=None):
    model = MODELOS.get(tipo)
    if model is None:
        from django.http import Http404
        raise Http404
    instance = get_object_or_404(model, pk=pk) if pk else None
    if request.method == "POST":
        _log_upload_diagnostics(request, tipo)
        form = MODEL_FORMS[tipo](request.POST, request.FILES, instance=instance)
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
                    _verify_received_images(form, set(request.FILES.keys()))
            except Exception as exc:
                logger.exception(
                    "Falló el guardado del catálogo: tipo=%s producto=%s "
                    "storage=%s",
                    tipo,
                    getattr(form.instance, "pk", None),
                    default_storage.__class__.__name__,
                )
                if instance is None:
                    form.instance.pk = None
                form.add_error(None, str(exc))
            else:
                messages.success(
                    request,
                    "Producto guardado y actualizado en el catálogo público.",
                )
                return redirect("catalogo:gestion")
        else:
            logger.warning(
                "Formulario de catálogo inválido: tipo=%s errores=%s "
                "file_keys=%s",
                tipo,
                form.errors.as_json(),
                sorted(request.FILES.keys()),
            )
    else:
        form = MODEL_FORMS[tipo](instance=instance)
    return render(request, "catalogo/form.html", {
        "form": form, "objeto": instance, "tipo": tipo,
    })


@permitido
def publicar(request, tipo, pk):
    model = MODELOS.get(tipo)
    objeto = get_object_or_404(model, pk=pk) if model else None
    if request.method == "POST" and objeto is not None:
        objeto.activo = not objeto.activo
        objeto.save(update_fields=["activo"])
        messages.success(request, "Publicación actualizada.")
    return redirect("catalogo:gestion")


@permitido
def talles_stock(request):
    color_id = request.GET.get("color_id")
    color = Color.objects.filter(pk=color_id).first() if color_id else None
    return JsonResponse(talles_stock_para_color(color))
