from decimal import Decimal

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


CODIGO_PREFIJOS = {
    Prenda.C_SACO: "SA",
    Prenda.C_PANTALON: "PA",
    Prenda.C_CAMISA: "CA",
    Prenda.C_CHALECO: "CH",
    Prenda.C_MONO: "MO",
    Prenda.C_CORBATA: "CO",
    Prenda.C_ZAPATOS: "ZA",
    Prenda.C_CINTURON: "CI",
}


def _prenda_choices(prendas):
    choices = [("", "Sin seleccionar")]
    for prenda in prendas:
        desc = f"{prenda.codigo} - {prenda.color} {prenda.marca} talle {prenda.talle}".strip()
        choices.append((prenda.codigo, desc))
    return choices


def _buscar_conflicto(prenda: Prenda, fecha_entrega, fecha_devolucion):
    if not prenda or not fecha_entrega or not fecha_devolucion:
        return None

    return (
        AlquilerItem.objects
        .select_related("alquiler")
        .filter(
            prenda=prenda,
            alquiler__estado_alquiler__in=[Alquiler.EST_RESERVADO, Alquiler.EST_ENTREGADO],
            alquiler__fecha_entrega__lte=fecha_devolucion,
            alquiler__fecha_devolucion__gte=fecha_entrega,
        )
        .order_by("alquiler__fecha_entrega", "alquiler__id")
        .first()
    )


