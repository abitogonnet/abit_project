import logging

from django import forms

from .image_utils import normalize_uploaded_image
from .stock_colors import stock_colors_for_model
from .models import (
    Camisa,
    Chaleco,
    Cinturon,
    Combo,
    Corbata,
    ImagenTraje,
    TalleColorCamisa,
    TalleColorChaleco,
    TalleColorTraje,
    TalleColorZapato,
    Traje,
    Zapato,
)

logger = logging.getLogger(__name__)

IMAGE_ERROR = (
    "No pudimos procesar esta imagen. Probá con otra foto o con un archivo "
    "JPG, PNG, WEBP, HEIC o HEIF."
)
IMAGE_ACCEPT = (
    "image/*,image/jpeg,image/png,image/webp,image/heic,image/heif,"
    ".jpg,.jpeg,.png,.webp,.heic,.heif"
)


class CatalogImageField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault(
            "widget",
            forms.ClearableFileInput(
                attrs={"class": "ab-inp", "accept": IMAGE_ACCEPT}
            ),
        )
        super().__init__(*args, **kwargs)

    def to_python(self, data):
        uploaded = super().to_python(data)
        if uploaded is None:
            return None
        try:
            return normalize_uploaded_image(
                uploaded,
                fallback_name=self.label or "imagen-catalogo",
            )
        except Exception:
            logger.exception(
                "No se pudo procesar imagen de catálogo: nombre=%r tamaño=%r "
                "content_type=%r campo=%r",
                getattr(uploaded, "name", ""),
                getattr(uploaded, "size", None),
                getattr(uploaded, "content_type", ""),
                self.label,
            )
            raise forms.ValidationError(
                f"{getattr(uploaded, 'name', 'archivo')}: {IMAGE_ERROR}",
                code="invalid_catalog_image",
            )


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleCatalogImageField(forms.Field):
    widget = MultipleFileInput(
        attrs={"class": "ab-inp", "accept": IMAGE_ACCEPT}
    )

    def clean(self, data):
        files = data if isinstance(data, (list, tuple)) else ([data] if data else [])
        cleaned = []
        errors = []
        image_field = CatalogImageField(required=True, label=self.label)
        for uploaded in files:
            try:
                cleaned.append(image_field.clean(uploaded))
            except forms.ValidationError as exc:
                errors.extend(exc.error_list)
        if errors:
            raise forms.ValidationError(errors)
        return cleaned


class CatalogoModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "colores_stock" in self.fields:
            self.fields["colores_stock"].queryset = stock_colors_for_model(self._meta.model)
            self.fields["colores_stock"].widget = forms.CheckboxSelectMultiple()
            self.fields["colores_stock"].help_text = (
                "Elegí colores existentes en Stock. Los talles se vinculan "
                "automáticamente por color y se actualizan con el inventario."
            )
        for name, field in list(self.fields.items()):
            if isinstance(field, forms.ImageField):
                self.fields[name] = CatalogImageField(
                    required=field.required,
                    label=field.label,
                    help_text=field.help_text,
                    initial=field.initial,
                )
                field = self.fields[name]
            field.widget.attrs.setdefault("class", "ab-inp")


class ConVariantesForm(CatalogoModelForm):
    variantes = forms.CharField(
        required=False,
        label="Colores y talles (una variante por línea, separados con |)",
        widget=forms.Textarea(attrs={"class": "ab-inp", "rows": 6}),
        help_text="Trajes: Color | talle saco | talle pantalón. Otros: Color | talle.",
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
        for number, raw in enumerate(
            (self.cleaned_data.get("variantes") or "").splitlines(), 1
        ):
            if not raw.strip():
                continue
            values = [part.strip() for part in raw.split("|")]
            if len(values) != len(self.related_fields) or not all(values):
                raise forms.ValidationError(
                    f"Revisá la línea {number}: formato de variante inválido."
                )
            rows.append(dict(zip(self.related_fields, values)))
        return rows

    def save(self, commit=True):
        instance = super().save(commit=commit)
        if commit:
            instance.talles.all().delete()
            parent_field = self.related_model._meta.fields[1].name
            self.related_model.objects.bulk_create([
                self.related_model(**{parent_field: instance}, **row)
                for row in self.cleaned_data["variantes"]
            ])
        return instance


def form_for(model):
    return type(
        f"{model.__name__}Form",
        (CatalogoModelForm,),
        {"Meta": type("Meta", (), {"model": model, "fields": "__all__"})},
    )


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


MODEL_FORMS = {
    model._meta.model_name: form_for(model)
    for model in (Traje, Chaleco, Cinturon, Corbata, Camisa, Zapato, Combo)
}


class TrajeForm(CatalogoModelForm):
    imagenes_galeria = MultipleCatalogImageField(
        required=False,
        label="Imágenes adicionales / galería",
    )

    class Meta:
        model = Traje
        fields = [
            "tela",
            "descripcion",
            "linea",
            "color_stock",
            "precio",
            "foto_modelo",
            "foto_colgado",
            "activo",
        ]
        labels = {
            "tela": "Nombre / modelo y tela",
            "color_stock": "Color stock",
            "precio": "Precio del traje",
            "foto_modelo": "Foto principal",
            "foto_colgado": "Foto colgado",
            "activo": "Publicado",
        }

    def save(self, commit=True):
        instance = super().save(commit=commit)
        self.saved_gallery_images = []
        if commit:
            inicio = instance.imagenes_galeria.count()
            for index, image in enumerate(
                self.cleaned_data.get("imagenes_galeria") or []
            ):
                gallery = ImagenTraje.objects.create(
                    traje=instance,
                    imagen=image,
                    orden=inicio + index,
                )
                self.saved_gallery_images.append(gallery.imagen)
        return instance


MODEL_FORMS["traje"] = TrajeForm
