from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from cuentas.models import Actividad, PerfilUsuario
from gastos.models import MovimientoFinanciero
from gastos.services import registrar_sena
from prendas.models import Prenda

from .models import Alquiler, AlquilerItem, Cliente
from .services import TransicionAlquilerInvalida, cancelar_alquiler


class CancelacionAlquilerTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("owner", password="test")
        PerfilUsuario.objects.create(
            user=self.user,
            nombre="Owner",
            rol=PerfilUsuario.PROPIETARIO,
            debe_cambiar_password=False,
        )
        self.client.force_login(self.user)
        self.cliente = Cliente.objects.create(
            nombre="Juan",
            dni="40123456",
            telefono="2215555555",
            saldo_a_favor=Decimal("10000.00"),
        )

    def crear_alquiler(self, *, sena=Decimal("50000.00"), estado=None):
        return Alquiler.objects.create(
            cliente=self.cliente,
            cliente_nombre=self.cliente.nombre,
            cliente_telefono=self.cliente.telefono,
            persona1_nombre=self.cliente.nombre,
            fecha_visita=date(2026, 7, 1),
            fecha_reserva=date(2026, 7, 1),
            fecha_entrega=date(2026, 7, 10),
            fecha_devolucion=date(2026, 7, 12),
            total_bruto=Decimal("150000.00"),
            sena=sena,
            metodo_sena=Alquiler.MP_EFEC if sena else "",
            estado_alquiler=estado or Alquiler.EST_RESERVADO,
        )

    def test_cancelacion_normal_es_atomica_y_auditada(self):
        alquiler = self.crear_alquiler()
        prenda = Prenda.objects.create(
            codigo="SA-CAN-1",
            categoria=Prenda.C_SACO,
            color="Negro",
            talle="48",
            estado=Prenda.E_RES,
        )
        AlquilerItem.objects.create(
            alquiler=alquiler, persona_num=1, prenda=prenda
        )
        registrar_sena(alquiler, self.user)

        cancelado, changed = cancelar_alquiler(alquiler.pk, self.user)

        self.assertTrue(changed)
        self.assertEqual(cancelado.estado_alquiler, Alquiler.EST_CANCELADO)
        alquiler.refresh_from_db()
        self.cliente.refresh_from_db()
        prenda.refresh_from_db()
        self.assertEqual(self.cliente.saldo_a_favor, Decimal("60000.00"))
        self.assertTrue(alquiler.credito_cancelacion_generado)
        self.assertEqual(alquiler.cancelado_por, self.user)
        self.assertIsNotNone(alquiler.cancelado_en)
        self.assertEqual(prenda.estado, Prenda.E_DISP)
        self.assertEqual(
            Actividad.objects.filter(
                objeto_id=str(alquiler.pk), accion="Canceló alquiler"
            ).count(),
            1,
        )
        self.assertEqual(
            MovimientoFinanciero.objects.filter(
                clave=f"alquiler:{alquiler.pk}:credito-cancelacion"
            ).count(),
            1,
        )
        sena = MovimientoFinanciero.objects.get(
            clave=f"alquiler:{alquiler.pk}:sena"
        )
        self.assertEqual(sena.ingreso, Decimal("50000.00"))
        self.assertFalse(sena.informativo)

    def test_dos_intentos_consecutivos_no_duplican_credito(self):
        alquiler = self.crear_alquiler()

        _, primero = cancelar_alquiler(alquiler.pk, self.user)
        _, segundo = cancelar_alquiler(alquiler.pk, self.user)

        self.assertTrue(primero)
        self.assertFalse(segundo)
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.saldo_a_favor, Decimal("60000.00"))
        self.assertEqual(
            MovimientoFinanciero.objects.filter(
                clave=f"alquiler:{alquiler.pk}:credito-cancelacion"
            ).count(),
            1,
        )
        self.assertEqual(
            Actividad.objects.filter(
                objeto_id=str(alquiler.pk), accion="Canceló alquiler"
            ).count(),
            1,
        )

    def test_doble_post_produce_un_solo_credito(self):
        alquiler = self.crear_alquiler()
        payload = {"alq_id": alquiler.pk, "accion": "cancelar_alquiler"}

        self.client.post(reverse("alquileres:home"), payload)
        self.client.post(reverse("alquileres:home"), payload)

        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.saldo_a_favor, Decimal("60000.00"))
        self.assertEqual(
            MovimientoFinanciero.objects.filter(
                clave=f"alquiler:{alquiler.pk}:credito-cancelacion"
            ).count(),
            1,
        )

    def test_alquiler_ya_cancelado_no_genera_efectos(self):
        alquiler = self.crear_alquiler(estado=Alquiler.EST_CANCELADO)

        _, changed = cancelar_alquiler(alquiler.pk, self.user)

        self.assertFalse(changed)
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.saldo_a_favor, Decimal("10000.00"))
        self.assertFalse(
            MovimientoFinanciero.objects.filter(alquiler=alquiler).exists()
        )

    def test_sena_cero_cancela_sin_generar_credito(self):
        alquiler = self.crear_alquiler(sena=Decimal("0.00"))

        cancelar_alquiler(alquiler.pk, self.user)

        alquiler.refresh_from_db()
        self.cliente.refresh_from_db()
        self.assertEqual(alquiler.estado_alquiler, Alquiler.EST_CANCELADO)
        self.assertFalse(alquiler.credito_cancelacion_generado)
        self.assertEqual(self.cliente.saldo_a_favor, Decimal("10000.00"))
        self.assertFalse(
            MovimientoFinanciero.objects.filter(alquiler=alquiler).exists()
        )

    def test_no_permite_cancelar_un_alquiler_entregado(self):
        alquiler = self.crear_alquiler(estado=Alquiler.EST_ENTREGADO)

        with self.assertRaises(TransicionAlquilerInvalida):
            cancelar_alquiler(alquiler.pk, self.user)

        alquiler.refresh_from_db()
        self.assertEqual(alquiler.estado_alquiler, Alquiler.EST_ENTREGADO)

    def test_falla_intermedia_hace_rollback_completo(self):
        alquiler = self.crear_alquiler()

        with patch(
            "gastos.services.registrar_movimiento",
            side_effect=RuntimeError("fallo simulado"),
        ):
            with self.assertRaises(RuntimeError):
                cancelar_alquiler(alquiler.pk, self.user)

        alquiler.refresh_from_db()
        self.cliente.refresh_from_db()
        self.assertEqual(alquiler.estado_alquiler, Alquiler.EST_RESERVADO)
        self.assertFalse(alquiler.credito_cancelacion_generado)
        self.assertIsNone(alquiler.cancelado_en)
        self.assertIsNone(alquiler.cancelado_por)
        self.assertEqual(self.cliente.saldo_a_favor, Decimal("10000.00"))
        self.assertFalse(
            MovimientoFinanciero.objects.filter(alquiler=alquiler).exists()
        )
        self.assertFalse(
            Actividad.objects.filter(objeto_id=str(alquiler.pk)).exists()
        )
