from django import forms
from .models import Prenda

# ===========================
# Listas “oficiales” (datalist)
# ===========================
BRANDS = [
    "Boiler",
    "Aires Modernos",  # ✅ dejamos solo este
    "HYM",
    "Zara",
    "Rochas",
    "Calvin Klein",
    "Calvin Klain",   # lo incluyo porque vos lo escribiste así
    "Edmonds",
    "Rosatti",
    "Ralph Laurent",
    "Abito",
    "Sin marca",
]

COLORES_TRAJE = [
    "Beige","Negro","Azul oscuro","Azul francia","Gris perla","Gris oscuro",
    "Celeste","Verde oscuro","Pistacho","Rosa","Violeta","Bordo","Marron",
    "Blanco"
]

COLORES_ZAPATOS = ["Negro","Marron"]
COLORES_CHALECO = ["Gris","Negro","Azul oscuro","Azul francia"]

TAM_NINO_ADULTO = ["Niño","Adulto"]

def _norm(s: str) -> str:
    return (s or "").strip()

def _in_list(val: str, options: list[str]) -> bool:
    v = _norm(val).casefold()
    return any(v == o.casefold() for o in options)

def _nums(a:int,b:int,step:int=1):
    return [str(x) for x in range(a, b+1, step)]

BOILER_SACO_NUM = _nums(4, 16, 2)
BOILER_CHAL_NUM = _nums(0, 16, 2)

LETRAS_XS_5XL = ["XXS","XS","S","M","L","XL","2XL","3XL","4XL","5XL"]
LETRAS_XS_4XL = ["XS","S","M","L","XL","2XL","3XL","4XL"]  # por lo que mencionaste

AIRES_SACO_NUM = _nums(22, 76, 2)
AIRES_CHAL_NUM = _nums(22, 70, 2)

PANTALON_NUM = _nums(0, 70, 1)
ZAPATOS_NUM = _nums(36, 46, 1)

GENERIC_NUM = _nums(0, 76, 1)
GENERIC_TALLES = GENERIC_NUM + LETRAS_XS_5XL


