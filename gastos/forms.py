from decimal import Decimal
from django import forms


class RangoInformeSemanalForm(forms.Form):
    desde = forms.DateField(
        required=False,
        label="Desde",
        widget=forms.DateInput(attrs={"type": "date", "class": "ab-inp"}),
    )
    hasta = forms.DateField(
        required=False,
        label="Hasta",
        widget=forms.DateInput(attrs={"type": "date", "class": "ab-inp"}),
    )

    def clean(self):
        cleaned = super().clean()
        desde = cleaned.get("desde")
        hasta = cleaned.get("hasta")
        if bool(desde) != bool(hasta):
            raise forms.ValidationError("Elegí las dos fechas o dejá ambas vacías para usar la última semana.")
        if desde and hasta and desde > hasta:
            raise forms.ValidationError("La fecha desde no puede ser posterior a la fecha hasta.")
        return cleaned
from django.core.exceptions import ValidationError
from .models import Gasto, DivisionBienes

HTML_DATE_FORMAT = "%Y-%m-%d"


CATEGORIAS = [
    "PAGO NANO/LUCAS",
    "PAGO RUEDOS",
    "PAGO BELEN",
    "COMPRA DE PRODUCTOS",
    "GASTOS TADE Y BAUTI",
    "PUBLICIDAD",
    "PAGO DE ALQUILER",
    "SERVICIOS",
]

METODOS = [
    "Efectivo",
    "Transferencia",
    "Tarjeta",
    "MercadoPago",
    "Otro",
]


def _html_date_widget():
    return forms.DateInput(
        format=HTML_DATE_FORMAT,
        attrs={"class": "ab-inp", "type": "date"},
    )


def _norm(s: str) -> str:
    return (s or "").strip()


def _in_list(val: str, options: list[str]) -> bool:
    v = _norm(val).casefold()
    return any(v == o.casefold() for o in options)


class GastoForm(forms.ModelForm):
    categoria = forms.ChoiceField(
        choices=[("", "Elegir categoria")] + [(c, c) for c in CATEGORIAS],
        widget=forms.Select(attrs={"class": "ab-sel"}),
    )
    metodo = forms.ChoiceField(
        choices=[("", "Elegir metodo")] + [(m, m) for m in METODOS],
        required=False,
        widget=forms.Select(attrs={"class": "ab-sel"}),
    )

    class Meta:
        model = Gasto
        fields = ["fecha", "categoria", "metodo", "descripcion", "notas", "monto"]
        widgets = {
            "fecha": _html_date_widget(),
            "descripcion": forms.TextInput(attrs={"class": "ab-inp", "placeholder": "Ej: tela, limpieza, publicidad"}),
            "notas": forms.TextInput(attrs={"class": "ab-inp", "placeholder": "Opcional"}),
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
            "fecha": _html_date_widget(),
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