class AlquilerForm(forms.ModelForm):
    tiene_persona2 = forms.CharField(required=False, widget=forms.HiddenInput())

    p1_saco = forms.ChoiceField(required=False)
    p1_pantalon = forms.ChoiceField(required=False)
    p1_camisa = forms.ChoiceField(required=False)
    p1_chaleco = forms.ChoiceField(required=False)
    p1_mono = forms.ChoiceField(required=False)
    p1_corbata = forms.ChoiceField(required=False)
    p1_zapatos = forms.ChoiceField(required=False)
    p1_cinturon = forms.ChoiceField(required=False)

    p1_ruedo_pantalon_valor = forms.DecimalField(required=False, max_digits=6, decimal_places=2)
    p1_ruedo_pantalon_tipo = forms.ChoiceField(required=False, choices=[("", "No aplica")] + AlquilerItem.RUEDO_TIPOS)
    p1_ruedo_saco_valor = forms.DecimalField(required=False, max_digits=6, decimal_places=2)
    p1_ruedo_saco_tipo = forms.ChoiceField(required=False, choices=[("", "No aplica")] + AlquilerItem.RUEDO_TIPOS)

    p2_saco = forms.ChoiceField(required=False)
    p2_pantalon = forms.ChoiceField(required=False)
    p2_camisa = forms.ChoiceField(required=False)
    p2_chaleco = forms.ChoiceField(required=False)
    p2_mono = forms.ChoiceField(required=False)
    p2_corbata = forms.ChoiceField(required=False)
    p2_zapatos = forms.ChoiceField(required=False)
    p2_cinturon = forms.ChoiceField(required=False)

    p2_ruedo_pantalon_valor = forms.DecimalField(required=False, max_digits=6, decimal_places=2)
    p2_ruedo_pantalon_tipo = forms.ChoiceField(required=False, choices=[("", "No aplica")] + AlquilerItem.RUEDO_TIPOS)
    p2_ruedo_saco_valor = forms.DecimalField(required=False, max_digits=6, decimal_places=2)
    p2_ruedo_saco_tipo = forms.ChoiceField(required=False, choices=[("", "No aplica")] + AlquilerItem.RUEDO_TIPOS)

    class Meta:
        model = Alquiler
        fields = [
            "fecha_reserva",
            "fecha_entrega",
            "fecha_devolucion",
            "cliente_nombre",
            "cliente_telefono",
            "persona1_nombre",
            "persona2_nombre",
            "total_bruto",
            "descuento_pct",
            "sena",
            "metodo_sena",
        ]
        widgets = {
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
            "metodo_sena": forms.Select(attrs={"class": "ab-sel"}),
        }

    def __init__(self, *args, **kwargs):
        disponibles = kwargs.pop("disponibles", None) or {}
        super().__init__(*args, **kwargs)

        for who in ["p1", "p2"]:
            for short, categoria in CATS:
                fname = f"{who}_{short}"
                numero_fname = f"{fname}_numero"
                prefijo = CODIGO_PREFIJOS.get(categoria, "")

                self.fields[numero_fname] = forms.CharField(
                    required=False,
                    widget=forms.TextInput(
                        attrs={
                            "class": "ab-inp js-code-filter",
                            "autocomplete": "off",
                            "inputmode": "numeric",
                            "maxlength": "4",
                            "placeholder": "Numero",
                            "data-prefix": prefijo,
                            "data-target-select": f"id_{fname}",
                        }
                    ),
                )
                self.fields[fname].choices = _prenda_choices(disponibles.get(short, []))
                self.fields[fname].widget.attrs.update({
                    "class": "ab-sel js-code-select",
                    "data-prefix": prefijo,
                })

        for name in [
            "p1_ruedo_pantalon_valor",
            "p1_ruedo_saco_valor",
            "p2_ruedo_pantalon_valor",
            "p2_ruedo_saco_valor",
        ]:
            self.fields[name].widget = forms.NumberInput(attrs={"class": "ab-inp", "step": "0.01"})

        for name in [
            "p1_ruedo_pantalon_tipo",
            "p1_ruedo_saco_tipo",
            "p2_ruedo_pantalon_tipo",
            "p2_ruedo_saco_tipo",
        ]:
            self.fields[name].widget.attrs.update({"class": "ab-sel"})

    def clean(self):
        cleaned = super().clean()
        fecha_entrega = cleaned.get("fecha_entrega")
        fecha_devolucion = cleaned.get("fecha_devolucion")

        tiene_p2 = (cleaned.get("tiene_persona2") or "").strip() == "1"
        any_p2 = any((cleaned.get(f"p2_{short}") or "").strip() for short, _ in CATS)
        if (tiene_p2 or any_p2) and not (cleaned.get("persona2_nombre") or "").strip():
            self.add_error("persona2_nombre", "Si agregas 2da persona, completa el nombre.")

        any_p1 = any((cleaned.get(f"p1_{short}") or "").strip() for short, _ in CATS)
        if not any_p1 and not any_p2:
            raise ValidationError("Tienes que elegir al menos una prenda.")

        usados = set()

        def validar_code(code: str, categoria: str, fieldname: str):
            codigo = (code or "").strip()
            if not codigo:
                return None

            try:
                prenda = Prenda.objects.get(codigo=codigo)
            except Prenda.DoesNotExist:
                self.add_error(fieldname, "Codigo inexistente.")
                return None

            if prenda.categoria != categoria:
                self.add_error(fieldname, "Ese codigo no corresponde a esa categoria.")
                return None

            if prenda.estado == Prenda.E_DAN:
                self.add_error(fieldname, "Esa prenda esta marcada como danada.")
                return None

            conflicto = _buscar_conflicto(prenda, fecha_entrega, fecha_devolucion)
            if conflicto:
                self.add_error(
                    fieldname,
                    "Esa prenda ya esta ocupada del "
                    f"{conflicto.alquiler.fecha_entrega.strftime('%d/%m/%Y')} al "
                    f"{conflicto.alquiler.fecha_devolucion.strftime('%d/%m/%Y')}."
                )
                return None

            if prenda.codigo in usados:
                self.add_error(fieldname, "Repetiste la misma prenda.")
                return None

            usados.add(prenda.codigo)
            cleaned[fieldname] = prenda.codigo
            return prenda

        selected = {"p1": [], "p2": []}
        for who in ["p1", "p2"]:
            for short, categoria in CATS:
                field_name = f"{who}_{short}"
                prenda = validar_code(cleaned.get(field_name), categoria, field_name)
                if prenda:
                    selected[who].append(prenda)

        cleaned["_selected_prendas"] = selected

        total = Decimal(cleaned.get("total_bruto") or 0)
        sena = Decimal(cleaned.get("sena") or 0)
        if total < 0:
            self.add_error("total_bruto", "El total no puede ser negativo.")
        if sena < 0:
            self.add_error("sena", "La sena no puede ser negativa.")

        metodo_sena = (cleaned.get("metodo_sena") or "").strip()
        if sena > 0 and not metodo_sena:
            self.add_error("metodo_sena", "Elige el metodo de pago de la sena.")

        return cleaned


class VerAlquileresFiltroForm(forms.Form):
    fecha_desde = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"class": "ab-inp", "type": "date"}),
    )
    fecha_hasta = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"class": "ab-inp", "type": "date"}),
    )

    def clean(self):
        cleaned = super().clean()
        fecha_desde = cleaned.get("fecha_desde")
        fecha_hasta = cleaned.get("fecha_hasta")

        if fecha_desde and fecha_hasta and fecha_desde > fecha_hasta:
            self.add_error("fecha_hasta", "La fecha final no puede ser menor que la inicial.")

        return cleaned
