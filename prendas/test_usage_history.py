from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from alquileres.models import Alquiler, AlquilerItem
from cuentas.models import PerfilUsuario

from .models import Prenda


class HistorialUsoPrendaTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("stock-history", password="test")
        PerfilUsuario.objects.create(
            user=self.user, nombre="Stock", rol=PerfilUsuario.EMPLEADO,
            debe_cambiar_password=False,
        )
        self.client.force_login(self.user)
        self.prenda = Prenda.objects.create(
            codigo="SA-052", categoria=Prenda.C_SACO, marca="Abito",
            color="Azul Francia", talle="50", origen=Prenda.O_IMP,
            estado=Prenda.E_RES,
        )

    def alquiler(self, numero, estado, *, persona_num=1):
        hoy = timezone.localdate()
        alquiler = Alquiler.objects.create(
            cliente_nombre=f"Cliente {numero}", cliente_telefono="2215555555",
            persona1_nombre=f"Cliente {numero}",
            persona2_nombre=f"Persona real {numero}",
            fecha_visita=hoy - timedelta(days=numero + 20),
            fecha_reserva=hoy - timedelta(days=numero + 20),
            fecha_entrega=hoy - timedelta(days=numero * 3),
            fecha_devolucion=hoy - timedelta(days=numero * 3 - 2),
            total_bruto=0, sena=0, estado_alquiler=estado,
        )
        AlquilerItem.objects.create(
            alquiler=alquiler, persona_num=persona_num, prenda=self.prenda
        )
        return alquiler

    def test_historial_existente_persona_real_orden_actual_cancelado_y_contador(self):
        antiguos = [
            self.alquiler(numero, Alquiler.EST_CERRADO, persona_num=2 if numero == 1 else 1)
            for numero in range(1, 6)
        ]
        cancelado = self.alquiler(6, Alquiler.EST_CANCELADO)
        actual = self.alquiler(0, Alquiler.EST_RESERVADO, persona_num=2)

        response = self.client.get(reverse("prendas:detalle", args=[self.prenda.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["usos_historicos"], 5)
        self.assertEqual(len(response.context["usos"]), 7)
        self.assertEqual(response.context["usos"][0]["alquiler"], actual)
        self.assertEqual(response.context["usos"][0]["persona"], "Persona real 0")
        self.assertContains(response, "Uso actual")
        self.assertContains(response, "Persona real 1")
        self.assertContains(response, "Cancelado")
        self.assertContains(response, "no se cuenta como uso histórico efectivo")
        self.assertContains(response, f"?buscar={antiguos[0].pk}#alquiler-{antiguos[0].pk}")
        self.assertNotContains(response, "Saldo")
        self.assertNotContains(response, "Seña")
        self.assertNotContains(response, "Descuento")

    def test_prenda_sin_historial_muestra_estado_vacio(self):
        nueva = Prenda.objects.create(
            codigo="PA-999", categoria=Prenda.C_PANTALON,
            color="Negro", talle="50", origen=Prenda.O_NAC,
        )
        response = self.client.get(reverse("prendas:detalle", args=[nueva.pk]))
        self.assertContains(response, "Esta prenda todavía no tiene historial de uso.")
        self.assertContains(response, "Usos históricos: 0")

    def test_camisa_no_muestra_origen(self):
        camisa = Prenda.objects.create(
            codigo="CA-052", categoria=Prenda.C_CAMISA,
            color="Blanca", talle="M", origen=Prenda.O_NAC,
        )
        response = self.client.get(reverse("prendas:detalle", args=[camisa.pk]))
        self.assertFalse(response.context["mostrar_origen"])
        self.assertNotContains(response, ">Origen<")

    def test_detalle_no_es_publico_y_respeta_roles_de_stock(self):
        url = reverse("prendas:detalle", args=[self.prenda.pk])
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)

        costurera = User.objects.create_user("costurera-history", password="test")
        PerfilUsuario.objects.create(
            user=costurera, nombre="Costurera", rol=PerfilUsuario.COSTURERA,
            debe_cambiar_password=False,
        )
        self.client.force_login(costurera)
        self.assertEqual(self.client.get(url).status_code, 403)
