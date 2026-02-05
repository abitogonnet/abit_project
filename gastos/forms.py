from decimal import Decimal
from django import forms
from django.core.exceptions import ValidationError
from .models import Gasto, DivisionBienes


CATEGORIAS = [
    "Lavandería",
    "Arreglos",
    "Compras",
    "Publicidad",
    "Servicios",
    "Transporte",
    "Otros",
]

METODOS = [
    "Efectivo",
    "Transferencia",
    "Tarjeta",
    "MercadoPago",
    "Otro",
]


def _norm(s: str) -> str:
    return (s or "").strip()


def _in_list(val: str, options: list[str]) -> bool:
    v = _norm(val).casefold()
    return any(v == o.casefold() for o in options)


class GastoForm(forms.ModelForm):
    class Meta:
        model = Gasto
        fields = ["fecha", "categoria", "metodo", "descripcion", "monto"]
        widgets = {
            "fecha": forms.DateInput(attrs={"class": "ab-inp", "type": "date"}),
            "categoria": forms.TextInput(attrs={"class": "ab-inp", "list": "dl_gasto_cat", "autocomplete": "off"}),
            "metodo": forms.TextInput(attrs={"class": "ab-inp", "list": "dl_gasto_met", "autocomplete": "off"}),
            "descripcion": forms.TextInput(attrs={"class": "ab-inp", "placeholder": "Opcional"}),
            "monto": forms.NumberInput(attrs={"class": "ab-inp", "step": "0.01", "min": "0"}),
        }

    def clean_categoria(self):
        cat = _norm(self.cleaned_data.get("categoria", ""))
        if not cat:
            raise ValidationError("La categoría es obligatoria.")
        if not _in_list(cat, CATEGORIAS):
            raise ValidationError("La categoría debe ser una opción del desplegable.")
        for c in CATEGORIAS:
            if cat.casefold() == c.casefold():
                return c
        return cat

    def clean_metodo(self):
        met = _norm(self.cleaned_data.get("metodo", ""))
        if not met:
            return ""
        if not _in_list(met, METODOS):
            raise ValidationError("El método debe ser una opción del desplegable.")
        for m in METODOS:
            if met.casefold() == m.casefold():
                return m
        return met


class DivisionBienesForm(forms.ModelForm):
    class Meta:
        model = DivisionBienes
        fields = ["fecha", "monto_total", "para_tade", "para_bauti", "notas"]
        widgets = {
            "fecha": forms.DateInput(attrs={"class": "ab-inp", "type": "date"}),
            "monto_total": forms.NumberInput(attrs={"class": "ab-inp", "step": "0.01", "min": "0"}),
            "para_tade": forms.NumberInput(attrs={"class": "ab-inp", "step": "0.01", "min": "0"}),
            "para_bauti": forms.NumberInput(attrs={"class": "ab-inp", "step": "0.01", "min": "0"}),
            "notas": forms.TextInput(attrs={"class": "ab-inp", "placeholder": "Opcional"}),
        }

    def clean(self):
        cleaned = super().clean()
        total = Decimal(cleaned.get("monto_total") or 0)
        tade = cleaned.get("para_tade")
        bauti = cleaned.get("para_bauti")

        if total < 0:
            self.add_error("monto_total", "El total no puede ser negativo.")
            return cleaned

        # Permitimos que cargues 1 de los dos y el otro se complete solo.
        if tade is None and bauti is None:
            raise ValidationError("Cargá al menos uno: Tade o Bauti.")

        tade_val = Decimal(tade or 0)
        bauti_val = Decimal(bauti or 0)

        if tade is None and bauti is not None:
            tade_val = total - bauti_val
        if bauti is None and tade is not None:
            bauti_val = total - tade_val

        if tade_val < 0:
            self.add_error("para_tade", "No puede quedar negativo.")
        if bauti_val < 0:
            self.add_error("para_bauti", "No puede quedar negativo.")

        if (tade_val + bauti_val) != total:
            raise ValidationError("La suma (Tade + Bauti) tiene que ser exactamente igual al total.")

        cleaned["para_tade"] = tade_val
        cleaned["para_bauti"] = bauti_val
        return cleaned


# Export para templates
GASTO_CATEGORIAS = CATEGORIAS
GASTO_METODOS = METODOS
