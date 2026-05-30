from datetime import date

from django.test import TestCase
from django.urls import reverse

from alquileres.models import Alquiler

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
    def _crear_alquiler(self, *, total_bruto, sena, estado_saldo=Alquiler.SAL_PEND, metodo_saldo="", saldo_pagado_en=None):
        return Alquiler.objects.create(
            fecha_visita=date(2026, 5, 1),
            fecha_reserva=date(2026, 5, 1),
            fecha_entrega=date(2026, 5, 10),
            fecha_devolucion=date(2026, 5, 12),
            cliente_nombre="Cliente Caja",
            cliente_telefono="1111",
            persona1_nombre="Juan",
            total_bruto=total_bruto,
            sena=sena,
            metodo_sena=Alquiler.MP_EFEC if str(sena) != "0" else "",
            estado_saldo=estado_saldo,
            metodo_saldo=metodo_saldo,
            saldo_pagado_en=saldo_pagado_en,
        )

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

        self._crear_alquiler(
            total_bruto="95000",
            sena="75000",
            estado_saldo=Alquiler.SAL_PAG,
            metodo_saldo=Alquiler.MP_TRANS,
            saldo_pagado_en=date(2026, 5, 10),
        )
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
        self.assertContains(response, "Saldo actual en cuenta")
        self.assertContains(response, "Señas de Mayo 2026")
        self.assertContains(response, "Saldos cobrados en Mayo 2026")
        self.assertContains(response, "Ingresos por alquileres del mes")
        self.assertContains(response, "$75.000")
        self.assertContains(response, "$20.000")
        self.assertContains(response, "$95.000")
        self.assertContains(response, "$40.000")
        self.assertNotContains(response, "Tade acumulado")
        self.assertNotContains(response, "Bauti acumulado")

    def test_home_calcula_saldo_actual_de_cuenta_desde_alquileres(self):
        session = self.client.session
        session["gastos_access_ok"] = True
        session.save()

        self._crear_alquiler(
            total_bruto="95000",
            sena="75000",
            estado_saldo=Alquiler.SAL_PAG,
            metodo_saldo=Alquiler.MP_TRANS,
            saldo_pagado_en=date(2026, 5, 10),
        )
        self._crear_alquiler(
            total_bruto="50000",
            sena="10000",
            estado_saldo=Alquiler.SAL_PEND,
        )
        Gasto.objects.create(
            fecha=date(2026, 5, 10),
            categoria="Arreglo",
            monto="5000",
        )
        DivisionBienes.objects.create(
            fecha=date(2026, 5, 11),
            monto_total="10000",
            para_tade="5000",
            para_bauti="5000",
        )

        response = self.client.get(reverse("gastos:home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "$90.000")

    def test_vista_crear_renderiza_selectores_y_notas_tras_desbloqueo(self):
        self._unlock_gastos()

        response = self.client.get(reverse("gastos:crear"))

        self.assertContains(response, '<select name="categoria"', html=False)
        self.assertContains(response, '<select name="metodo"', html=False)
        self.assertContains(response, 'name="notas"', html=False)

    def test_division_muestra_saldo_actual_en_lugar_de_totales_por_persona(self):
        session = self.client.session
        session["gastos_access_ok"] = True
        session.save()

        self._crear_alquiler(
            total_bruto="95000",
            sena="75000",
            estado_saldo=Alquiler.SAL_PAG,
            metodo_saldo=Alquiler.MP_TRANS,
            saldo_pagado_en=date(2026, 5, 10),
        )
        Gasto.objects.create(
            fecha=date(2026, 5, 10),
            categoria="Publicidad",
            monto="5000",
        )
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
        self.assertContains(response, "Saldo actual en cuenta")
        self.assertContains(response, "Señas de Mayo 2026")
        self.assertContains(response, "Saldos cobrados en Mayo 2026")
        self.assertContains(response, "Dinero ya dividido en Mayo 2026")
        self.assertContains(response, "$75.000")
        self.assertNotContains(response, "Total esperado en cuentas")
        self.assertNotContains(response, "Tade acumulado")
        self.assertNotContains(response, "Bauti acumulado")

    def test_home_filtra_listas_por_mes_elegido(self):
        session = self.client.session
        session["gastos_access_ok"] = True
        session.save()

        Gasto.objects.create(
            fecha=date(2026, 5, 10),
            categoria="Publicidad",
            monto="5000",
            descripcion="Mayo",
        )
        Gasto.objects.create(
            fecha=date(2026, 4, 10),
            categoria="Publicidad",
            monto="3000",
            descripcion="Abril",
        )

        response = self.client.get(reverse("gastos:home"), {
            "ym": "2026-04",
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Abril 2026")
        self.assertContains(response, "Abril")
        self.assertNotContains(response, "Mayo")
