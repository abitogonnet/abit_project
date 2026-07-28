from datetime import date, datetime, time

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from alquileres.models import Alquiler, AlquilerItem
from gastos.models import Gasto
from prendas.models import Prenda
from visitas.models import Visita
from .views import _visitas_conversion


class ReportesViewsTests(TestCase):
    def test_efectividad_excluye_futuras_y_canceladas(self):
        alquiler = Alquiler.objects.create(
            fecha_visita=date(2026, 7, 1), fecha_reserva=date(2026, 7, 1),
            fecha_entrega=date(2026, 7, 2), fecha_devolucion=date(2026, 7, 3),
            cliente_nombre="Cliente", cliente_telefono="1111",
            persona1_nombre="Cliente", total_bruto=1, sena=1,
        )
        common = {
            "dni": "12345678", "telefono": "2215555555",
            "cantidad_personas": 1, "fecha_evento": date(2026, 7, 20),
        }
        Visita.objects.create(nombre="Alquiló", fecha_visita=date(2026, 7, 5), hora_visita=time(17), alquiler=alquiler, **common)
        Visita.objects.create(nombre="No alquiló", fecha_visita=date(2026, 7, 6), hora_visita=time(17), **common)
        Visita.objects.create(nombre="Futura", fecha_visita=date(2026, 7, 20), hora_visita=time(17), **common)
        Visita.objects.create(nombre="Cancelada", fecha_visita=date(2026, 7, 7), hora_visita=time(17), estado=Visita.ESTADO_CANCELADA, **common)
        result = _visitas_conversion(
            date(2026, 7, 1), date(2026, 8, 1),
            ahora=timezone.make_aware(datetime(2026, 7, 10, 12)),
        )
        self.assertEqual(result["total"], 2)
        self.assertEqual(result["alquilaron"], 1)
        self.assertEqual(result["no_alquilaron"], 1)
        self.assertEqual(result["conversion"], 50.0)
        self.assertEqual(result["canceladas"], 1)

    def _unlock_finanzas(self):
        session = self.client.session
        session["gastos_access_ok"] = True
        session.save()

    def test_home_pide_contrasena(self):
        response = self.client.get(reverse("reportes:home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Finanzas protegidas")
        self.assertContains(response, "Contrasena")

    def test_home_muestra_mes_y_barras_con_color_real(self):
        self._unlock_finanzas()

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
        self._unlock_finanzas()

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

    def test_home_regulariza_cerrados_viejos_y_cuenta_el_total_completo(self):
        self._unlock_finanzas()

        alquiler = Alquiler.objects.create(
            fecha_visita=date(2026, 5, 1),
            fecha_reserva=date(2026, 5, 1),
            fecha_entrega=date(2026, 5, 10),
            fecha_devolucion=date(2026, 5, 12),
            cliente_nombre="Cliente Cerrado",
            cliente_telefono="1111",
            persona1_nombre="Juan",
            total_bruto="160000",
            sena="80000",
            metodo_sena=Alquiler.MP_TRANS,
            estado_saldo=Alquiler.SAL_PEND,
            estado_alquiler=Alquiler.EST_CERRADO,
        )

        response = self.client.get(reverse("reportes:home"), {
            "ym": "2026-05",
            "periodo": "mensual",
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "$160.000")
        alquiler.refresh_from_db()
        self.assertEqual(alquiler.estado_saldo, Alquiler.SAL_PAG)
        self.assertEqual(alquiler.saldo_pagado_en, date(2026, 5, 12))

    def test_exportar_pide_contrasena(self):
        response = self.client.get(reverse("reportes:exportar_excel"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Finanzas protegidas")
