from decimal import Decimal
import re
from django import forms
from django.core.exceptions import ValidationError

from prendas.models import Prenda
from .models import Alquiler, AlquilerItem


CATS = [
    ("saco", Prenda.C_SACO),
    ("pantalon", Prenda.C_PANTALON),
    ("camisa", Prenda.C_CAMISA),
    ("chaleco", Prenda.C_CHALECO),
    ("mono", Prenda.C_MONO),
    ("corbata", Prenda.C_CORBATA),
    ("zapatos", Prenda.C_ZAPATOS),
    ("cinturon", Prenda.C_CINTURON),
]

SHORT_PREF = {
    "saco": "SA",
    "pantalon": "PA",
    "camisa": "CA",
    "chaleco": "CH",
    "mono": "MO",
    "corbata": "CO",
    "zapatos": "ZA",
    "cinturon": "CI",
}


def _normalizar_codigo(code: str, prefijo: str) -> str:
    raw = (code or "").strip().upper()
    pref = (prefijo or "").strip().upper()

    if not raw:
        return ""

    if raw == pref or raw == f"{pref}-":
        return ""

    if raw.isdigit():
        return f"{pref}-{int(raw):03d}"

    m = re.fullmatch(r"([A-Z]{2})\s*[- ]?\s*(\d{1,3})", raw)
    if m:
        p = m.group(1)
        n = int(m.group(2))
        return f"{p}-{n:03d}"

    return raw


