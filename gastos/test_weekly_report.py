from datetime import datetime
from decimal import Decimal
from unittest.mock import patch
import uuid

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from cuentas.models import Actividad, PerfilUsuario
from .models import DivisionBienes, InformeFinancieroSemanal, MovimientoFinanciero
from .weekly_report import datos_informe_semanal, generar_pdf


class InformeSemanalTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("owner-report", password="test")
        PerfilUsuario.objects.create(
            user=self.user, nombre="Bautista", rol=PerfilUsuario.PROPIETARIO,
            debe_cambiar_password=False,
        )
        self.client.force_login(self.user)
        self.desde = timezone.make_aware(datetime(2026, 7, 27, 0, 0))
        self.hasta = timezone.make_aware(datetime(2026, 7, 31, 18, 0))

    def movimiento(self, clave, ingreso=0, egreso=0, hora=None):
        return MovimientoFinanciero.objects.create(
            clave=clave, concepto="Movimiento", referencia="Alquiler #145",
            ingreso=Decimal(ingreso), egreso=Decimal(egreso),
            fecha_hora=hora or timezone.make_aware(datetime(2026, 7, 28, 12, 0)),
        )

    def test_datos_y_pdf_usan_solo_libro_mayor_real(self):
        self.movimiento("sena", ingreso="50000")
        self.movimiento("saldo", ingreso="250000")
        self.movimiento("gasto", egreso="80000")
        self.movimiento(
            "anterior", ingreso="100000",
            hora=timezone.make_aware(datetime(2026, 7, 20, 12, 0)),
        )
        # Un saldo pendiente no genera movimiento y por eso no puede entrar.
        datos = datos_informe_semanal(self.desde, self.hasta)
        self.assertEqual(datos["total_ingresos"], Decimal("300000"))
        self.assertEqual(datos["total_egresos"], Decimal("80000"))
        self.assertEqual(datos["resultado"], Decimal("220000"))
        self.assertEqual(datos["saldo_actual"], Decimal("320000"))
        pdf = generar_pdf(datos)
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertGreater(len(pdf), 1000)

    def test_division_no_es_egreso_del_resultado_pero_baja_saldo_actual(self):
        self.movimiento("ingreso", ingreso="100000")
        division = DivisionBienes.objects.create(
            fecha=self.desde.date(), monto_total="40000",
            para_tade="20000", para_bauti="20000",
        )
        MovimientoFinanciero.objects.create(
            clave="division:test", concepto="División de bienes",
            egreso="40000", division=division,
            fecha_hora=timezone.make_aware(datetime(2026, 7, 28, 13, 0)),
        )
        datos = datos_informe_semanal(self.desde, self.hasta)
        self.assertEqual(datos["total_egresos"], Decimal("0"))
        self.assertEqual(datos["resultado"], Decimal("100000"))
        self.assertEqual(datos["saldo_actual"], Decimal("60000"))

    @override_settings(WHATSAPP_ACCESS_TOKEN="", WHATSAPP_PHONE_NUMBER_ID="")
    def test_sin_whatsapp_permite_descargar_y_no_falla(self):
        response = self.client.get(reverse("gastos:descargar_informe_semanal"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))
        response = self.client.post(
            reverse("gastos:enviar_informe_semanal"),
            {"clave_solicitud": str(uuid.uuid4())},
            follow=True,
        )
        self.assertContains(response, "todavía no está configurado")
        self.assertEqual(InformeFinancieroSemanal.objects.count(), 0)

    def test_descarga_acepta_rango_personalizado_inclusivo(self):
        self.movimiento("dentro", ingreso="25000", hora=timezone.make_aware(datetime(2026, 7, 10, 23, 30)))
        response = self.client.get(
            reverse("gastos:descargar_informe_semanal"),
            {"desde": "2026-07-01", "hasta": "2026-07-10"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("2026-07-01_2026-07-10", response["Content-Disposition"])
        self.assertTrue(response.content.startswith(b"%PDF"))

    def test_rango_incompleto_no_descarga(self):
        response = self.client.get(
            reverse("gastos:descargar_informe_semanal"),
            {"desde": "2026-07-01"},
        )
        self.assertRedirects(response, reverse("gastos:enviar_informe_semanal"))

    def test_empleado_no_accede(self):
        empleado = User.objects.create_user("employee-report", password="test")
        PerfilUsuario.objects.create(
            user=empleado, nombre="Empleado", rol=PerfilUsuario.EMPLEADO,
            debe_cambiar_password=False,
        )
        self.client.force_login(empleado)
        self.assertEqual(
            self.client.get(reverse("gastos:enviar_informe_semanal")).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(reverse("gastos:descargar_informe_semanal")).status_code,
            403,
        )

    @override_settings(
        WHATSAPP_ACCESS_TOKEN="token-prueba",
        WHATSAPP_PHONE_NUMBER_ID="123",
        WEEKLY_REPORT_RECIPIENTS={"Bauti": "5492215383164", "Tadeo": "5492216710491"},
    )
    @patch("gastos.views.enviar_documento_whatsapp")
    def test_reintento_no_reenvia_a_quien_ya_recibio(self, enviar):
        intentos_tadeo = 0

        def resultado(pdf, archivo, telefono, caption):
            nonlocal intentos_tadeo
            if telefono.endswith("3164"):
                return {"estado": "enviado", "message_id": "b1", "media_id": "m1"}
            intentos_tadeo += 1
            if intentos_tadeo == 1:
                return {"estado": "fallido", "error": "temporal"}
            return {"estado": "enviado", "message_id": "t1", "media_id": "m1"}

        enviar.side_effect = resultado
        clave = str(uuid.uuid4())
        url = reverse("gastos:enviar_informe_semanal")
        payload = {"clave_solicitud": clave, "desde": "2026-07-01", "hasta": "2026-07-31"}
        self.client.post(url, payload)
        self.client.post(url, payload)

        self.assertEqual(InformeFinancieroSemanal.objects.count(), 1)
        informe = InformeFinancieroSemanal.objects.get()
        self.assertEqual(timezone.localtime(informe.periodo_desde).date().isoformat(), "2026-07-01")
        self.assertEqual(timezone.localtime(informe.periodo_hasta).date().isoformat(), "2026-07-31")
        self.assertEqual(informe.resultados["Bauti"]["estado"], "enviado")
        self.assertEqual(informe.resultados["Tadeo"]["estado"], "enviado")
        self.assertEqual(enviar.call_count, 3)
        self.assertTrue(
            Actividad.objects.filter(
                accion="Informe financiero semanal enviado",
                es_financiera=True,
            ).exists()
        )
