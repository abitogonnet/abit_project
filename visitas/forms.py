from datetime import date, time, timedelta

from django import forms

from catalogo.models import Traje

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
            ("si", "Si, quiero indicar ambos y talles"),
        ],
        required=False,
        widget=forms.Select(attrs={"class": "reserve-input"}),
        label="Viste alguna prenda en el catalogo?",
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
        self.trajes_catalogo = list(
            Traje.objects
            .filter(activo=True)
            .prefetch_related("talles")
            .order_by("linea", "tela", "-creado")
        )

        super().__init__(*args, **kwargs)

        hoy = date.today().isoformat()
        self.fields["fecha_evento"].widget.attrs["min"] = hoy
        self.fields["fecha_visita"].widget.attrs["min"] = hoy

        for index in range(1, 4):
            self.fields[f"preferencia_{index}_traje"] = forms.ModelChoiceField(
                queryset=Traje.objects.filter(activo=True).order_by("linea", "tela"),
                required=False,
                empty_label="Elegi un ambo",
                widget=forms.Select(attrs={"class": "reserve-input"}),
                label=f"Ambo {index}",
            )
            self.fields[f"preferencia_{index}_color"] = forms.ChoiceField(
                required=False,
                choices=[("", "Elegi un color")],
                widget=forms.Select(attrs={"class": "reserve-input"}),
                label=f"Color del ambo {index}",
            )
            self.fields[f"preferencia_{index}_talle_saco"] = forms.CharField(
                required=False,
                max_length=50,
                widget=forms.TextInput(
                    attrs={
                        "class": "reserve-input",
                        "placeholder": "Ej: 50",
                    }
                ),
                label=f"Talle de saco del ambo {index}",
            )
            self.fields[f"preferencia_{index}_talle_pantalon"] = forms.CharField(
                required=False,
                max_length=50,
                widget=forms.TextInput(
                    attrs={
                        "class": "reserve-input",
                        "placeholder": "Ej: 42",
                    }
                ),
                label=f"Talle de pantalon del ambo {index}",
            )

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

        try:
            traje_id = int(traje_id)
        except (TypeError, ValueError):
            return choices

        traje = next((item for item in self.trajes_catalogo if item.id == traje_id), None)
        if not traje:
            return choices

        colores = []
        for variante in traje.talles.all():
            if variante.color not in colores:
                colores.append(variante.color)

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
                "Indicanos si viste alguna prenda en el catalogo.",
            )

        self.selected_preferences = []

        if vio_prendas_catalogo == "si":
            for index in range(1, 4):
                traje = cleaned_data.get(f"preferencia_{index}_traje")
                color = (cleaned_data.get(f"preferencia_{index}_color") or "").strip()
                talle_saco = (
                    cleaned_data.get(f"preferencia_{index}_talle_saco") or ""
                ).strip()
                talle_pantalon = (
                    cleaned_data.get(f"preferencia_{index}_talle_pantalon") or ""
                ).strip()

                if not traje and not color and not talle_saco and not talle_pantalon:
                    continue

                if color or talle_saco or talle_pantalon:
                    if not traje:
                        self.add_error(
                            f"preferencia_{index}_traje",
                            "Primero elegi el ambo.",
                        )
                        continue

                if traje and not color:
                    self.add_error(
                        f"preferencia_{index}_color",
                        "Elegi el color para ese ambo.",
                    )
                if traje and not talle_saco:
                    self.add_error(
                        f"preferencia_{index}_talle_saco",
                        "Escribi el talle de saco.",
                    )
                if traje and not talle_pantalon:
                    self.add_error(
                        f"preferencia_{index}_talle_pantalon",
                        "Escribi el talle de pantalon.",
                    )

                if not color or not talle_saco or not talle_pantalon:
                    continue

                color_valido = traje.talles.filter(color=color).exists()
                if not color_valido:
                    self.add_error(
                        f"preferencia_{index}_color",
                        "El color elegido no corresponde a ese ambo.",
                    )
                    continue

                self.selected_preferences.append(
                    {
                        "orden": index,
                        "traje": traje,
                        "linea": traje.get_linea_display(),
                        "tela": traje.tela,
                        "color": color,
                        "talle_saco": talle_saco,
                        "talle_pantalon": talle_pantalon,
                    }
                )

            if not self.selected_preferences:
                self.add_error(
                    "vio_prendas_catalogo",
                    "Si viste prendas, elegi al menos un ambo con sus talles.",
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
    class Meta:
        model = BloqueoAgenda
        fields = ["fecha", "hora_inicio", "hora_fin", "motivo"]
        widgets = {
            "fecha": forms.DateInput(attrs={"class": "ab-inp", "type": "date"}),
            "hora_inicio": forms.TimeInput(attrs={"class": "ab-inp", "type": "time", "step": 1800}),
            "hora_fin": forms.TimeInput(attrs={"class": "ab-inp", "type": "time", "step": 1800}),
            "motivo": forms.TextInput(attrs={"class": "ab-inp"}),
        }
