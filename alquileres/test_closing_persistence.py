from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from cuentas.models import Actividad, PerfilUsuario
from gastos.models import MovimientoFinanciero
from gastos.services import registrar_sena
from prendas.models import Prenda

from .models import Alquiler, AlquilerItem


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
