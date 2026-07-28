from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from cuentas.models import PerfilUsuario
from .models import Gasto


class GastosAgrupadosTests(TestCase):
    def setUp(self):
        user = User.objects.create_user("gastos-owner", password="test")
        PerfilUsuario.objects.create(
            user=user, nombre="Owner", rol=PerfilUsuario.PROPIETARIO,
            debe_cambiar_password=False,
        )
        self.client.force_login(user)

    def test_gastos_se_agrupan_por_categoria_con_subtotal(self):
        Gasto.objects.create(
            fecha=date(2026, 7, 20), categoria="SERVICIOS",
            descripcion="Luz", monto=Decimal("30000"),
        )
        Gasto.objects.create(
            fecha=date(2026, 7, 24), categoria="SERVICIOS",
            descripcion="Internet", monto=Decimal("25000"),
        )
        Gasto.objects.create(
            fecha=date(2026, 7, 21), categoria="COMPRA DE PRODUCTOS",
            descripcion="Compra", monto=Decimal("80000"),
        )
        response = self.client.get(reverse("gastos:home"), {"ym": "2026-07"})
        self.assertEqual(response.status_code, 200)
        grupos = response.context["gastos_agrupados"]
        servicios = next(g for g in grupos if g["categoria"] == "SERVICIOS")
        self.assertEqual(servicios["subtotal"], Decimal("55000"))
        self.assertEqual(
            [g.descripcion for g in servicios["gastos"]],
            ["Internet", "Luz"],
        )
        self.assertContains(response, "Subtotal SERVICIOS")
        self.assertContains(response, "$55.000")
