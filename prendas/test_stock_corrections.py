from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from cuentas.models import PerfilUsuario
from .forms import CAMISA_TALLES, PrendaForm, talle_options_for
from .models import Color, Prenda


class StockCorrectionsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("stock-owner", password="test")
        PerfilUsuario.objects.create(
            user=self.user, nombre="Owner", rol=PerfilUsuario.PROPIETARIO,
            debe_cambiar_password=False,
        )
        self.client.force_login(self.user)
        Color.objects.get_or_create(nombre="Negro")

    def test_modificar_origen_persiste_y_sale_de_incompletas(self):
        prenda = Prenda.objects.create(
            codigo="SA-150", categoria=Prenda.C_SACO, marca="Abito",
            color="Negro", talle="50", origen="",
        )
        response = self.client.post(reverse("prendas:editar", args=[prenda.pk]), {
            "categoria": Prenda.C_SACO, "marca": "Abito", "color": "Negro",
            "talle": "50", "origen": Prenda.O_IMP, "notas": "",
        })
        self.assertRedirects(response, reverse("prendas:stock"))
        prenda.refresh_from_db()
        self.assertEqual(prenda.origen, Prenda.O_IMP)
        self.assertFalse(Prenda.incompletas().filter(pk=prenda.pk).exists())
        self.assertContains(
            self.client.get(reverse("prendas:stock")),
            "No hay pendientes.",
        )

    def test_lista_camisas_es_unica_y_acepta_hasta_80(self):
        esperados = [
            "2", "4", "6", "8", "10", "12", "14", "16",
            "XS", "S", "M", "L", "XL", "2XL", "3XL",
            "40", "42", "44", "46", "48", "50", "52", "54", "56",
            "58", "60", "62", "64", "66", "68", "70", "72", "74",
            "76", "78", "80",
        ]
        self.assertEqual(CAMISA_TALLES, esperados)
        self.assertEqual(talle_options_for(Prenda.C_CAMISA, "Abito"), esperados)
        for talle in ("76", "78", "80"):
            form = PrendaForm(data={
                "categoria": Prenda.C_CAMISA, "marca": "Abito",
                "color": "Negro", "talle": talle,
                "origen": Prenda.O_NAC, "notas": "",
            })
            self.assertTrue(form.is_valid(), form.errors)

    def test_camisa_historica_fuera_de_lista_no_se_rompe_al_editar(self):
        prenda = Prenda.objects.create(
            codigo="CA-OLD", categoria=Prenda.C_CAMISA, marca="Abito",
            color="Negro", talle="5XL", origen=Prenda.O_NAC,
        )
        form = PrendaForm(data={
            "categoria": Prenda.C_CAMISA, "marca": "Abito",
            "color": "Negro", "talle": "5XL",
            "origen": Prenda.O_NAC, "notas": "Histórica",
        }, instance=prenda)
        self.assertTrue(form.is_valid(), form.errors)

    def test_editar_camisa_oculta_selector_y_mantiene_origen_importado(self):
        prenda = Prenda.objects.create(
            codigo="CA-AUTO", categoria=Prenda.C_CAMISA, marca="Abito",
            color="Negro", talle="M", origen=Prenda.O_NAC,
        )

        response = self.client.get(reverse("prendas:editar", args=[prenda.pk]))

        self.assertContains(response, 'id="origenField" style="display:none"')
        self.assertEqual(prenda.origen, Prenda.O_IMP)

    def test_editar_chaleco_oculta_selector_y_mantiene_origen_nacional(self):
        prenda = Prenda.objects.create(
            codigo="CH-AUTO", categoria=Prenda.C_CHALECO, marca="Boiler",
            color="Negro", talle="M", origen=Prenda.O_IMP,
        )

        response = self.client.get(reverse("prendas:editar", args=[prenda.pk]))

        self.assertContains(response, 'id="origenField" style="display:none"')
        self.assertEqual(prenda.origen, Prenda.O_NAC)
