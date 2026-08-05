from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from alquileres.models import Alquiler, Cliente
from alquileres.services import regularizar_saldos_de_cerrados
from cuentas.models import PerfilUsuario
from .forms import DivisionBienesForm
from .models import DivisionBienes, Gasto, MovimientoFinanciero
from .services import registrar_movimiento, registrar_saldo, registrar_sena, resumen_movimientos


class MovimientosFinancierosTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("owner", password="test")
        PerfilUsuario.objects.create(
            user=self.user, nombre="Owner", rol=PerfilUsuario.PROPIETARIO,
            debe_cambiar_password=False,
        )
        self.client.force_login(self.user)
        self.cliente = Cliente.objects.create(nombre="Juan", dni="40123456", telefono="2213540416")

    def alquiler(self, estado=Alquiler.EST_RESERVADO):
        return Alquiler.objects.create(
            cliente=self.cliente, cliente_nombre="Juan", cliente_telefono="2213540416",
            persona1_nombre="Juan", fecha_visita=date.today(), fecha_reserva=date.today(),
            fecha_entrega=date.today(), fecha_devolucion=date.today(),
            total_bruto=Decimal("300000"), sena=Decimal("50000"),
            metodo_sena=Alquiler.MP_EFEC, estado_alquiler=estado,
        )

    def test_sena_y_saldo_se_contabilizan_una_sola_vez(self):
        alquiler = self.alquiler()
        registrar_sena(alquiler, self.user)
        registrar_sena(alquiler, self.user)
        registrar_saldo(alquiler, self.user)
        registrar_saldo(alquiler, self.user)
        self.assertEqual(MovimientoFinanciero.objects.filter(alquiler=alquiler).count(), 2)
        self.assertEqual(resumen_movimientos()["saldo"], Decimal("300000"))

    def test_pendiente_no_integra_saldo_actual_hasta_cobro_real(self):
        alquiler = self.alquiler()
        registrar_sena(alquiler, self.user)
        self.assertEqual(alquiler.saldo_contractual, Decimal("250000"))
        self.assertEqual(resumen_movimientos()["saldo"], Decimal("50000"))

        self.client.post(
            reverse("alquileres:home"),
            {"alq_id": alquiler.id, "accion": "marcar_saldo_pagado"},
        )
        self.assertEqual(resumen_movimientos()["saldo"], Decimal("300000"))
        self.client.post(
            reverse("alquileres:home"),
            {"alq_id": alquiler.id, "accion": "marcar_entregado"},
        )
        self.assertEqual(resumen_movimientos()["saldo"], Decimal("300000"))

    def test_saldo_acumulado_filtrado_conserva_acumulado_global(self):
        alquiler = self.alquiler()
        registrar_sena(alquiler, self.user)
        gasto = Gasto.objects.create(categoria="Lavandería", monto=Decimal("10000"))
        registrar_movimiento(
            clave=f"gasto:{gasto.pk}", concepto="Gasto", referencia="Gasto",
            egreso=gasto.monto, gasto=gasto, usuario=self.user,
        )
        response = self.client.get(reverse("gastos:movimientos"), {"tipo": "egresos"})
        self.assertEqual(response.context["saldo_actual"], Decimal("40000"))
        self.assertEqual(response.context["movimientos"][0].saldo_acumulado, Decimal("40000"))

    def test_regularizacion_de_cerrado_crea_movimiento_faltante_una_vez(self):
        alquiler = self.alquiler(estado=Alquiler.EST_CERRADO)
        registrar_sena(alquiler, self.user)
        self.assertEqual(resumen_movimientos()["saldo"], Decimal("50000"))
        regularizar_saldos_de_cerrados(self.user)
        regularizar_saldos_de_cerrados(self.user)
        self.assertEqual(resumen_movimientos()["saldo"], Decimal("300000"))
        self.assertEqual(
            MovimientoFinanciero.objects.filter(
                clave=f"alquiler:{alquiler.pk}:saldo"
            ).count(),
            1,
        )

    def test_entregado_y_cierre_posterior_no_duplican_saldo(self):
        alquiler = self.alquiler()
        registrar_sena(alquiler, self.user)
        self.client.post(reverse("alquileres:home"), {"alq_id": alquiler.id, "accion": "marcar_entregado"})
        self.client.post(reverse("alquileres:home"), {"alq_id": alquiler.id, "accion": "cerrar_alquiler"})
        self.assertEqual(MovimientoFinanciero.objects.filter(clave=f"alquiler:{alquiler.id}:saldo").count(), 1)
        self.assertEqual(resumen_movimientos()["saldo"], Decimal("300000"))

    def test_cierre_directo_contabiliza_restante_y_cancelado_no(self):
        cerrado = self.alquiler()
        registrar_sena(cerrado, self.user)
        self.client.post(reverse("alquileres:home"), {"alq_id": cerrado.id, "accion": "cerrar_alquiler"})
        cancelado = self.alquiler()
        registrar_sena(cancelado, self.user)
        self.client.post(reverse("alquileres:home"), {"alq_id": cancelado.id, "accion": "cancelar_alquiler"})
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.saldo_a_favor, Decimal("50000"))
        self.assertFalse(MovimientoFinanciero.objects.filter(clave=f"alquiler:{cancelado.id}:saldo").exists())
        self.assertEqual(resumen_movimientos()["saldo"], Decimal("350000"))

    def test_gasto_reconcilia_saldo(self):
        alquiler = self.alquiler()
        registrar_sena(alquiler, self.user)
        gasto = Gasto.objects.create(categoria="Lavandería", monto=Decimal("40000"))
        registrar_movimiento(clave=f"gasto:{gasto.id}", concepto="Gasto", referencia="Gasto",
                             egreso=gasto.monto, gasto=gasto, usuario=self.user)
        self.assertEqual(resumen_movimientos()["saldo"], Decimal("10000"))

    def test_division_baja_la_cuenta_pero_no_el_resultado_del_mes(self):
        registrar_movimiento(
            clave="ingreso-prueba", concepto="Ingreso", referencia="Prueba",
            ingreso=Decimal("100000"), usuario=self.user,
        )
        division = DivisionBienes.objects.create(
            monto_total=Decimal("40000"),
            para_tade=Decimal("20000"),
            para_bauti=Decimal("20000"),
        )
        registrar_movimiento(
            clave=f"division:{division.pk}", concepto="División de bienes",
            referencia="Prueba", egreso=division.monto_total,
            division=division, usuario=self.user,
        )
        self.assertEqual(resumen_movimientos()["saldo"], Decimal("60000"))
        self.assertEqual(
            resumen_movimientos(incluir_divisiones=False)["saldo"],
            Decimal("100000"),
        )

    def test_division_sin_reparto_manual_se_completa_cincuenta_cincuenta(self):
        form = DivisionBienesForm(data={
            "fecha": date.today().isoformat(),
            "monto_total": "10001",
            "para_tade": "",
            "para_bauti": "",
            "notas": "",
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["para_tade"], Decimal("5000.50"))
        self.assertEqual(form.cleaned_data["para_bauti"], Decimal("5000.50"))

    def test_division_admite_reparto_manual(self):
        form = DivisionBienesForm(data={
            "fecha": date.today().isoformat(),
            "monto_total": "10000",
            "para_tade": "6000",
            "para_bauti": "4000",
            "notas": "",
        })
        self.assertTrue(form.is_valid(), form.errors)

    def test_planilla_movimientos_es_privada_y_renderiza(self):
        response = self.client.get(reverse("gastos:movimientos"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Saldo actual de la cuenta")
        empleado = User.objects.create_user("empleado", password="test")
        PerfilUsuario.objects.create(
            user=empleado, nombre="Empleado", rol=PerfilUsuario.EMPLEADO,
            debe_cambiar_password=False,
        )
        self.client.force_login(empleado)
        self.assertEqual(self.client.get(reverse("gastos:movimientos")).status_code, 403)

    def test_planilla_renderiza_movimiento_sin_usuario_como_sistema(self):
        registrar_movimiento(
            clave="movimiento-sistema",
            concepto="Regularización",
            referencia="Movimiento histórico",
            ingreso=Decimal("1000"),
            usuario=None,
        )

        response = self.client.get(reverse("gastos:movimientos"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Movimiento histórico")
        self.assertContains(response, "Sistema")

    def test_finanzas_muestra_solo_cuatro_indicadores_principales(self):
        response = self.client.get(reverse("gastos:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "SALDO ACTUAL", count=1)
        self.assertContains(response, "SALDO DEL MES", count=1)
        self.assertContains(response, "A ENTRAR ESTA SEMANA", count=1)
        self.assertContains(response, "GASTOS DEL MES", count=1)
