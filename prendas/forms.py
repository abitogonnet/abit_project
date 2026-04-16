from django import forms

from .models import Prenda


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
    "Beige",
    "Negro",
    "Azul oscuro",
    "Azul francia",
    "Gris perla",
    "Gris oscuro",
    "Celeste",
    "Verde oscuro",
    "Pistacho",
    "Rosa",
    "Violeta",
    "Bordo",
    "Marron",
    "Blanco",
]

COLORES_ZAPATOS = ["Negro", "Marron"]
COLORES_CHALECO = ["Gris", "Negro", "Azul oscuro", "Azul francia"]
COLORES_GENERALES = []
for _color in COLORES_TRAJE + COLORES_ZAPATOS + COLORES_CHALECO:
    if _color not in COLORES_GENERALES:
        COLORES_GENERALES.append(_color)

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

PANTALON_NUM = _nums(0, 70, 1)
ZAPATOS_NUM = _nums(36, 46, 1)

GENERIC_NUM = _nums(0, 76, 1)
GENERIC_TALLES = GENERIC_NUM + LETRAS_XS_5XL


def color_options_for(categoria: str):
    if categoria in {Prenda.C_ZAPATOS, Prenda.C_CINTURON}:
        return COLORES_ZAPATOS
    if categoria == Prenda.C_CHALECO:
        return COLORES_CHALECO
    if categoria in {Prenda.C_SACO, Prenda.C_PANTALON, Prenda.C_CAMISA}:
        return COLORES_TRAJE
    if categoria in {Prenda.C_MONO, Prenda.C_CORBATA}:
        return COLORES_GENERALES
    return []


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
        if marca_cf == "boiler":
            return _unique(BOILER_SACO_NUM + LETRAS_XS_5XL + LETRAS_XS_4XL)
        if marca_cf == "aires modernos":
            return AIRES_SACO_NUM
        return _unique(GENERIC_TALLES + LETRAS_XS_4XL)
    if categoria == Prenda.C_CAMISA:
        return GENERIC_TALLES
    return []


def requiere_origen(categoria: str, marca: str) -> bool:
    return categoria in {Prenda.C_SACO, Prenda.C_PANTALON} and _norm(marca).casefold() == "aires modernos"


class PrendaForm(forms.ModelForm):
    categoria = forms.ChoiceField(required=True)
    marca = forms.ChoiceField(required=False)
    color = forms.ChoiceField(required=False)
    talle = forms.ChoiceField(required=False)
    origen = forms.ChoiceField(required=False)
    notas = forms.CharField(required=False)

    class Meta:
        model = Prenda
        fields = ["categoria", "marca", "color", "talle", "origen", "notas"]
        widgets = {
            "categoria": forms.Select(attrs={"class": "ab-sel", "id": "id_categoria"}),
            "marca": forms.Select(attrs={"class": "ab-sel", "id": "id_marca"}),
            "color": forms.Select(attrs={"class": "ab-sel", "id": "id_color"}),
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
        self.fields["color"].choices = _choices(
            color_options_for(current_categoria),
            "Elegir color",
            current=current_color,
        )
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

    def clean(self):
        cleaned = super().clean()
        cat = cleaned.get("categoria")
        marca = cleaned.get("marca", "")
        color = _norm(cleaned.get("color", ""))
        talle = _norm(cleaned.get("talle", ""))
        origen = _norm(cleaned.get("origen", ""))

        if cat in {Prenda.C_MONO, Prenda.C_CORBATA}:
            if talle not in TAM_NINO_ADULTO:
                self.add_error("talle", "Para mono/corbata, elegi Niño o Adulto.")
            return cleaned

        if cat == Prenda.C_CINTURON:
            if color not in COLORES_ZAPATOS:
                self.add_error("color", "Para cinturon, elegi Negro o Marron.")
            if talle not in TAM_NINO_ADULTO:
                self.add_error("talle", "Para cinturon, elegi Niño o Adulto.")
            return cleaned

        if cat == Prenda.C_ZAPATOS:
            if color not in COLORES_ZAPATOS:
                self.add_error("color", "Para zapatos, elegi Negro o Marron.")
            if talle not in ZAPATOS_NUM:
                self.add_error("talle", "Para zapatos, elegi un talle entre 36 y 46.")
            return cleaned

        if cat == Prenda.C_PANTALON:
            if color not in COLORES_TRAJE:
                self.add_error("color", "Para pantalon, elegi un color del desplegable.")
            if talle not in PANTALON_NUM:
                self.add_error("talle", "Para pantalon, elegi un talle entre 0 y 70.")
            if requiere_origen(cat, marca) and origen not in dict(Prenda.ORIGENES):
                self.add_error("origen", "Para Aires Modernos elegi si es nacional o importado.")
            if not requiere_origen(cat, marca):
                cleaned["origen"] = ""
            return cleaned

        if cat == Prenda.C_CHALECO:
            if color not in COLORES_CHALECO:
                self.add_error("color", "Para chaleco, elegi Gris, Negro, Azul oscuro o Azul francia.")
            if talle not in talle_options_for(cat, marca):
                self.add_error("talle", "Para chaleco, elegi un talle valido del desplegable.")
            cleaned["origen"] = ""
            return cleaned

        if cat == Prenda.C_SACO:
            if color not in COLORES_TRAJE:
                self.add_error("color", "Para saco, elegi un color del desplegable.")
            if talle not in talle_options_for(cat, marca):
                self.add_error("talle", "Para saco, elegi un talle valido del desplegable.")
            if requiere_origen(cat, marca) and origen not in dict(Prenda.ORIGENES):
                self.add_error("origen", "Para Aires Modernos elegi si es nacional o importado.")
            if not requiere_origen(cat, marca):
                cleaned["origen"] = ""
            return cleaned

        if cat == Prenda.C_CAMISA:
            if color not in COLORES_TRAJE:
                self.add_error("color", "Para camisa, elegi un color del desplegable.")
            if talle not in GENERIC_TALLES:
                self.add_error("talle", "Para camisa, elegi un talle valido del desplegable.")
            cleaned["origen"] = ""
            return cleaned

        cleaned["origen"] = ""
        return cleaned


class BuscarPrendaForm(forms.Form):
    marca = forms.ChoiceField(required=False)
    talle = forms.ChoiceField(required=False)

    def __init__(self, *args, **kwargs):
        marcas = kwargs.pop("marcas", [])
        talles = kwargs.pop("talles", [])
        super().__init__(*args, **kwargs)
        self.fields["marca"].choices = _choices(marcas, "Todas las marcas", current=self._bound("marca"))
        self.fields["talle"].choices = _choices(talles, "Todos los talles", current=self._bound("talle"))
        self.fields["marca"].widget.attrs.update({"class": "ab-sel"})
        self.fields["talle"].widget.attrs.update({"class": "ab-sel"})

    def _bound(self, name: str) -> str:
        return _norm(self.data.get(name, "")) if self.is_bound else ""
