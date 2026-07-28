from django import forms

from .models import Color, Prenda


BRANDS = [
    "Boiler",
    "Aires Modernos",
    "Sportfino",
    "HYM",
    "Zara",
    "Rochas",
    "Calvin Klein",
    "Calvin Klain",
    "Edmonds",
    "Rosatti",
    "Ralph Laurent",
    "Abito",
    "Sin marca",
]

COLORES_TRAJE = [
    "Azul Oscuro",
    "Azul Francia",
    "Blanca",
    "Gris Perla",
    "Gris Topo",
    "Celeste",
    "Rosa",
    "Verde Pistacho",
    "Verde Oscuro",
    "Petroleo",
    "Bordo",
    "Violeta",
    "Beige",
    "Marron",
    "Negro",
]

COLORES_ZAPATOS = ["Negro", "Marron"]
COLORES_CHALECO = ["Gris", "Negro", "Azul Oscuro", "Azul Francia"]
COLORES_GENERALES = []
for _color in COLORES_TRAJE + COLORES_ZAPATOS + COLORES_CHALECO:
    if _color not in COLORES_GENERALES:
        COLORES_GENERALES.append(_color)

COLORES_RESTRINGIDOS_POR_CATEGORIA = {
    Prenda.C_SACO: COLORES_TRAJE,
    Prenda.C_PANTALON: COLORES_TRAJE,
    Prenda.C_CAMISA: COLORES_TRAJE,
    Prenda.C_ZAPATOS: COLORES_ZAPATOS,
    Prenda.C_CINTURON: COLORES_ZAPATOS,
}

TAM_NINO_ADULTO = ["Niño", "Adulto"]


def _norm(s: str) -> str:
    return (s or "").strip()


def _nums(a: int, b: int, step: int = 1):
    return [str(x) for x in range(a, b + 1, step)]


def _unique(seq):
    out = []
    for item in seq:
        if item not in out:
            out.append(item)
    return out


def _choices(options, placeholder, current=""):
    clean_current = _norm(current)
    base = list(options)
    if clean_current and clean_current not in base:
        base = [clean_current] + base
    return [("", placeholder)] + [(opt, opt) for opt in base]


BOILER_SACO_NUM = _nums(4, 16, 2)
BOILER_CHAL_NUM = _nums(0, 16, 2)

LETRAS_XS_5XL = ["XXS", "XS", "S", "M", "L", "XL", "2XL", "3XL", "4XL", "5XL"]
LETRAS_XS_4XL = ["XS", "S", "M", "L", "XL", "2XL", "3XL", "4XL"]

AIRES_SACO_NUM = _nums(22, 76, 2)
AIRES_CHAL_NUM = _nums(22, 70, 2)

SACO_TALLES = _nums(2, 16, 2) + ["XS", "S", "M", "L", "XL", "2XL", "3XL", "4XL", "5XL"] + _nums(50, 74, 2)
CAMISA_TALLES = (
    _nums(2, 16, 2)
    + ["XS", "S", "M", "L", "XL", "2XL", "3XL"]
    + _nums(40, 80, 2)
)
CAMISA_SACO_TALLES = SACO_TALLES
PANTALON_NUM = _nums(2, 74, 2)
ZAPATOS_NUM = _nums(30, 50, 2)

GENERIC_NUM = _nums(0, 76, 1)
GENERIC_TALLES = GENERIC_NUM + LETRAS_XS_5XL


def color_options_for(categoria: str):
    if categoria in {
        Prenda.C_SACO, Prenda.C_PANTALON, Prenda.C_CAMISA,
        Prenda.C_ZAPATOS, Prenda.C_CINTURON,
    }:
        catalogo = list(Color.objects.values_list("nombre", flat=True))
        return catalogo or COLORES_GENERALES
    if categoria == Prenda.C_CHALECO:
        return COLORES_CHALECO
    if categoria == Prenda.C_CAMISA:
        return COLORES_TRAJE
    if categoria in {Prenda.C_MONO, Prenda.C_CORBATA}:
        return COLORES_GENERALES
    return []


def restricted_color_options_for(categoria: str):
    return color_options_for(categoria) if categoria in {
        Prenda.C_SACO, Prenda.C_PANTALON, Prenda.C_CAMISA,
        Prenda.C_ZAPATOS, Prenda.C_CINTURON,
    } else []


