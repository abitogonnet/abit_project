from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from cuentas.access import roles_requeridos
from cuentas.models import PerfilUsuario

from .forms import MODEL_FORMS
from .models import Camisa, Chaleco, Cinturon, Combo, Corbata, Traje, Zapato

MODELOS = {
    model._meta.model_name: model
    for model in (Traje, Chaleco, Cinturon, Corbata, Camisa, Zapato, Combo)
}
permitido = roles_requeridos(PerfilUsuario.PROPIETARIO, PerfilUsuario.ADMINISTRADOR)


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
    form = MODEL_FORMS[tipo](request.POST or None, request.FILES or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Producto guardado y actualizado en el catálogo público.")
        return redirect("catalogo:gestion")
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
