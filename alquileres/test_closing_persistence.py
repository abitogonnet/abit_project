from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.db import DatabaseError, connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from cuentas.models import Actividad, PerfilUsuario
from gastos.models import MovimientoFinanciero
from gastos.services import registrar_sena
from prendas.models import Prenda

from .models import Alquiler, AlquilerItem
from .services import cerrar_alquiler


class CierrePersistenteTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("cierre-owner", password="test")
        PerfilUsuario.objects.create(
            user=self.user, nombre="Bautista", rol=PerfilUsuario.PROPIETARIO,
            debe_cambiar_password=False,
        )
        self.client.force_login(self.user)

    def crear_alquiler(self, estado=Alquiler.EST_RESERVADO):
        hoy = timezone.localdate()
        alquiler = Alquiler.objects.create(
            cliente_nombre="Cliente", cliente_telefono="2215555555",
            persona1_nombre="Cliente", fecha_visita=hoy - timedelta(days=10),
            fecha_reserva=hoy - timedelta(days=10),
            fecha_entrega=hoy - timedelta(days=5),
            fecha_devolucion=hoy - timedelta(days=2),
            total_bruto=Decimal("300000"), sena=Decimal("50000"),
            estado_alquiler=estado,
        )
        prenda = Prenda.objects.create(
            codigo=f"SA-{alquiler.pk}", categoria=Prenda.C_SACO,
            marca="Abito", color="Negro", talle="50",
            origen=Prenda.O_NAC, estado=Prenda.E_RES,
        )
        AlquilerItem.objects.create(alquiler=alquiler, prenda=prenda)
        registrar_sena(alquiler, self.user)
        return alquiler, prenda

    def test_cierre_desde_todas_las_vistas_persiste_y_no_duplica(self):
        casos = [
            ("alquileres:home", Alquiler.EST_RESERVADO),
            ("alquileres:ver", Alquiler.EST_RESERVADO),
            ("alquileres:entregas", Alquiler.EST_ENTREGADO),
            ("alquileres:retrasados", Alquiler.EST_ENTREGADO),
        ]
        for ruta, estado in casos:
            with self.subTest(ruta=ruta):
                alquiler, prenda = self.crear_alquiler(estado)
                url = reverse(ruta)
                self.client.post(url, {"alq_id": alquiler.pk, "accion": "cerrar_alquiler"})
                alquiler.refresh_from_db()
                prenda.refresh_from_db()
                self.assertEqual(alquiler.estado_alquiler, Alquiler.EST_CERRADO)
                self.assertEqual(alquiler.estado_saldo, Alquiler.SAL_PAG)
                self.assertEqual(alquiler.saldo, Decimal("0"))
                self.assertIsNotNone(alquiler.cerrado_en)
                self.assertEqual(alquiler.cerrado_por, self.user)
                self.assertEqual(prenda.estado, Prenda.E_DISP)
                self.assertEqual(
                    MovimientoFinanciero.objects.filter(alquiler=alquiler).count(), 2
                )
                self.client.post(url, {"alq_id": alquiler.pk, "accion": "cerrar_alquiler"})
                self.assertEqual(
                    MovimientoFinanciero.objects.filter(alquiler=alquiler).count(), 2
                )
                self.assertEqual(
                    Actividad.objects.filter(
                        objeto_id=str(alquiler.pk), accion="Alquiler cerrado"
                    ).count(),
                    1,
                )
                recarga = self.client.get(url)
                self.assertEqual(recarga.status_code, 200)
                if ruta == "alquileres:ver":
                    self.assertContains(recarga, "Cerrado")
                else:
                    self.assertNotContains(
                        recarga, f'input type="hidden" name="alq_id" value="{alquiler.pk}"'
                    )

    def test_bloqueo_del_alquiler_no_incluye_join_nullable_de_usuario(self):
        alquiler, _prenda = self.crear_alquiler()

        with CaptureQueriesContext(connection) as queries:
            cerrar_alquiler(alquiler.pk, self.user)

        consulta_bloqueo = next(
            query["sql"]
            for query in queries.captured_queries
            if 'FROM "alquileres_alquiler"' in query["sql"]
        )
        self.assertNotIn('JOIN "auth_user"', consulta_bloqueo)

    def test_cierre_historico_con_varias_personas_prendas_y_ruedo(self):
        alquiler, saco = self.crear_alquiler(Alquiler.EST_ENTREGADO)
        alquiler.cliente_telefono = ""
        alquiler.persona2_nombre = "Persona histórica"
        alquiler.save(update_fields=["cliente_telefono", "persona2_nombre"])
        pantalon = Prenda.objects.create(
            codigo=f"PA-{alquiler.pk}", categoria=Prenda.C_PANTALON,
            marca="Abito", color="Negro", talle="42",
            origen=Prenda.O_NAC, estado=Prenda.E_ENT,
        )
        item_ruedo = AlquilerItem.objects.create(
            alquiler=alquiler,
            persona_num=2,
            prenda=pantalon,
            ruedo_valor=Decimal("3.50"),
            ruedo_tipo=AlquilerItem.RUEDO_CM,
        )

        cerrar_alquiler(alquiler.pk, self.user)

        alquiler.refresh_from_db()
        saco.refresh_from_db()
        pantalon.refresh_from_db()
        item_ruedo.refresh_from_db()
        self.assertEqual(alquiler.estado_alquiler, Alquiler.EST_CERRADO)
        self.assertEqual(saco.estado, Prenda.E_DISP)
        self.assertEqual(pantalon.estado, Prenda.E_DISP)
        self.assertEqual(item_ruedo.ruedo_valor, Decimal("3.50"))
        self.assertEqual(item_ruedo.persona_num, 2)
        self.assertTrue(AlquilerItem.objects.filter(pk=item_ruedo.pk).exists())

    def test_cierre_ya_pagado_no_duplica_ingreso(self):
        alquiler, _prenda = self.crear_alquiler(Alquiler.EST_ENTREGADO)
        alquiler.marcar_completamente_abonado()
        alquiler.save(update_fields=["saldo", "estado_saldo", "saldo_pagado_en"])
        from gastos.services import registrar_saldo
        registrar_saldo(alquiler, self.user)
        movimientos_antes = MovimientoFinanciero.objects.filter(
            alquiler=alquiler,
        ).count()

        cerrar_alquiler(alquiler.pk, self.user)
        cerrar_alquiler(alquiler.pk, self.user)

        self.assertEqual(
            MovimientoFinanciero.objects.filter(alquiler=alquiler).count(),
            movimientos_antes,
        )

    def test_error_de_base_controlado_revierte_y_muestra_mensaje(self):
        alquiler, prenda = self.crear_alquiler()

        with patch(
            "alquileres.views.cerrar_alquiler",
            side_effect=DatabaseError("fallo simulado"),
        ):
            response = self.client.post(
                reverse("alquileres:ver"),
                {"alq_id": alquiler.pk, "accion": "cerrar_alquiler"},
                follow=True,
            )

        alquiler.refresh_from_db()
        prenda.refresh_from_db()
        self.assertEqual(alquiler.estado_alquiler, Alquiler.EST_RESERVADO)
        self.assertEqual(prenda.estado, Prenda.E_RES)
        self.assertContains(
            response,
            "No se pudo cerrar el alquiler. No se realizó ningún cambio.",
        )
