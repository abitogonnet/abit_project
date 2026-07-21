from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError

from prendas.models import Prenda

from .models import Alquiler, AlquilerItem

HTML_DATE_FORMAT = "%Y-%m-%d"


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


PERSONA_INDICES = tuple(range(1, Alquiler.MAX_PERSONAS + 1))
PERSONAS_FORM = [f"p{numero}" for numero in PERSONA_INDICES]
CATEGORIA_POR_SHORT = dict(CATS)
SHORT_POR_CATEGORIA = {categoria: short for short, categoria in CATS}
CATEGORIA_LABELS = dict(Prenda.CATEGORIAS)
RUEDO_FIELDS = {
    "pantalon": ("ruedo_pantalon_valor", "ruedo_pantalon_tipo"),
    "saco": ("ruedo_saco_valor", "ruedo_saco_tipo"),
}


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


def _persona_name_field(persona_num: int) -> str:
    return f"persona{persona_num}_nombre"


def _alquiler_form_fields():
    return [
        "fecha_reserva",
        "fecha_entrega",
        "fecha_devolucion",
        "cliente_nombre",
        "cliente_telefono",
        *[_persona_name_field(persona_num) for persona_num in PERSONA_INDICES],
        "total_bruto",
        "descuento_pct",
        "sena",
        "metodo_sena",
    ]


def _alquiler_form_widgets():
    widgets = {
        "fecha_reserva": _html_date_widget(),
        "fecha_entrega": _html_date_widget(),
        "fecha_devolucion": _html_date_widget(),
        "cliente_nombre": forms.TextInput(attrs={"class": "ab-inp"}),
        "cliente_telefono": forms.TextInput(attrs={"class": "ab-inp"}),
        "total_bruto": forms.NumberInput(attrs={"class": "ab-inp", "step": "0.01", "min": "0"}),
        "descuento_pct": forms.NumberInput(attrs={"class": "ab-inp", "step": "0.01", "min": "0", "max": "100"}),
        "sena": forms.NumberInput(attrs={"class": "ab-inp", "step": "0.01", "min": "0"}),
        "metodo_sena": forms.Select(attrs={"class": "ab-sel"}),
    }
    widgets.update({
        _persona_name_field(persona_num): forms.TextInput(attrs={"class": "ab-inp"})
        for persona_num in PERSONA_INDICES
    })
    return widgets


def _html_date_widget():
    return forms.DateInput(
        format=HTML_DATE_FORMAT,
        attrs={"class": "ab-inp", "type": "date"},
    )


def _prenda_choices(prendas):
    choices = [("", "Sin seleccionar")]
    for prenda in prendas:
        choices.append((prenda.codigo, _prenda_label(prenda)))
    return choices


def _prenda_label(prenda: Prenda) -> str:
    return f"{prenda.codigo} - {prenda.color} {prenda.marca} talle {prenda.talle}".strip()


def _numero_codigo(codigo: str, prefijo: str) -> str:
    raw = (codigo or "").strip().upper()
    prefijo_completo = f"{(prefijo or '').upper()}-"
    if raw.startswith(prefijo_completo):
        return raw[len(prefijo_completo):]
    if "-" in raw:
        return raw.split("-", 1)[1]
    return raw


def _items_por_slot(instance: Alquiler):
    if not instance or not getattr(instance, "pk", None):
        return {}

    items = {}
    prefetched = getattr(instance, "_prefetched_objects_cache", {})
    source = prefetched.get("items")
    if source is None:
        source = instance.items.select_related("prenda")

    for item in source:
        short = SHORT_POR_CATEGORIA.get(item.prenda.categoria)
        persona = f"p{item.persona_num}"
        if not short or (persona, short) in items:
            continue
        items[(persona, short)] = item
    return items


def _bound_field_value(form, field_name: str) -> str:
    if not form.is_bound:
        return ""
    return (form.data.get(form.add_prefix(field_name)) or "").strip()


def _prenda_lookup(disponibles):
    lookup = {}
    for prendas in disponibles.values():
        for prenda in prendas:
            lookup[prenda.codigo] = prenda
    return lookup


def _compact_prenda_choices(field_value, current_item, prenda_lookup):
    choices = [("", "Sin seleccionar")]
    seen = {""}

    if current_item and current_item.prenda.codigo not in seen:
        choices.append((current_item.prenda.codigo, _prenda_label(current_item.prenda)))
        seen.add(current_item.prenda.codigo)

    if field_value and field_value not in seen:
        prenda = prenda_lookup.get(field_value)
        label = _prenda_label(prenda) if prenda else field_value
        choices.append((field_value, label))

    return choices


