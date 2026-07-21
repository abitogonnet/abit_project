from django import forms
from django.contrib.auth import authenticate, password_validation
from django.contrib.auth.models import User

from .models import PerfilUsuario


class LoginForm(forms.Form):
    username = forms.CharField(label="Usuario")
    password = forms.CharField(label="Contraseña", widget=forms.PasswordInput)

    def __init__(self, request=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.request, self.user_cache = request, None

    def clean(self):
        data = super().clean()
        if data.get("username") and data.get("password"):
            self.user_cache = authenticate(self.request, username=data["username"], password=data["password"])
            if self.user_cache is None:
                raise forms.ValidationError("Usuario o contraseña incorrectos.")
            if not self.user_cache.is_active:
                raise forms.ValidationError("Este usuario está inactivo.")
        return data

    def get_user(self):
        return self.user_cache


class UsuarioForm(forms.Form):
    nombre = forms.CharField(max_length=150)
    username = forms.CharField(label="Nombre de usuario", max_length=150)
    password1 = forms.CharField(label="Contraseña", widget=forms.PasswordInput, required=False)
    password2 = forms.CharField(label="Confirmación", widget=forms.PasswordInput, required=False)
    rol = forms.ChoiceField(choices=PerfilUsuario.ROLES)

    def __init__(self, *args, user=None, require_password=False, **kwargs):
        self.edited_user, self.require_password = user, require_password
        super().__init__(*args, **kwargs)
        if require_password:
            self.fields["password1"].required = self.fields["password2"].required = True

    def clean_username(self):
        value = self.cleaned_data["username"].strip().lower()
        qs = User.objects.filter(username__iexact=value)
        if self.edited_user:
            qs = qs.exclude(pk=self.edited_user.pk)
        if qs.exists():
            raise forms.ValidationError("Ese nombre de usuario ya existe.")
        return value

    def clean(self):
        data = super().clean()
        p1, p2 = data.get("password1"), data.get("password2")
        if p1 != p2:
            self.add_error("password2", "Las contraseñas no coinciden.")
        if p1:
            password_validation.validate_password(p1, self.edited_user)
        return data