class AlquilerForm(forms.ModelForm):
    # Toggle 2da persona (lo maneja JS)
    tiene_persona2 = forms.CharField(required=False, widget=forms.HiddenInput())

    # Persona 1: códigos
    p1_saco = forms.CharField(required=False)
    p1_pantalon = forms.CharField(required=False)
    p1_camisa = forms.CharField(required=False)
    p1_chaleco = forms.CharField(required=False)
    p1_mono = forms.CharField(required=False)
    p1_corbata = forms.CharField(required=False)
    p1_zapatos = forms.CharField(required=False)
    p1_cinturon = forms.CharField(required=False)

    # Ruedo Persona 1
    p1_ruedo_pantalon_valor = forms.DecimalField(required=False, max_digits=6, decimal_places=2)
    p1_ruedo_pantalon_tipo = forms.ChoiceField(required=False, choices=[("", "—")] + AlquilerItem.RUEDO_TIPOS)
    p1_ruedo_saco_valor = forms.DecimalField(required=False, max_digits=6, decimal_places=2)
    p1_ruedo_saco_tipo = forms.ChoiceField(required=False, choices=[("", "—")] + AlquilerItem.RUEDO_TIPOS)

    # Persona 2: códigos
    p2_saco = forms.CharField(required=False)
    p2_pantalon = forms.CharField(required=False)
    p2_camisa = forms.CharField(required=False)
    p2_chaleco = forms.CharField(required=False)
    p2_mono = forms.CharField(required=False)
    p2_corbata = forms.CharField(required=False)
    p2_zapatos = forms.CharField(required=False)
    p2_cinturon = forms.CharField(required=False)

    # Ruedo Persona 2
    p2_ruedo_pantalon_valor = forms.DecimalField(required=False, max_digits=6, decimal_places=2)
    p2_ruedo_pantalon_tipo = forms.ChoiceField(required=False, choices=[("", "—")] + AlquilerItem.RUEDO_TIPOS)
    p2_ruedo_saco_valor = forms.DecimalField(required=False, max_digits=6, decimal_places=2)
    p2_ruedo_saco_tipo = forms.ChoiceField(required=False, choices=[("", "—")] + AlquilerItem.RUEDO_TIPOS)

    class Meta:
        model = Alquiler
        fields = [
            "fecha_visita", "fecha_reserva", "fecha_entrega", "fecha_devolucion",
            "cliente_nombre", "cliente_telefono",
            "persona1_nombre", "persona2_nombre",
            "total_bruto", "descuento_pct", "sena",
            "metodo_sena",  # ✅ nuevo
        ]
        widgets = {
            "fecha_visita": forms.DateInput(attrs={"class": "ab-inp", "type": "date"}),
            "fecha_reserva": forms.DateInput(attrs={"class": "ab-inp", "type": "date"}),
            "fecha_entrega": forms.DateInput(attrs={"class": "ab-inp", "type": "date"}),
            "fecha_devolucion": forms.DateInput(attrs={"class": "ab-inp", "type": "date"}),

            "cliente_nombre": forms.TextInput(attrs={"class": "ab-inp"}),
            "cliente_telefono": forms.TextInput(attrs={"class": "ab-inp"}),

            "persona1_nombre": forms.TextInput(attrs={"class": "ab-inp"}),
            "persona2_nombre": forms.TextInput(attrs={"class": "ab-inp"}),

            "total_bruto": forms.NumberInput(attrs={"class": "ab-inp", "step": "0.01", "min": "0"}),
            "descuento_pct": forms.NumberInput(attrs={"class": "ab-inp", "step": "0.01", "min": "0", "max": "100"}),
            "sena": forms.NumberInput(attrs={"class": "ab-inp", "step": "0.01", "min": "0"}),

            "metodo_sena": forms.Select(attrs={"class": "ab-sel"}),  # ✅
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Inputs de códigos con datalist + prefijo fijo (JS)
        for who in ["p1", "p2"]:
            for short, _cat in CATS:
                fname = f"{who}_{short}"
                pref = SHORT_PREF.get(short, "XX")
                self.fields[fname].widget = forms.TextInput(attrs={
                    "class": "ab-inp ab-code",
                    "autocomplete": "off",
                    "list": f"dl_{short}",
                    "data-prefix": f"{pref}-",
                    "placeholder": "001",
                    "inputmode": "numeric",
                })

        # Widgets ruedos
        for f in [
            "p1_ruedo_pantalon_valor", "p1_ruedo_saco_valor",
            "p2_ruedo_pantalon_valor", "p2_ruedo_saco_valor",
        ]:
            self.fields[f].widget = forms.NumberInput(attrs={"class": "ab-inp", "step": "0.01"})

        for f in [
            "p1_ruedo_pantalon_tipo", "p1_ruedo_saco_tipo",
            "p2_ruedo_pantalon_tipo", "p2_ruedo_saco_tipo",
        ]:
            self.fields[f].widget.attrs.update({"class": "ab-sel"})

    def clean(self):
        cleaned = super().clean()

        # 2da persona
        tiene_p2 = (cleaned.get("tiene_persona2") or "").strip() == "1"
        any_p2 = any((cleaned.get(f"p2_{short}") or "").strip() for short, _ in CATS)
        if (tiene_p2 or any_p2) and not (cleaned.get("persona2_nombre") or "").strip():
            self.add_error("persona2_nombre", "Si agregás 2da persona, tenés que poner el nombre.")

        any_p1 = any((cleaned.get(f"p1_{short}") or "").strip() for short, _ in CATS)
        if not any_p1 and not any_p2:
            raise ValidationError("Tenés que elegir al menos una prenda.")

        usados = set()

        def validar_code(code: str, categoria: str, fieldname: str, prefijo: str):
            code2 = _normalizar_codigo(code, prefijo)
            if not code2:
                return None

            try:
                pr = Prenda.objects.get(codigo=code2)
            except Prenda.DoesNotExist:
                self.add_error(fieldname, "Código inexistente.")
                return None

            if pr.categoria != categoria:
                self.add_error(fieldname, "Ese código no corresponde a esa categoría.")
                return None

            if pr.estado != Prenda.E_DISP:
                self.add_error(fieldname, f"Esa prenda no está disponible (estado: {pr.get_estado_display()}).")
                return None

            if pr.codigo in usados:
                self.add_error(fieldname, "Repetiste el mismo código.")
                return None

            usados.add(pr.codigo)
            cleaned[fieldname] = pr.codigo
            return pr

        selected = {"p1": [], "p2": []}
        for who in ["p1", "p2"]:
            for short, cat in CATS:
                fname = f"{who}_{short}"
                pref = SHORT_PREF.get(short, "XX")
                pr = validar_code(cleaned.get(fname), cat, fname, pref)
                if pr:
                    selected[who].append(pr)

        cleaned["_selected_prendas"] = selected

        total = Decimal(cleaned.get("total_bruto") or 0)
        sena = Decimal(cleaned.get("sena") or 0)
        if total < 0:
            self.add_error("total_bruto", "El total no puede ser negativo.")
        if sena < 0:
            self.add_error("sena", "La seña no puede ser negativa.")

        # ✅ método seña: si hay seña > 0, obligamos método
        mp = (cleaned.get("metodo_sena") or "").strip()
        if sena > 0 and not mp:
            self.add_error("metodo_sena", "Elegí método de pago de la seña.")

        return cleaned