def talle_options_for(categoria: str, marca: str):
    marca_cf = _norm(marca).casefold()

    if categoria in {Prenda.C_MONO, Prenda.C_CORBATA, Prenda.C_CINTURON}:
        return TAM_NINO_ADULTO
    if categoria == Prenda.C_ZAPATOS:
        return ZAPATOS_NUM
    if categoria == Prenda.C_PANTALON:
        return PANTALON_NUM
    if categoria == Prenda.C_CHALECO:
        if marca_cf == "boiler":
            return _unique(BOILER_CHAL_NUM + LETRAS_XS_5XL + LETRAS_XS_4XL)
        if marca_cf == "aires modernos":
            return AIRES_CHAL_NUM
        return _unique(GENERIC_TALLES + LETRAS_XS_4XL)
    if categoria == Prenda.C_SACO:
        return SACO_TALLES
    if categoria == Prenda.C_CAMISA:
        return CAMISA_TALLES
    return []


def requiere_origen(categoria: str, marca: str) -> bool:
    return bool(categoria)


class PrendaForm(forms.ModelForm):
    categoria = forms.ChoiceField(required=True)
    marca = forms.ChoiceField(required=False)
    color = forms.CharField(required=False)
    talle = forms.ChoiceField(required=False)
    origen = forms.ChoiceField(required=False)
    notas = forms.CharField(required=False)

    class Meta:
        model = Prenda
        fields = ["categoria", "marca", "color", "talle", "origen", "notas"]
        widgets = {
            "categoria": forms.Select(attrs={"class": "ab-sel", "id": "id_categoria"}),
            "marca": forms.Select(attrs={"class": "ab-sel", "id": "id_marca"}),
            "color": forms.TextInput(
                attrs={
                    "class": "ab-inp",
                    "id": "id_color",
                    "placeholder": "Escribir color",
                    "autocomplete": "off",
                }
            ),
            "talle": forms.Select(attrs={"class": "ab-sel", "id": "id_talle"}),
            "origen": forms.Select(attrs={"class": "ab-sel", "id": "id_origen"}),
            "notas": forms.TextInput(attrs={"class": "ab-inp", "placeholder": "Opcional"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        current_categoria = self._bound_or_initial("categoria")
        current_marca = self._bound_or_initial("marca")
        current_color = self._bound_or_initial("color")
        current_talle = self._bound_or_initial("talle")
        current_origen = self._bound_or_initial("origen")

        self.fields["categoria"].choices = [("", "Elegir categoria")] + list(Prenda.CATEGORIAS)
        self.fields["marca"].choices = _choices(BRANDS, "Elegir marca", current=current_marca)
        self.fields["color"].initial = current_color
        self.fields["color"].widget.attrs["placeholder"] = "Escribir color"
        self.fields["talle"].choices = _choices(
            talle_options_for(current_categoria, current_marca),
            "Elegir talle",
            current=current_talle,
        )

        if requiere_origen(current_categoria, current_marca):
            self.fields["origen"].choices = [("", "Elegir origen")] + list(Prenda.ORIGENES)
        else:
            self.fields["origen"].choices = _choices([], "No aplica", current=current_origen)

    def _bound_or_initial(self, name: str) -> str:
        if self.is_bound:
            return _norm(self.data.get(name, ""))
        if self.instance and self.instance.pk:
            return _norm(getattr(self.instance, name, ""))
        return _norm(self.initial.get(name, ""))

    def clean_marca(self):
        marca = _norm(self.cleaned_data.get("marca", ""))
        if not marca:
            return ""
        if marca.casefold() == "calvin klain":
            return "Calvin Klein"
        return marca

    def clean_color(self):
        categoria = self._bound_or_initial("categoria")
        color = _norm(self.cleaned_data.get("color", ""))
        if categoria in COLORES_RESTRINGIDOS_POR_CATEGORIA:
            normalized = Prenda.normalize_color_value(color, categoria)
            catalogado = Color.objects.filter(clave_normalizada=Color.normalizar_clave(normalized)).first()
            return catalogado.nombre if catalogado else color
        return Prenda.normalize_color_value(color, categoria)

    def clean(self):
        cleaned = super().clean()
        cat = cleaned.get("categoria")
        marca = cleaned.get("marca", "")
        color = _norm(cleaned.get("color", ""))
        if cat in COLORES_RESTRINGIDOS_POR_CATEGORIA:
            normalized = Prenda.normalize_color_value(color, cat)
            catalogado = Color.objects.filter(clave_normalizada=Color.normalizar_clave(normalized)).first()
            color = catalogado.nombre if catalogado else color
        else:
            color = Prenda.normalize_color_value(color, cat)
        talle = _norm(cleaned.get("talle", ""))
        origen = _norm(cleaned.get("origen", ""))
        cleaned["color"] = color

        if cat in {Prenda.C_SACO, Prenda.C_PANTALON, Prenda.C_CAMISA, Prenda.C_ZAPATOS, Prenda.C_CINTURON}:
            colores_validos = set(restricted_color_options_for(cat))
            if not color:
                self.add_error("color", "Elegí un color del catálogo.")
            elif color not in colores_validos:
                self.add_error("color", "Elegí un color válido del catálogo.")

        if origen not in dict(Prenda.ORIGENES):
            self.add_error("origen", "Elegí si la prenda es nacional o importada.")

        if cat == Prenda.C_MONO:
            if talle not in TAM_NINO_ADULTO:
                self.add_error("talle", "Para mono/corbata, elegi Niño o Adulto.")
            return cleaned

        if cat == Prenda.C_CORBATA:
            if talle not in TAM_NINO_ADULTO:
                self.add_error("talle", "Para mono/corbata, elegi Niño o Adulto.")
            return cleaned

        if cat == Prenda.C_CINTURON:
            if talle not in TAM_NINO_ADULTO:
                self.add_error("talle", "Para cinturon, elegi Niño o Adulto.")
            return cleaned

        if cat == Prenda.C_ZAPATOS:
            if talle not in ZAPATOS_NUM:
                self.add_error("talle", "Para zapatos, elegí un talle par entre 30 y 50.")
            return cleaned

        if cat == Prenda.C_PANTALON:
            if talle not in PANTALON_NUM:
                self.add_error("talle", "Para pantalón, elegí un talle par entre 2 y 74.")
            return cleaned

        if cat == Prenda.C_CHALECO:
            if talle not in talle_options_for(cat, marca):
                self.add_error("talle", "Para chaleco, elegi un talle valido del desplegable.")
            return cleaned

        if cat == Prenda.C_SACO:
            if talle not in talle_options_for(cat, marca):
                self.add_error("talle", "Para saco, elegi un talle valido del desplegable.")
            return cleaned

        if cat == Prenda.C_CAMISA:
            talle_historico_sin_cambios = (
                self.instance
                and self.instance.pk
                and talle == _norm(self.instance.talle)
            )
            if talle not in CAMISA_TALLES and not talle_historico_sin_cambios:
                self.add_error("talle", "Para camisa, elegi un talle valido del desplegable.")
            return cleaned

        return cleaned


class ColorForm(forms.ModelForm):
    class Meta:
        model = Color
        fields = ["nombre"]

    def clean_nombre(self):
        nombre = " ".join((self.cleaned_data.get("nombre") or "").split())
        if not nombre:
            raise forms.ValidationError("Ingresá un nombre de color.")
        clave = Color.normalizar_clave(nombre)
        if Color.objects.filter(clave_normalizada=clave).exists():
            raise forms.ValidationError("Ese color ya existe.")
        return nombre


class BuscarPrendaForm(forms.Form):
    categoria = forms.ChoiceField(required=False)
    marca = forms.ChoiceField(required=False)
    color = forms.ChoiceField(required=False)
    talle = forms.ChoiceField(required=False)
    origen = forms.ChoiceField(required=False)

    def __init__(self, *args, **kwargs):
        marcas = kwargs.pop("marcas", [])
        colores = kwargs.pop("colores", [])
        talles = kwargs.pop("talles", [])
        super().__init__(*args, **kwargs)
        self.fields["categoria"].choices = [("", "Todas las prendas")] + list(Prenda.CATEGORIAS)
        self.fields["marca"].choices = _choices(marcas, "Todas las marcas", current=self._bound("marca"))
        self.fields["color"].choices = _choices(colores, "Todos los colores", current=self._bound("color"))
        self.fields["talle"].choices = _choices(talles, "Todos los talles", current=self._bound("talle"))
        self.fields["origen"].choices = [("", "Nacional o importado")] + list(Prenda.ORIGENES)
        self.fields["categoria"].widget.attrs.update({"class": "ab-sel"})
        self.fields["marca"].widget.attrs.update({"class": "ab-sel"})
        self.fields["color"].widget.attrs.update({"class": "ab-sel"})
        self.fields["talle"].widget.attrs.update({"class": "ab-sel"})
        self.fields["origen"].widget.attrs.update({"class": "ab-sel", "id": "id_origen"})

    def _bound(self, name: str) -> str:
        return _norm(self.data.get(name, "")) if self.is_bound else ""

    def clean_color(self):
        categoria = _norm(self.cleaned_data.get("categoria", "")) or _norm(self.data.get("categoria", ""))
        return Prenda.normalize_color_value(_norm(self.cleaned_data.get("color", "")), categoria)
