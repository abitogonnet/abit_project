from datetime import date

from django.test import TestCase
from django.urls import reverse

from .forms import GastoForm
from .models import DivisionBienes, Gasto


class GastoFormTests(TestCase):
    def test_categoria_usa_select_nativo(self):
        form = GastoForm()

        self.assertIn("<select", str(form["categoria"]))
        self.assertIn('class="ab-sel"', str(form["categoria"]))

    def test_metodo_usa_select_nativo(self):
        form = GastoForm()

        self.assertIn("<select", str(form["metodo"]))
        self.assertIn('class="ab-sel"', str(form["metodo"]))

    def test_formulario_expone_campo_notas(self):
        form = GastoForm()

        self.assertIn("notas", form.fields)


class GastosViewsTests(TestCase):
    def _unlock_gastos(self, path_name="gastos:home"):
        return self.client.post(reverse(path_name), {
            "access_action": "unlock",
            "access_password": "Abito2024",
        }, follow=True)

    def test_home_pide_contrasena(self):
        response = self.client.get(reverse("gastos:home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Contrasena")
        self.assertContains(response, "Gastos protegidos")

    def test_home_desbloquea_con_contrasena_correcta(self):
        response = self._unlock_gastos()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Gastos")
        self.assertNotContains(response, "Gastos protegidos")

    def test_home_muestra_detallado_de_gastos_y_divisiones(self):
        session = self.client.session
        session["gastos_access_ok"] = True
        session.save()

        Gasto.objects.create(
            fecha=date(2026, 5, 10),
            categoria="Publicidad",
            metodo="Transferencia",
            descripcion="Campana de Instagram",
            notas="Semana del evento",
            monto="15000",
        )
        DivisionBienes.objects.create(
            fecha=date(2026, 5, 11),
            monto_total="40000",
            para_tade="20000",
            para_bauti="20000",
            notas="Retiro de mitad de mes",
        )

        response = self.client.get(reverse("gastos:home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ver detallado")
        self.assertContains(response, "Campana de Instagram")
        self.assertContains(response, "Semana del evento")
        self.assertContains(response, "Retiro de mitad de mes")
        self.assertContains(response, "Total esperado en cuentas")
        self.assertContains(response, "$40000")

    def test_vista_crear_renderiza_selectores_y_notas_tras_desbloqueo(self):
        self._unlock_gastos()

        response = self.client.get(reverse("gastos:crear"))

        self.assertContains(response, '<select name="categoria"', html=False)
        self.assertContains(response, '<select name="metodo"', html=False)
        self.assertContains(response, 'name="notas"', html=False)

    def test_division_muestra_totales_en_cuentas(self):
        session = self.client.session
        session["gastos_access_ok"] = True
        session.save()

        DivisionBienes.objects.create(
            fecha=date(2026, 5, 1),
            monto_total="10000",
            para_tade="6000",
            para_bauti="4000",
            notas="Primera division",
        )
        DivisionBienes.objects.create(
            fecha=date(2026, 5, 2),
            monto_total="5000",
            para_tade="2500",
            para_bauti="2500",
            notas="Segunda division",
        )

        response = self.client.get(reverse("gastos:division_bienes"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Total esperado en cuentas")
        self.assertContains(response, "$15000")
        self.assertContains(response, "$8500")
        self.assertContains(response, "$6500")
