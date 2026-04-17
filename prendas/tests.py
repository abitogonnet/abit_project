from datetime import date

from django.test import TestCase
from django.urls import reverse

from alquileres.models import Alquiler, AlquilerItem

from .forms import PrendaForm
from .models import Prenda


class PrendaFormTests(TestCase):
    def test_requires_origen_for_cualquier_saco(self):
        form = PrendaForm(data={
            "categoria": Prenda.C_SACO,
            "marca": "Boiler",
            "color": "Negro",
            "talle": "4",
            "origen": "",
            "notas": "",
        })

        self.assertFalse(form.is_valid())
        self.assertIn("origen", form.errors)

    def test_corbata_admite_color_libre(self):
        form = PrendaForm(data={
            "categoria": Prenda.C_CORBATA,
            "marca": "Boiler",
            "color": "Azul con flores bordadas",
            "talle": "Adulto",
            "origen": "",
            "notas": "",
        })

        self.assertTrue(form.is_valid())


class PrendaViewsTests(TestCase):
    def test_editar_prenda_actualiza_datos_y_mantiene_origen_requerido(self):
        prenda = Prenda.objects.create(
            codigo="SA-001",
            categoria=Prenda.C_SACO,
            marca="Aires Modernos",
            color="Negro",
            talle="22",
            origen=Prenda.O_NAC,
        )

        response = self.client.post(reverse("prendas:editar", args=[prenda.pk]), {
            "categoria": Prenda.C_SACO,
            "marca": "Boiler",
            "color": "Azul oscuro",
            "talle": "4",
            "origen": Prenda.O_IMP,
            "notas": "Corregida",
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        prenda.refresh_from_db()
        self.assertEqual(prenda.marca, "Boiler")
        self.assertEqual(prenda.color, "Azul oscuro")
        self.assertEqual(prenda.talle, "4")
        self.assertEqual(prenda.origen, Prenda.O_IMP)

    def test_buscar_prenda_devuelve_codigos_por_marca_y_talle(self):
        match = Prenda.objects.create(
            codigo="PA-010",
            categoria=Prenda.C_PANTALON,
            marca="Boiler",
            color="Negro",
            talle="40",
        )
        Prenda.objects.create(
            codigo="SA-020",
            categoria=Prenda.C_SACO,
            marca="Boiler",
            color="Azul oscuro",
            talle="42",
        )
        Prenda.objects.create(
            codigo="CA-030",
            categoria=Prenda.C_CAMISA,
            marca="Sportfino",
            color="Blanco",
            talle="40",
        )

        response = self.client.get(reverse("prendas:buscar_prenda"), {
            "marca": "Boiler",
            "talle": "40",
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, match.codigo)
        self.assertNotContains(response, "SA-020")
        self.assertNotContains(response, "CA-030")

    def test_buscar_prenda_muestra_fechas_si_esta_reservada(self):
        match = Prenda.objects.create(
            codigo="PA-011",
            categoria=Prenda.C_PANTALON,
            marca="Boiler",
            color="Negro",
            talle="41",
            estado=Prenda.E_RES,
        )
        alquiler = Alquiler.objects.create(
            fecha_visita=date(2026, 4, 16),
            fecha_reserva=date(2026, 4, 16),
            fecha_entrega=date(2026, 4, 20),
            fecha_devolucion=date(2026, 4, 25),
            cliente_nombre="Pedro",
            cliente_telefono="1234",
            persona1_nombre="Pedro",
            total_bruto="1000",
            sena="0",
            metodo_sena="",
        )
        AlquilerItem.objects.create(alquiler=alquiler, persona_num=1, prenda=match)

        response = self.client.get(reverse("prendas:buscar_prenda"), {
            "marca": "Boiler",
            "talle": "41",
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "20/04/2026")
        self.assertContains(response, "25/04/2026")

    def test_buscar_prenda_filtra_por_origen_sin_importar_la_marca(self):
        importado = Prenda.objects.create(
            codigo="SA-090",
            categoria=Prenda.C_SACO,
            marca="Boiler",
            color="Negro",
            talle="4",
            origen=Prenda.O_IMP,
        )
        Prenda.objects.create(
            codigo="SA-091",
            categoria=Prenda.C_SACO,
            marca="Boiler",
            color="Negro",
            talle="4",
            origen=Prenda.O_NAC,
        )

        response = self.client.get(reverse("prendas:buscar_prenda"), {
            "marca": "Boiler",
            "talle": "4",
            "origen": Prenda.O_IMP,
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, importado.codigo)
        self.assertNotContains(response, "SA-091")

    def test_buscar_prenda_muestra_todas_las_reservas_activas(self):
        match = Prenda.objects.create(
            codigo="PA-012",
            categoria=Prenda.C_PANTALON,
            marca="Boiler",
            color="Negro",
            talle="42",
            estado=Prenda.E_RES,
        )
        alquiler_abril = Alquiler.objects.create(
            fecha_visita=date(2026, 4, 10),
            fecha_reserva=date(2026, 4, 10),
            fecha_entrega=date(2026, 4, 20),
            fecha_devolucion=date(2026, 4, 25),
            cliente_nombre="Pedro",
            cliente_telefono="1234",
            persona1_nombre="Pedro",
            total_bruto="1000",
            sena="0",
            metodo_sena="",
        )
        alquiler_mayo = Alquiler.objects.create(
            fecha_visita=date(2026, 5, 1),
            fecha_reserva=date(2026, 5, 1),
            fecha_entrega=date(2026, 5, 30),
            fecha_devolucion=date(2026, 6, 2),
            cliente_nombre="Lucas",
            cliente_telefono="5678",
            persona1_nombre="Lucas",
            total_bruto="1000",
            sena="0",
            metodo_sena="",
        )
        AlquilerItem.objects.create(alquiler=alquiler_abril, persona_num=1, prenda=match)
        AlquilerItem.objects.create(alquiler=alquiler_mayo, persona_num=1, prenda=match)

        response = self.client.get(reverse("prendas:buscar_prenda"), {
            "marca": "Boiler",
            "talle": "42",
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "20/04/2026")
        self.assertContains(response, "25/04/2026")
        self.assertContains(response, "30/05/2026")
        self.assertContains(response, "02/06/2026")

    def test_stock_permite_eliminar_prenda_sin_alquileres(self):
        prenda = Prenda.objects.create(
            codigo="ZA-001",
            categoria=Prenda.C_ZAPATOS,
            marca="Boiler",
            color="Negro",
            talle="40",
        )

        response = self.client.post(reverse("prendas:stock"), {
            "prenda_id": prenda.id,
            "accion": "eliminar",
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Prenda.objects.filter(id=prenda.id).exists())

    def test_stock_no_elimina_prenda_con_alquileres_asociados(self):
        prenda = Prenda.objects.create(
            codigo="SA-050",
            categoria=Prenda.C_SACO,
            marca="Boiler",
            color="Negro",
            talle="6",
            estado=Prenda.E_RES,
        )
        alquiler = Alquiler.objects.create(
            fecha_visita=date(2026, 4, 16),
            fecha_reserva=date(2026, 4, 16),
            fecha_entrega=date(2026, 4, 20),
            fecha_devolucion=date(2026, 4, 25),
            cliente_nombre="Luis",
            cliente_telefono="1234",
            persona1_nombre="Luis",
            total_bruto="1000",
            sena="0",
            metodo_sena="",
        )
        AlquilerItem.objects.create(alquiler=alquiler, persona_num=1, prenda=prenda)

        response = self.client.post(reverse("prendas:stock"), {
            "prenda_id": prenda.id,
            "accion": "eliminar",
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(Prenda.objects.filter(id=prenda.id).exists())
