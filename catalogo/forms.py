from django import forms

from .models import Camisa, Chaleco, Cinturon, Combo, Corbata, Traje, Zapato


class CatalogoModelForm(forms.ModelForm):
    MAX_IMAGE_BYTES = 8 * 1024 * 1024

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "ab-inp")
            if isinstance(field, forms.ImageField):
                field.widget.attrs.update({"accept": "image/jpeg,image/png,image/webp,image/heic,image/heif"})

    def clean(self):
        cleaned = super().clean()
        for name, field in self.fields.items():
            if not isinstance(field, forms.ImageField):
                continue
            image = cleaned.get(name)
            if image and getattr(image, "size", 0) > self.MAX_IMAGE_BYTES:
                self.add_error(name, "La imagen supera el máximo de 8 MB.")
            content_type = getattr(image, "content_type", "")
            if image and content_type and not content_type.startswith("image/"):
                self.add_error(name, "El archivo debe ser una imagen válida.")
        return cleaned


class ConVariantesForm(CatalogoModelForm):
    variantes = forms.CharField(
        required=False,
        label="Colores y talles (una variante por línea, separados con |)",
        widget=forms.Textarea(attrs={"class": "ab-inp", "rows": 6}),
        help_text="Ambos: Color | talle saco | talle pantalón. Otros: Color | talle.",
    )
    related_model = None
    related_fields = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["variantes"].initial = "\n".join(
                " | ".join(str(getattr(row, name)) for name in self.related_fields)
                for row in self.instance.talles.all()
            )

    def clean_variantes(self):
        rows = []
        for number, raw in enumerate((self.cleaned_data.get("variantes") or "").splitlines(), 1):
            if not raw.strip():
                continue
            values = [part.strip() for part in raw.split("|")]
            if len(values) != len(self.related_fields) or not all(values):
                raise forms.ValidationError(f"Revisá la línea {number}: formato de variante inválido.")
            rows.append(dict(zip(self.related_fields, values)))
        return rows

    def save(self, commit=True):
        instance = super().save(commit=commit)
        if commit:
            instance.talles.all().delete()
            self.related_model.objects.bulk_create([
                self.related_model(**{self.related_model._meta.get_field(
                    self.related_model._meta.fields[1].name
                ).name: instance}, **row)
                for row in self.cleaned_data["variantes"]
            ])
        return instance


def form_for(model):
    return type(
        f"{model.__name__}Form",
        (CatalogoModelForm,),
        {"Meta": type("Meta", (), {"model": model, "fields": "__all__"})},
    )


MODEL_FORMS = {
    model._meta.model_name: form_for(model)
    for model in (Traje, Chaleco, Cinturon, Corbata, Camisa, Zapato, Combo)
}

from .models import TalleColorCamisa, TalleColorChaleco, TalleColorTraje, TalleColorZapato


def variant_form(model, related_model, fields):
    return type(
        f"{model.__name__}VariantesForm",
        (ConVariantesForm,),
        {
            "related_model": related_model,
            "related_fields": fields,
            "Meta": type("Meta", (), {"model": model, "fields": "__all__"}),
        },
    )


MODEL_FORMS.update({
    "traje": variant_form(Traje, TalleColorTraje, ("color", "talle_saco", "talle_pantalon")),
    "chaleco": variant_form(Chaleco, TalleColorChaleco, ("color", "talle")),
    "camisa": variant_form(Camisa, TalleColorCamisa, ("color", "talle")),
    "zapato": variant_form(Zapato, TalleColorZapato, ("color", "talle")),
})