def _configurar_campos_prenda(form, disponibles, initial_items=None, *, compact_choices=False):
    initial_items = initial_items or {}
    prenda_lookup = _prenda_lookup(disponibles) if compact_choices else {}

    for who in PERSONAS_FORM:
        for short, categoria in CATS:
            field_name = f"{who}_{short}"
            numero_field = f"{field_name}_numero"
            prefijo = CODIGO_PREFIJOS.get(categoria, "")

            if field_name not in form.fields:
                form.fields[field_name] = forms.ChoiceField(required=False)

            form.fields[numero_field] = forms.CharField(
                required=False,
                widget=forms.TextInput(
                    attrs={
                        "class": "ab-inp js-code-filter",
                        "autocomplete": "off",
                        "inputmode": "numeric",
                        "maxlength": "4",
                        "placeholder": "Numero",
                        "data-prefix": prefijo,
                        "data-target-select": f"id_{form.add_prefix(field_name)}",
                    }
                ),
            )

            prendas_categoria = list(disponibles.get(short, []))
            current_item = initial_items.get((who, short))
            if not compact_choices and current_item and all(prenda.id != current_item.prenda_id for prenda in prendas_categoria):
                prendas_categoria = [current_item.prenda] + prendas_categoria

            field_value = _bound_field_value(form, field_name)
            if compact_choices:
                form.fields[field_name].choices = _compact_prenda_choices(field_value, current_item, prenda_lookup)
            else:
                form.fields[field_name].choices = _prenda_choices(prendas_categoria)
            form.fields[field_name].widget.attrs.update({
                "class": "ab-sel js-code-select",
                "data-prefix": prefijo,
                "data-category-key": short,
            })

            if current_item:
                form.initial.setdefault(field_name, current_item.prenda.codigo)
                form.initial.setdefault(numero_field, _numero_codigo(current_item.prenda.codigo, prefijo))

    for who in PERSONAS_FORM:
        for short, (valor_suffix, tipo_suffix) in RUEDO_FIELDS.items():
            valor_name = f"{who}_{valor_suffix}"
            tipo_name = f"{who}_{tipo_suffix}"

            if valor_name not in form.fields:
                form.fields[valor_name] = forms.DecimalField(required=False, max_digits=6, decimal_places=2)
            if tipo_name not in form.fields:
                form.fields[tipo_name] = forms.ChoiceField(
                    required=False,
                    choices=[("", "No aplica")] + AlquilerItem.RUEDO_TIPOS,
                )

            form.fields[valor_name].widget = forms.NumberInput(attrs={"class": "ab-inp", "step": "0.01"})
            form.fields[tipo_name].widget.attrs.update({"class": "ab-sel"})

            current_item = initial_items.get((who, short))
            if current_item:
                if current_item.ruedo_valor is not None:
                    form.initial.setdefault(valor_name, current_item.ruedo_valor)
                if current_item.ruedo_tipo:
                    form.initial.setdefault(tipo_name, current_item.ruedo_tipo)


def _rows_prendas(form, who: str):
    rows = []
    for short, categoria in CATS:
        ruedo_valor = None
        ruedo_tipo = None
        if short in RUEDO_FIELDS:
            valor_suffix, tipo_suffix = RUEDO_FIELDS[short]
            ruedo_valor = form[f"{who}_{valor_suffix}"]
            ruedo_tipo = form[f"{who}_{tipo_suffix}"]

        rows.append({
            "label": CATEGORIA_LABELS.get(categoria, short.title()),
            "prefix": CODIGO_PREFIJOS.get(categoria, ""),
            "numero": form[f"{who}_{short}_numero"],
            "select": form[f"{who}_{short}"],
            "ruedo_valor": ruedo_valor,
            "ruedo_tipo": ruedo_tipo,
        })
    return rows


def _persona_has_content(name_field, prenda_rows):
    if (name_field.value() or "").strip():
        return True

    for row in prenda_rows:
        if (row["numero"].value() or "").strip():
            return True
        if (row["select"].value() or "").strip():
            return True
        if row["ruedo_valor"] and (row["ruedo_valor"].value() or "").strip():
            return True
        if row["ruedo_tipo"] and (row["ruedo_tipo"].value() or "").strip():
            return True
    return False


def _personas_visibles_solicitadas(form) -> int:
    if not form.is_bound:
        return 1

    raw_value = (form.data.get(form.add_prefix("personas_visibles")) or "").strip()
    if not raw_value.isdigit():
        return 1

    return max(1, min(int(raw_value), Alquiler.MAX_PERSONAS))