class PrendaForm(forms.ModelForm):
    class Meta:
        model = Prenda
        fields = ["categoria", "marca", "color", "talle", "notas"]

        widgets = {
            "categoria": forms.Select(attrs={"class":"ab-sel", "id":"id_categoria"}),
            "marca": forms.TextInput(attrs={"class":"ab-inp", "id":"id_marca", "list":"dl_marcas", "autocomplete":"off"}),
            "color": forms.TextInput(attrs={"class":"ab-inp", "id":"id_color", "list":"dl_colores", "autocomplete":"off"}),
            "talle": forms.TextInput(attrs={"class":"ab-inp", "id":"id_talle", "list":"dl_talles", "autocomplete":"off"}),
            "notas": forms.TextInput(attrs={"class":"ab-inp", "placeholder":"Opcional"}),
        }

    def clean_marca(self):
        marca = _norm(self.cleaned_data.get("marca", ""))
        if marca == "":
            return ""

        # ✅ si escriben "Aires", lo normalizamos a "Aires Modernos"
        if marca.casefold() == "aires".casefold():
            marca = "Aires Modernos"

        if not _in_list(marca, BRANDS):
            raise forms.ValidationError("La marca debe ser una opción del desplegable.")

        # normalizo “Calvin Klain” a “Calvin Klein”
        if marca.casefold() == "calvin klain".casefold():
            return "Calvin Klein"

        return marca

    def clean(self):
        cleaned = super().clean()
        cat = cleaned.get("categoria")
        marca = cleaned.get("marca", "")
        color = _norm(cleaned.get("color", ""))
        talle = _norm(cleaned.get("talle", ""))

        # 1) Moño / Corbata -> color libre, talle Niño/Adulto obligatorio
        if cat in [Prenda.C_MONO, Prenda.C_CORBATA]:
            if talle == "" or not _in_list(talle, TAM_NINO_ADULTO):
                self.add_error("talle", "Para moño/corbata, el talle debe ser Niño o Adulto (del desplegable).")
            return cleaned

        # 2) Cinturón -> color Negro/Marron y talle Niño/Adulto
        if cat == Prenda.C_CINTURON:
            if color == "" or not _in_list(color, COLORES_ZAPATOS):
                self.add_error("color", "Para cinturón, el color debe ser Negro o Marron (del desplegable).")
            if talle == "" or not _in_list(talle, TAM_NINO_ADULTO):
                self.add_error("talle", "Para cinturón, el talle debe ser Niño o Adulto (del desplegable).")
            return cleaned

        # 3) Zapatos -> color Negro/Marron y talle 36-46
        if cat == Prenda.C_ZAPATOS:
            if color == "" or not _in_list(color, COLORES_ZAPATOS):
                self.add_error("color", "Para zapatos, el color debe ser Negro o Marron (del desplegable).")
            if talle == "" or talle not in ZAPATOS_NUM:
                self.add_error("talle", "Para zapatos, el talle debe estar entre 36 y 46 (del desplegable).")
            return cleaned

        # 4) Pantalón -> colores traje y talle 0-70
        if cat == Prenda.C_PANTALON:
            if color == "" or not _in_list(color, COLORES_TRAJE):
                self.add_error("color", "Para pantalón, el color debe ser del desplegable.")
            if talle == "" or talle not in PANTALON_NUM:
                self.add_error("talle", "Para pantalón, el talle debe ser 0 a 70 (del desplegable).")
            return cleaned

        # 5) Chaleco -> color limitado; talle depende marca
        if cat == Prenda.C_CHALECO:
            if color == "" or not _in_list(color, COLORES_CHALECO):
                self.add_error("color", "Para chaleco, el color debe ser Gris/Negro/Azul oscuro/Azul francia.")

            if marca.casefold() == "boiler".casefold():
                allowed = BOILER_CHAL_NUM + LETRAS_XS_5XL + LETRAS_XS_4XL
                if talle == "" or talle not in allowed:
                    self.add_error("talle", "Chaleco Boiler: talle 0-16 (de 2 en 2) o letras (XXS a 5XL).")

            elif marca.casefold() == "aires modernos".casefold():
                if talle == "" or talle not in AIRES_CHAL_NUM:
                    self.add_error("talle", "Chaleco Aires Modernos: talle 22 a 70 (de 2 en 2).")

            else:
                if talle == "" or talle not in GENERIC_TALLES:
                    self.add_error("talle", "Chaleco: elegí un talle del desplegable (numérico o letras).")
            return cleaned

        # 6) Saco -> color traje; talle depende marca
        if cat == Prenda.C_SACO:
            if color == "" or not _in_list(color, COLORES_TRAJE):
                self.add_error("color", "Para saco, el color debe ser del desplegable.")

            if marca.casefold() == "boiler".casefold():
                allowed = BOILER_SACO_NUM + LETRAS_XS_5XL + LETRAS_XS_4XL
                if talle == "" or talle not in allowed:
                    self.add_error("talle", "Saco Boiler: talle 4-16 (de 2 en 2) o letras (XXS a 5XL).")

            elif marca.casefold() == "aires modernos".casefold():
                if talle == "" or talle not in AIRES_SACO_NUM:
                    self.add_error("talle", "Saco Aires Modernos: talle 22 a 76 (de 2 en 2).")

            else:
                if talle == "" or talle not in GENERIC_TALLES:
                    self.add_error("talle", "Saco: elegí un talle del desplegable (numérico o letras).")
            return cleaned

        # 7) Camisa (default): color del desplegable, talle letras o numérico genérico
        if cat == Prenda.C_CAMISA:
            if color == "" or not _in_list(color, COLORES_TRAJE):
                self.add_error("color", "Para camisa, elegí un color del desplegable.")
            if talle == "" or talle not in GENERIC_TALLES:
                self.add_error("talle", "Para camisa, elegí un talle del desplegable (numérico o letras).")
            return cleaned

        return cleaned
