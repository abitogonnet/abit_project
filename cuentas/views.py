import hmac
import os
from datetime import datetime, time, timedelta

from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .access import es_propietario, puede_finanzas
from .forms import LoginForm, UsuarioForm
from .models import Actividad, PerfilUsuario
from .services import registrar_actividad


def _hay_propietario():
    return PerfilUsuario.objects.filter(rol=PerfilUsuario.PROPIETARIO, user__is_active=True).exists()


def _configurar_vencimiento(request):
    now = timezone.localtime()
    if time(17, 0) <= now.time() < time(21, 0):
        end = timezone.make_aware(datetime.combine(now.date(), time(21, 0)), timezone.get_current_timezone())
        request.session.set_expiry(max(1, int((end - now).total_seconds())))
    else:
        request.session.set_expiry(0)


def iniciar_sesion(request):
    if request.user.is_authenticated:
        return redirect("alquileres:home")
    form = LoginForm(request, request.POST or None)
    if request.method == "POST" and form.is_valid():
        login(request, form.get_user())
        _configurar_vencimiento(request)
        next_url = request.POST.get("next") or request.GET.get("next")
        if request.user.perfil.debe_cambiar_password:
            return redirect("cuentas:cambiar_password")
        if request.user.perfil.rol == PerfilUsuario.COSTURERA:
            return redirect("alquileres:ruedos")
        return redirect(next_url if next_url and next_url.startswith("/") else "alquileres:home")
    return render(request, "cuentas/login.html", {"form": form, "next": request.GET.get("next", "")})


@require_http_methods(["POST"])
def cerrar_sesion(request):
    logout(request)
    return redirect("cuentas:login")


def configuracion_inicial(request):
    if _hay_propietario():
        messages.info(request, "La configuración inicial ya fue realizada.")
        return redirect("cuentas:login")
    expected = os.environ.get("INITIAL_SETUP_SECRET", "")
    data = request.POST.copy() if request.method == "POST" else None
    if data is not None:
        data["rol"] = PerfilUsuario.PROPIETARIO
    form = UsuarioForm(data, require_password=True, initial={"rol": PerfilUsuario.PROPIETARIO})
    if request.method == "POST":
        supplied = request.POST.get("setup_secret", "")
        if not expected or not hmac.compare_digest(supplied, expected):
            form.add_error(None, "Clave inicial incorrecta o no configurada.")
        elif form.is_valid():
            with transaction.atomic():
                if _hay_propietario():
                    return redirect("cuentas:login")
                user = User.objects.create_user(form.cleaned_data["username"], password=form.cleaned_data["password1"])
                PerfilUsuario.objects.create(user=user, nombre=form.cleaned_data["nombre"], rol=PerfilUsuario.PROPIETARIO, debe_cambiar_password=False)
            messages.success(request, "Propietario creado. Ya podés iniciar sesión.")
            return redirect("cuentas:login")
    return render(request, "cuentas/configuracion_inicial.html", {"form": form})


def usuarios(request):
    if not es_propietario(request.user): raise PermissionDenied
    return render(request, "cuentas/usuarios.html", {"usuarios": User.objects.select_related("perfil").order_by("username")})


def usuario_crear(request):
    if not es_propietario(request.user): raise PermissionDenied
    form = UsuarioForm(request.POST or None, require_password=True)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            user = User.objects.create_user(form.cleaned_data["username"], password=form.cleaned_data["password1"])
            PerfilUsuario.objects.create(user=user, nombre=form.cleaned_data["nombre"], rol=form.cleaned_data["rol"], debe_cambiar_password=True)
        registrar_actividad(request, "Creó usuario", Actividad.USUARIOS, objeto=user, referencia=user.username)
        return redirect("cuentas:usuarios")
    return render(request, "cuentas/usuario_form.html", {"form": form, "titulo": "Crear usuario"})


def usuario_editar(request, pk):
    if not es_propietario(request.user): raise PermissionDenied
    user = get_object_or_404(User.objects.select_related("perfil"), pk=pk)
    form = UsuarioForm(request.POST or None, user=user, initial={"nombre": user.perfil.nombre, "username": user.username, "rol": user.perfil.rol})
    if request.method == "POST" and form.is_valid():
        if user.perfil.rol == PerfilUsuario.PROPIETARIO and form.cleaned_data["rol"] != PerfilUsuario.PROPIETARIO and PerfilUsuario.objects.filter(rol=PerfilUsuario.PROPIETARIO, user__is_active=True).count() <= 1:
            form.add_error("rol", "Debe quedar al menos un propietario activo.")
            return render(request, "cuentas/usuario_form.html", {"form": form, "titulo": "Modificar usuario", "edited_user": user})
        user.username = form.cleaned_data["username"]
        if form.cleaned_data["password1"]: user.set_password(form.cleaned_data["password1"])
        user.save(); user.perfil.nombre = form.cleaned_data["nombre"]; user.perfil.rol = form.cleaned_data["rol"]; user.perfil.save()
        registrar_actividad(request, "Modificó usuario", Actividad.USUARIOS, objeto=user, referencia=user.username)
        return redirect("cuentas:usuarios")
    return render(request, "cuentas/usuario_form.html", {"form": form, "titulo": "Modificar usuario", "edited_user": user})


@require_http_methods(["POST"])
def usuario_estado(request, pk):
    if not es_propietario(request.user): raise PermissionDenied
    user = get_object_or_404(User, pk=pk)
    if user == request.user and user.is_active:
        messages.error(request, "No podés desactivar tu propia sesión.")
    elif user.is_active and getattr(user, "perfil", None) and user.perfil.rol == PerfilUsuario.PROPIETARIO and PerfilUsuario.objects.filter(rol=PerfilUsuario.PROPIETARIO, user__is_active=True).count() <= 1:
        messages.error(request, "Debe quedar al menos un propietario activo.")
    else:
        user.is_active = not user.is_active; user.save(update_fields=["is_active"])
        registrar_actividad(request, "Activó usuario" if user.is_active else "Desactivó usuario", Actividad.USUARIOS, objeto=user, referencia=user.username)
    return redirect("cuentas:usuarios")


def actividad(request):
    qs = Actividad.objects.select_related("usuario", "usuario__perfil")
    if not puede_finanzas(request.user): qs = qs.filter(es_financiera=False)
    uid, categoria, desde, hasta = (request.GET.get(k, "") for k in ("usuario", "categoria", "desde", "hasta"))
    if uid.isdigit(): qs = qs.filter(usuario_id=int(uid))
    if categoria: qs = qs.filter(categoria=categoria)
    if desde: qs = qs.filter(creado_en__date__gte=desde)
    if hasta: qs = qs.filter(creado_en__date__lte=hasta)
    return render(request, "cuentas/actividad.html", {"actividades": qs[:500], "usuarios": User.objects.filter(actividades__isnull=False).distinct(), "categorias": Actividad.CATEGORIAS, "filtros": request.GET})


def cambiar_password(request):
    form = PasswordChangeForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        request.user.perfil.debe_cambiar_password = False
        request.user.perfil.save(update_fields=["debe_cambiar_password"])
        update_session_auth_hash(request, user)
        registrar_actividad(request, "Cambió su contraseña", Actividad.USUARIOS, objeto=user, referencia=user.username)
        messages.success(request, "Contraseña actualizada.")
        return redirect("alquileres:home")
    return render(request, "cuentas/cambiar_password.html", {"form": form})
