from django import forms
from django.utils import timezone
from .models import Visita

class VisitaForm(forms.ModelForm):
    class Meta:
        model = Visita
        fields = ["nombre", "telefono", "fecha_evento", "inicio", "duracion_min", "personas"]
        widgets = {
            "fecha_evento": forms.DateInput(attrs={"type": "date", "class": "ab-inp"}),
            "inicio": forms.DateTimeInput(attrs={"type": "datetime-local", "class": "ab-inp"}),
            "nombre": forms.TextInput(attrs={"class": "ab-inp", "placeholder": "Nombre (opcional)"}),
            "telefono": forms.TextInput(attrs={"class": "ab-inp", "placeholder": "+54 9 ..."}),
            "duracion_min": forms.Select(attrs={"class": "ab-sel"}),
            "personas": forms.NumberInput(attrs={"class": "ab-inp", "min": "1"}),
        }

    def clean_inicio(self):
        inicio = self.cleaned_data["inicio"]
        if timezone.is_naive(inicio):
            inicio = timezone.make_aware(inicio, timezone.get_current_timezone())
        return inicio
