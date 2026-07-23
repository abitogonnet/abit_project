from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from cuentas.models import PerfilUsuario
from prendas.models import Prenda
from .models import Alquiler, AlquilerItem


class UsabilityRoundTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("owner2", password="test")
        PerfilUsuario.objects.create(user=self.user, nombre="Owner", rol=PerfilUsuario.PROPIETARIO)
        self.client.force_login(self.user)

    def alquiler(self, entrega):
        return Alquiler.objects.create(
            cliente_nombre="Bautista", cliente_telefono="2213540416", persona1_nombre="Bautista",
            fecha_visita=timezone.localdate(), fecha_reserva=timezone.localdate(),
            fecha_entrega=entrega, fecha_devolucion=entrega + timedelta(days=2),
            total_bruto=100000, sena=20000, metodo_sena=Alquiler.MP_EFEC,
        )

    def test_crear_incluye_modales_y_alerta_de_ruedo(self):
        response = self.client.get(reverse("alquileres:crear"))
        self.assertContains(response, "Buscar prenda")
        self.assertContains(response, "Crear prenda")
        self.assertContains(response, "ATENCIÓN: este alquiler tiene al menos una prenda con ruedo")
        self.assertContains(response, 'data-persona-number="1"')
        self.assertContains(response, 'data-persona-number="2"')
        self.assertContains(response, 'data-persona-number="2"\n            hidden', html=False)

    def test_ruedos_urgentes_ordenan_antes_de_proximos(self):
        urgente = self.alquiler(timezone.localdate() + timedelta(days=2))
        proximo = self.alquiler(timezone.localdate() + timedelta(days=6))
        p1 = Prenda.objects.create(codigo="PA-800", categoria=Prenda.C_PANTALON, origen=Prenda.O_NAC)
        p2 = Prenda.objects.create(codigo="PA-801", categoria=Prenda.C_PANTALON, origen=Prenda.O_NAC)
        AlquilerItem.objects.create(alquiler=urgente, prenda=p1, ruedo_valor=3, ruedo_tipo=AlquilerItem.RUEDO_CM)
        AlquilerItem.objects.create(alquiler=proximo, prenda=p2, ruedo_valor=2, ruedo_tipo=AlquilerItem.RUEDO_CM)
        content = self.client.get(reverse("alquileres:home")).content.decode()
        self.assertLess(content.index("URGENTE — Ruedo pendiente"), content.index(">Ruedo pendiente<"))

    def test_costurera_no_accede_a_api_de_stock(self):
        costurera = User.objects.create_user("costurera2", password="test")
        PerfilUsuario.objects.create(user=costurera, nombre="Costurera", rol=PerfilUsuario.COSTURERA)
        self.client.force_login(costurera)
        self.assertEqual(self.client.get(reverse("prendas:disponibles_api")).status_code, 403)
        self.assertEqual(self.client.get(reverse("alquileres:ruedos")).status_code, 200)