def _build_persona_sections(form):
    sections = []
    requested_visible = _personas_visibles_solicitadas(form)
    highest_visible = 1

    for persona_num in PERSONA_INDICES:
        who = f"p{persona_num}"
        name_field = form[_persona_name_field(persona_num)]
        prenda_rows = _rows_prendas(form, who)
        has_content = _persona_has_content(name_field, prenda_rows)
        if has_content:
            highest_visible = persona_num

        sections.append({
            "number": persona_num,
            "who": who,
            "name_field": name_field,
            "prenda_rows": prenda_rows,
            "badge": "Principal" if persona_num == 1 else "Opcional",
            "has_content": has_content,
        })

    visible_count = max(requested_visible, highest_visible)
    for section in sections:
        section["visible"] = section["number"] <= visible_count

    form.personas_visibles_inicial = visible_count
    return sections


def _validar_prendas(
    form,
    cleaned,
    fecha_entrega,
    fecha_devolucion,
    *,
    exclude_alquiler_id=None,
    allow_prenda_ids=None,
):
    usados = set()
    selected = {who: {} for who in PERSONAS_FORM}
    allow_prenda_ids = set(allow_prenda_ids or [])
    requested_codes = []

    for who in PERSONAS_FORM:
        for short, _categoria in CATS:
            field_name = f"{who}_{short}"
            codigo = (cleaned.get(field_name) or "").strip()
            if codigo:
                requested_codes.append(codigo)

    prendas_by_codigo = {
        prenda.codigo: prenda
        for prenda in Prenda.objects.filter(codigo__in=requested_codes)
    }

    conflictos_by_prenda_id = {}
    if fecha_entrega and fecha_devolucion and prendas_by_codigo:
        conflictos = (
            AlquilerItem.objects
            .select_related("alquiler", "prenda")
            .filter(
                prenda_id__in=[prenda.id for prenda in prendas_by_codigo.values()],
                alquiler__estado_alquiler__in=Alquiler.ESTADOS_ALQUILER_ACTIVOS,
                alquiler__fecha_entrega__lte=fecha_devolucion,
                alquiler__fecha_devolucion__gte=fecha_entrega,
            )
            .order_by("alquiler__fecha_entrega", "alquiler__id")
        )
        if exclude_alquiler_id:
            conflictos = conflictos.exclude(alquiler_id=exclude_alquiler_id)

        for conflicto in conflictos:
            conflictos_by_prenda_id.setdefault(conflicto.prenda_id, conflicto)

    def validar_code(code: str, categoria: str, fieldname: str):
        codigo = (code or "").strip()
        if not codigo:
            return None

        prenda = prendas_by_codigo.get(codigo)
        if not prenda:
            form.add_error(fieldname, "Codigo inexistente.")
            return None

        if prenda.categoria != categoria:
            form.add_error(fieldname, "Ese codigo no corresponde a esa categoria.")
            return None

        if prenda.estado == Prenda.E_DAN and prenda.id not in allow_prenda_ids:
            form.add_error(fieldname, "Esa prenda esta marcada como danada.")
            return None

        conflicto = conflictos_by_prenda_id.get(prenda.id)
        if conflicto:
            form.add_error(
                fieldname,
                "Esa prenda ya esta ocupada del "
                f"{conflicto.alquiler.fecha_entrega.strftime('%d/%m/%Y')} al "
                f"{conflicto.alquiler.fecha_devolucion.strftime('%d/%m/%Y')}.",
            )
            return None

        if prenda.codigo in usados:
            form.add_error(fieldname, "Repetiste la misma prenda.")
            return None

        usados.add(prenda.codigo)
        cleaned[fieldname] = prenda.codigo
        return prenda

    for who in PERSONAS_FORM:
        for short, categoria in CATS:
            field_name = f"{who}_{short}"
            prenda = validar_code(cleaned.get(field_name), categoria, field_name)
            if not prenda:
                continue

            slot = {
                "prenda": prenda,
                "ruedo_valor": None,
                "ruedo_tipo": "",
            }
            if short in RUEDO_FIELDS:
                valor_suffix, tipo_suffix = RUEDO_FIELDS[short]
                slot["ruedo_valor"] = cleaned.get(f"{who}_{valor_suffix}")
                slot["ruedo_tipo"] = (cleaned.get(f"{who}_{tipo_suffix}") or "").strip()

            selected[who][short] = slot

    cleaned["_selected_prendas"] = selected
    return selected


