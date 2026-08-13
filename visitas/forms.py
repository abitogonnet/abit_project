from datetime import date, time, timedelta

from django import forms

from catalogo.models import Camisa, Chaleco, Cinturon, Combo, Corbata, Traje, Zapato

from .models import BloqueoAgenda, PreferenciaAmboVisita, Visita


HORARIOS_VALIDOS = [
    time(17, 0),
    time(17, 30),
    time(18, 0),
    time(18, 30),
    time(19, 0),
    time(19, 30),
]


class VisitaForm(forms.ModelForm):
    vio_prendas_catalogo = forms.ChoiceField(
        choices=[
            ("", "Elegi una opcion"),
            ("no", "No, todavia no vi ninguna"),
            ("si", "Sí, quiero seleccionar productos"),
        ],
        required=False,
        widget=forms.Select(attrs={"class": "reserve-input"}),
        label="¿Viste algún traje o combo en nuestro catálogo?",
    )

    class Meta:
        model = Visita
        fields = [
            "cantidad_personas",
            "fecha_evento",
            "fecha_visita",
            "hora_visita",
            "nombre",
            "telefono",
            "dni",
        ]
        widgets = {
            "cantidad_personas": forms.Select(
                attrs={"class": "reserve-input"},
                choices=[
                    (1, "1 persona"),
                    (2, "2 personas"),
                    (3, "3 personas"),
                ],
            ),
            "fecha_evento": forms.DateInput(
                attrs={"type": "date", "class": "reserve-input"}
            ),
            "fecha_visita": forms.DateInput(
                attrs={"type": "date", "class": "reserve-input"}
            ),
            "hora_visita": forms.HiddenInput(),
            "nombre": forms.TextInput(attrs={"class": "reserve-input"}),
            "telefono": forms.TextInput(attrs={"class": "reserve-input"}),
            "dni": forms.TextInput(attrs={"class": "reserve-input"}),
        }
        labels = {
            "cantidad_personas": "Cantidad de personas",
            "fecha_evento": "Fecha del evento",
            "fecha_visita": "Dia para la visita",
            "hora_visita": "Horario",
            "nombre": "Nombre",
            "telefono": "Celular",
            "dni": "DNI",
        }

    def __init__(self, *args, **kwargs):
        self.trajes_catalogo = list(Traje.objects.filter(activo=True).select_related("color_stock").prefetch_related("colores_stock").order_by("linea", "tela"))
        self.productos_catalogo = []
        for obj in self.trajes_catalogo:
            self.productos_catalogo.append((f"traje:{obj.pk}", f"Traje {obj.get_linea_display()} — {obj.tela}", obj))
        for model, tipo in ((Combo, "combo"), (Camisa, "camisa"), (Zapato, "zapato"), (Chaleco, "chaleco"), (Corbata, "corbata"), (Cinturon, "cinturon")):
            qs = model.objects.filter(activo=True)
            if hasattr(model, "colores_stock"):
                qs = qs.prefetch_related("colores_stock")
            for obj in qs:
                nombre = obj.nombre if tipo == "combo" else (obj.descripcion or f"{model._meta.verbose_name.title()} #{obj.pk}")
                self.productos_catalogo.append((f"{tipo}:{obj.pk}", nombre, obj))

        super().__init__(*args, **kwargs)

        hoy = date.today().isoformat()
        self.fields["fecha_evento"].widget.attrs["min"] = hoy
        self.fields["fecha_visita"].widget.attrs["min"] = hoy

        for index in range(1, 4):
            self.fields[f"preferencia_{index}_traje"] = forms.ChoiceField(
                choices=[("", "Elegí un producto")] + [(key, name) for key, name, obj in self.productos_catalogo],
                required=False,
                widget=forms.Select(attrs={"class": "reserve-input"}),
                label=f"Producto {index}",
            )
            self.fields[f"preferencia_{index}_color"] = forms.ChoiceField(
                required=False,
                choices=[("", "Elegi un color")],
                widget=forms.Select(attrs={"class": "reserve-input"}),
                label=f"Color del traje {index}",
            )
            self.fields[f"preferencia_{index}_talle_saco"] = forms.CharField(required=False, widget=forms.HiddenInput())
            self.fields[f"preferencia_{index}_talle_pantalon"] = forms.CharField(required=False, widget=forms.HiddenInput())

        if self.is_bound:
            for index in range(1, 4):
                field_name = f"preferencia_{index}_color"
                traje_id = self.data.get(f"preferencia_{index}_traje") or ""
                self.fields[field_name].choices = self._color_choices(traje_id)

        self.selected_preferences = []

    def _color_choices(self, traje_id):
        choices = [("", "Elegi un color")]

        if not traje_id:
            return choices

        entry = next((item for item in self.productos_catalogo if item[0] == str(traje_id)), None)
        if not entry:
            return choices

        obj = entry[2]
        colores = [color.nombre for color in obj.colores_disponibles] if hasattr(obj, "colores_disponibles") else []

        for color in colores:
            choices.append((color, color))

        return choices

    def clean(self):
        cleaned_data = super().clean()

        cantidad_personas = cleaned_data.get("cantidad_personas")
        fecha_evento = cleaned_data.get("fecha_evento")
        fecha_visita = cleaned_data.get("fecha_visita")
        hora_visita = cleaned_data.get("hora_visita")
        vio_prendas_catalogo = cleaned_data.get("vio_prendas_catalogo")

        hoy = date.today()

        if cantidad_personas not in [1, 2, 3]:
            self.add_error(
                "cantidad_personas",
                "La cantidad de personas debe ser 1, 2 o 3.",
            )

        if fecha_evento and fecha_evento < hoy:
            self.add_error(
                "fecha_evento",
                "La fecha del evento no puede ser anterior a hoy.",
            )

        if fecha_evento and fecha_visita:
            if fecha_visita < hoy:
                self.add_error(
                    "fecha_visita",
                    "La fecha de la visita no puede ser anterior a hoy.",
                )

            if fecha_visita > fecha_evento:
                self.add_error(
                    "fecha_visita",
                    "La visita no puede ser posterior a la fecha del evento.",
                )

            primer_dia_habil = max(hoy, fecha_evento - timedelta(days=30))

            if fecha_visita < primer_dia_habil:
                self.add_error(
                    "fecha_visita",
                    "La visita solo puede reservarse dentro de los 30 dias previos al evento.",
                )

            if fecha_visita.weekday() > 4:
                self.add_error(
                    "fecha_visita",
                    "Las visitas solo se reservan de lunes a viernes.",
                )

        if hora_visita and hora_visita not in HORARIOS_VALIDOS:
            self.add_error(
                "hora_visita",
                "El horario elegido no es valido.",
            )

        if vio_prendas_catalogo not in ["si", "no"]:
            self.add_error(
                "vio_prendas_catalogo",
                "Indicanos si viste algun traje en nuestro catalogo.",
            )

        self.selected_preferences = []

        if vio_prendas_catalogo == "si":
            for index in range(1, 4):
                product_key = cleaned_data.get(f"preferencia_{index}_traje")
                entry = next((item for item in self.productos_catalogo if item[0] == product_key), None)
                traje = entry[2] if entry and product_key.startswith("traje:") else None
                color = (cleaned_data.get(f"preferencia_{index}_color") or "").strip()
                talle_saco = (
                    cleaned_data.get(f"preferencia_{index}_talle_saco") or ""
                ).strip()
                talle_pantalon = (
                    cleaned_data.get(f"preferencia_{index}_talle_pantalon") or ""
                ).strip()

                if not entry and not color:
                    continue

                if color and not entry:
                        self.add_error(
                            f"preferencia_{index}_traje",
                            "Primero elegi el traje.",
                        )
                        continue

                if entry and product_key.startswith("combo:") and not color:
                    self.add_error(
                        f"preferencia_{index}_color",
                        "Elegi el color para ese traje.",
                    )
                if not entry or (product_key.startswith("combo:") and not color):
                    continue

                colores_validos = [item.nombre for item in entry[2].colores_disponibles] if hasattr(entry[2], "colores_disponibles") else []
                color_valido = not color or color in colores_validos
                if not color_valido:
                    self.add_error(
                        f"preferencia_{index}_color",
                        "El color elegido no corresponde a ese traje.",
                    )
                    continue

                self.selected_preferences.append(
                    {
                        "orden": index,
                        "traje": traje,
                        "producto_tipo": product_key.split(":", 1)[0],
                        "producto_id": entry[2].pk,
                        "producto_nombre": entry[1],
                        "linea": traje.get_linea_display() if traje else "",
                        "tela": traje.tela if traje else entry[1],
                        "color": color,
                        "talle_saco": talle_saco,
                        "talle_pantalon": talle_pantalon,
                    }
                )

            if not self.selected_preferences:
                self.add_error(
                    "vio_prendas_catalogo",
                    "Si viste productos, elegí al menos uno.",
                )

        return cleaned_data

    def save(self, commit=True):
        visita = super().save(commit=False)

        vio_prendas_catalogo = self.cleaned_data.get("vio_prendas_catalogo")
        visita.vio_prendas_catalogo = True if vio_prendas_catalogo == "si" else False

        if commit:
            visita.save()
            self.save_preferencias(visita)

        return visita

    def save_preferencias(self, visita):
        PreferenciaAmboVisita.objects.filter(visita=visita).delete()

        preferencias = [
            PreferenciaAmboVisita(
                visita=visita,
                traje=item["traje"],
                producto_tipo=item["producto_tipo"],
                producto_id=item["producto_id"],
                producto_nombre=item["producto_nombre"],
                orden=item["orden"],
                linea=item["linea"],
                tela=item["tela"],
                color=item["color"],
                talle_saco=item["talle_saco"],
                talle_pantalon=item["talle_pantalon"],
            )
            for item in self.selected_preferences
        ]

        if preferencias:
            PreferenciaAmboVisita.objects.bulk_create(preferencias)


