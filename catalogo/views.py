import logging

from django.contrib import messages
from django.conf import settings
from django.core.files.storage import default_storage
from django.core.files.storage import FileSystemStorage
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from cuentas.access import roles_requeridos
from cuentas.models import PerfilUsuario

from .forms import MODEL_FORMS
from .models import Camisa, Chaleco, Cinturon, Color, Combo, Corbata, ImagenTraje, Traje, Zapato
from .stock_sizes import talles_stock_para_color

logger = logging.getLogger(__name__)

MODELOS = {
    model._meta.model_name: model
    for model in (Traje, Chaleco, Cinturon, Corbata, Camisa, Zapato, Combo)
}
IMAGE_MODELS = (*MODELOS.values(), ImagenTraje)
permitido = roles_requeridos(PerfilUsuario.PROPIETARIO, PerfilUsuario.ADMINISTRADOR)


def _persistent_media_is_active():
    if not isinstance(default_storage, FileSystemStorage):
        return True
    return bool(getattr(settings, "MEDIA_ROOT_ENV", ""))


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
    image_fields = {
        field.name: field
        for field in instance._meta.fields
        if getattr(field, "get_internal_type", lambda: "")() == "ImageField"
    }
    for field_name, model_field in image_fields.items():
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
            failures.append((field_name, str(model_field.verbose_name)))

    if "imagenes_galeria" in received_fields:
        expected = len(form.cleaned_data.get("imagenes_galeria") or [])
        gallery = list(instance.imagenes_galeria.order_by("-id")[:expected])
        if len(gallery) != expected:
            failures.append(("imagenes_galeria", "imagen de la galería"))
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
                failures.append(("imagenes_galeria", "imagen de la galería"))

    if failures:
        failed_labels = ", ".join(
            label for _, label in dict.fromkeys(failures)
        )
        raise OSError(
            f"No pudimos guardar: {failed_labels}. "
            "El almacenamiento no confirmó el archivo."
        )


def _image_names(instance):
    return {
        field.name: getattr(getattr(instance, field.name, None), "name", "")
        for field in instance._meta.fields
        if field.get_internal_type() == "ImageField"
    }


def _name_is_referenced(name):
    if not name:
        return False
    for model in IMAGE_MODELS:
        for field in model._meta.fields:
            if field.get_internal_type() == "ImageField" and model.objects.filter(
                **{field.name: name}
            ).exists():
                return True
    return False


def _delete_unreferenced(names):
    for name in set(filter(None, names)):
        if _name_is_referenced(name):
            continue
        try:
            default_storage.delete(name)
        except Exception:
            logger.exception("No se pudo limpiar archivo huérfano: %r", name)


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
    previous_names = _image_names(instance) if instance else {}
    if request.method == "POST":
        _log_upload_diagnostics(request, tipo)
        form = MODEL_FORMS[tipo](request.POST, request.FILES, instance=instance)
        if (
            request.FILES
            and getattr(settings, "IS_RENDER", False)
            and not _persistent_media_is_active()
        ):
            logger.error(
                "Carga bloqueada: producción usa FileSystemStorage efímero. "
                "Configurar AWS_STORAGE_BUCKET_NAME o MEDIA_ROOT persistente."
            )
            form.add_error(
                None,
                "No pudimos guardar las fotos porque el almacenamiento "
                "persistente no está configurado. No se modificó el traje. "
                "Contactá al administrador.",
            )
            return render(request, "catalogo/form.html", {
                "form": form, "objeto": instance, "tipo": tipo,
            })
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
            except Exception as exc:
                new_names = list(_image_names(form.instance).values())
                new_names.extend(
                    image.name for image in getattr(form, "saved_gallery_images", [])
                )
                _delete_unreferenced(
                    name for name in new_names if name not in previous_names.values()
                )
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
                current_names = set(_image_names(form.instance).values())
                _delete_unreferenced(
                    name for name in previous_names.values() if name not in current_names
                )
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