class AlquilerForm(forms.ModelForm):
    personas_visibles = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=Alquiler.MAX_PERSONAS,
        widget=forms.HiddenInput(),
    )

    class Meta:
        model = Alquiler
        fields = _alquiler_form_fields()
        widgets = _alquiler_form_widgets()

    def __init__(self, *args, **kwargs):
        disponibles = kwargs.pop("disponibles", None) or {}
        super().__init__(*args, **kwargs)
        _configurar_campos_prenda(self, disponibles)
        self.persona_sections = _build_persona_sections(self)
        self.fields["personas_visibles"].initial = getattr(self, "personas_visibles_inicial", 1)

    def clean(self):
        cleaned = super().clean()
        fecha_entrega = cleaned.get("fecha_entrega")
        fecha_devolucion = cleaned.get("fecha_devolucion")

        selected = _validar_prendas(self, cleaned, fecha_entrega, fecha_devolucion)
        if not any(selected[who] for who in PERSONAS_FORM):
            raise ValidationError("Tienes que elegir al menos una prenda.")

        for persona_num in PERSONA_INDICES[1:]:
            who = f"p{persona_num}"
            any_persona = any((cleaned.get(f"{who}_{short}") or "").strip() for short, _ in CATS) or bool(selected[who])
            if any_persona and not (cleaned.get(_persona_name_field(persona_num)) or "").strip():
                self.add_error(
                    _persona_name_field(persona_num),
                    f"Si agregas la persona {persona_num}, completa el nombre.",
                )

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
        widget=_html_date_widget(),
    )
    fecha_hasta = forms.DateField(
        required=False,
        widget=_html_date_widget(),
    )

    def clean(self):
        cleaned = super().clean()
        fecha_desde = cleaned.get("fecha_desde")
        fecha_hasta = cleaned.get("fecha_hasta")

        if fecha_desde and fecha_hasta and fecha_desde > fecha_hasta:
            self.add_error("fecha_hasta", "La fecha final no puede ser menor que la inicial.")

        return cleaned


class AlquilerEdicionForm(forms.ModelForm):
    personas_visibles = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=Alquiler.MAX_PERSONAS,
        widget=forms.HiddenInput(),
    )

    def __init__(self, *args, **kwargs):
        disponibles = kwargs.pop("disponibles", None) or {}
        super().__init__(*args, **kwargs)
        for field_name in ("fecha_reserva", "fecha_entrega", "fecha_devolucion"):
            self.fields[field_name].required = False
        _configurar_campos_prenda(
            self,
            disponibles,
            initial_items=_items_por_slot(self.instance),
            compact_choices=True,
        )
        self.persona_sections = _build_persona_sections(self)
        self.fields["personas_visibles"].initial = getattr(self, "personas_visibles_inicial", 1)

    class Meta:
        model = Alquiler
        fields = _alquiler_form_fields()
        widgets = _alquiler_form_widgets()

    def clean(self):
        cleaned = super().clean()
        for field_name in ("fecha_reserva", "fecha_entrega", "fecha_devolucion"):
            if not cleaned.get(field_name):
                cleaned[field_name] = getattr(self.instance, field_name, None)

        fecha_reserva = cleaned.get("fecha_reserva")
        fecha_entrega = cleaned.get("fecha_entrega")
        fecha_devolucion = cleaned.get("fecha_devolucion")

        if fecha_reserva and fecha_entrega and fecha_reserva > fecha_entrega:
            self.add_error("fecha_entrega", "La entrega no puede ser anterior a la reserva.")

        if fecha_entrega and fecha_devolucion and fecha_entrega > fecha_devolucion:
            self.add_error("fecha_devolucion", "La devolucion no puede ser anterior a la entrega.")

        total = Decimal(cleaned.get("total_bruto") or 0)
        sena = Decimal(cleaned.get("sena") or 0)
        if total < 0:
            self.add_error("total_bruto", "El total no puede ser negativo.")
        if sena < 0:
            self.add_error("sena", "La sena no puede ser negativa.")

        metodo_sena = (cleaned.get("metodo_sena") or "").strip()
        if sena > 0 and not metodo_sena:
            self.add_error("metodo_sena", "Elige el metodo de pago de la sena.")

        selected = _validar_prendas(
            self,
            cleaned,
            fecha_entrega,
            fecha_devolucion,
            exclude_alquiler_id=self.instance.id,
            allow_prenda_ids=self.instance.items.values_list("prenda_id", flat=True),
        )
        if not any(selected[who] for who in PERSONAS_FORM):
            raise ValidationError("Tienes que elegir al menos una prenda.")

        for persona_num in PERSONA_INDICES[1:]:
            who = f"p{persona_num}"
            any_persona = any((cleaned.get(f"{who}_{short}") or "").strip() for short, _ in CATS) or bool(selected[who])
            if any_persona and not (cleaned.get(_persona_name_field(persona_num)) or "").strip():
                self.add_error(
                    _persona_name_field(persona_num),
                    f"Completa el nombre de la persona {persona_num}.",
                )

        return cleaned