class VisitaInternaForm(forms.ModelForm):
    class Meta:
        model = Visita
        fields = ["estado", "observaciones_internas"]
        widgets = {
            "estado": forms.Select(attrs={"class": "ab-sel"}),
            "observaciones_internas": forms.Textarea(attrs={"class": "ab-inp", "rows": 4}),
        }


class BloqueoAgendaForm(forms.ModelForm):
    TIPO_DIA = "DIA"
    TIPO_HORARIO = "HORARIO"
    tipo_bloqueo = forms.ChoiceField(
        choices=[(TIPO_DIA, "Bloquear día"), (TIPO_HORARIO, "Bloquear horario")],
        initial=TIPO_HORARIO,
        widget=forms.RadioSelect,
        label="¿Qué querés bloquear?",
    )
    MODULOS_HORARIOS = [
        (f"{hora.strftime('%H:%M')}|{modulo}", f"{hora.strftime('%H:%M')} · módulo {modulo}")
        for hora in HORARIOS_VALIDOS
        for modulo in (1, 2)
    ]
    modulos_horarios = forms.MultipleChoiceField(
        required=False,
        choices=MODULOS_HORARIOS,
        widget=forms.CheckboxSelectMultiple,
        label="Elegí los módulos que querés bloquear",
    )
    modulos = forms.TypedChoiceField(
        required=False,
        choices=((1, "1 módulo"), (2, "2 módulos")),
        coerce=int,
        widget=forms.HiddenInput(),
    )

    class Meta:
        model = BloqueoAgenda
        fields = ["fecha", "tipo_bloqueo", "hora_inicio", "hora_fin", "modulos", "motivo"]
        labels = {"modulos": "¿Cuántos módulos querés bloquear por horario?"}
        widgets = {
            "fecha": forms.DateInput(attrs={"class": "ab-inp", "type": "date"}),
            "hora_inicio": forms.HiddenInput(),
            "hora_fin": forms.HiddenInput(),
            "modulos": forms.Select(attrs={"class": "ab-sel"}),
            "motivo": forms.TextInput(attrs={"class": "ab-inp"}),
        }

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("tipo_bloqueo") == self.TIPO_DIA:
            cleaned["hora_inicio"] = None
            cleaned["hora_fin"] = None
            cleaned["modulos"] = 2
        elif not cleaned.get("modulos_horarios"):
            self.add_error(
                "modulos_horarios",
                "Elegí al menos una burbuja de horario.",
            )
        return cleaned
