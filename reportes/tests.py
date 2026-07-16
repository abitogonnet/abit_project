from datetime import date

from django.test import TestCase
from django.urls import reverse

from alquileres.models import Alquiler, AlquilerItem
from gastos.models import Gasto
from prendas.models import Prenda


class ReportesViewsTests(TestCase):
    def test_home_muestra_mes_y_barras_con_color_real(self):
        prenda = Prenda.objects.create(
            codigo="SA-201",
            categoria=Prenda.C_SACO,
            marca="Boiler",
            color="Azul oscuro",
            talle="4",
            origen=Prenda.O_NAC,
        )
        alquiler = Alquiler.objects.create(
            fecha_visita=date(2026, 5, 1),
            fecha_reserva=date(2026, 5, 1),
            fecha_entrega=date(2026, 5, 10),
            fecha_devolucion=date(2026, 5, 12),
            cliente_nombre="Cliente Reporte",
            cliente_telefono="1111",
            persona1_nombre="Juan",
            total_bruto="160000",
            sena="80000",
            metodo_sena=Alquiler.MP_TRANS,
            estado_saldo=Alquiler.SAL_PAG,
            metodo_saldo=Alquiler.MP_EFEC,
            saldo_pagado_en=date(2026, 5, 11),
        )
        AlquilerItem.objects.create(alquiler=alquiler, persona_num=1, prenda=prenda)

        response = self.client.get(reverse("reportes:home"), {
            "ym": "2026-05",
            "periodo": "mensual",
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mayo 2026")
        self.assertContains(response, "$160.000")
        self.assertContains(response, "background: #1d3d63")

    def test_home_agrega_seccion_de_gastos_por_categoria(self):
        Gasto.objects.create(
            fecha=date(2026, 5, 3),
            categoria="PUBLICIDAD",
            monto="12000",
        )
        Gasto.objects.create(
            fecha=date(2026, 5, 8),
            categoria="PAGO DE ALQUILER",
            monto="30000",
        )

        response = self.client.get(reverse("reportes:home"), {
            "ym": "2026-05",
            "periodo": "mensual",
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Gastos")
        self.assertContains(response, "Por categoria")
        self.assertContains(response, "PUBLICIDAD")
        self.assertContains(response, "PAGO DE ALQUILER")
        self.assertContains(response, "$12.000")
        self.assertContains(response, "$30.000")
