from .models import Actividad


def registrar_actividad(request, accion, categoria, *, objeto=None, referencia="", detalle="", financiera=False):
    user = getattr(request, "user", None)
    if not getattr(user, "is_authenticated", False):
        return None
    nombre = getattr(getattr(user, "perfil", None), "nombre", "") or user.get_full_name() or user.username
    return Actividad.objects.create(
        usuario=user, usuario_nombre=nombre, accion=accion, categoria=categoria,
        tipo_objeto=objeto.__class__.__name__ if objeto is not None else "",
        objeto_id=str(objeto.pk) if objeto is not None and objeto.pk is not None else "",
        referencia=referencia, detalle=detalle, es_financiera=financiera,
    )

