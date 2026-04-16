from datetime import date

from django.test import TestCase
from django.urls import reverse

from prendas.models import Prenda

from .models import Alquiler, AlquilerItem


class AlquileresViewsTests(TestCase):
    def _base_payload(self):
        payload = {
            "fecha_reserva": "2026-04-16",
            "fecha_entrega": "2026-04-20",
            "fecha_devolucion": "2026-04-25",
            "cliente_nombre": "Juan Perez",
            "cliente_telefono": "1111",
            "persona1_nombre": "Juan",
            "persona2_nombre": "",
            "total_bruto": "1000",
            "descuento_pct": "",
            "sena": "100",
            "metodo_sena": Alquiler.MP_EFEC,
            "tiene_persona2": "",
            "p1_saco": "",
            "p1_pantalon": "",
            "p1_camisa": "",
            "p1_chaleco": "",
            "p1_mono": "",
            "p1_corbata": "",
            "p1_zapatos": "",
            "p1_cinturon": "",
            "p1_ruedo_pantalon_valor": "",
            "p1_ruedo_pantalon_tipo": "",
            "p1_ruedo_saco_valor": "",
            "p1_ruedo_saco_tipo": "",
            "p2_saco": "",
            "p2_pantalon": "",
            "p2_camisa": "",
            "p2_chaleco": "",
            "p2_mono": "",
            "p2_corbata": "",
            "p2_zapatos": "",
            "p2_cinturon": "",
            "p2_ruedo_pantalon_valor": "",
            "p2_ruedo_pantalon_tipo": "",
            "p2_ruedo_saco_valor": "",
            "p2_ruedo_saco_tipo": "",
        }
        return payload

    def _create_alquiler(self, suffix, created_prenda=None):
        alquiler = Alquiler.objects.create(
            fecha_visita=date(2026, 4, 16),
            fecha_reserva=date(2026, 4, 16),
            fecha_entrega=date(2026, 4, 20),
            fecha_devolucion=date(2026, 4, 25),
            cliente_nombre=f"Cliente {suffix}",
            cliente_telefono=f"11{suffix}",
            persona1_nombre=f"Persona {suffix}",
            total_bruto="1000",
            sena="0",
            metodo_sena="",
        )
        if created_prenda:
            AlquilerItem.objects.create(alquiler=alquiler, persona_num=1, prenda=created_prenda)
        return alquiler

    def test_crear_alquiler_reserva_prenda_y_asigna_fecha_visita(self):
        saco = Prenda.objects.create(
            codigo="SA-001",
            categoria=Prenda.C_SACO,
            marca="Boiler",
            color="Negro",
            talle="4",
        )

        payload = self._base_payload()
        payload["p1_saco"] = saco.codigo

        response = self.client.post(reverse("alquileres:crear"), payload, follow=True)

        self.assertEqual(response.status_code, 200)
        alquiler = Alquiler.objects.get()
        self.assertEqual(alquiler.fecha_visita, alquiler.fecha_reserva)
        self.assertEqual(alquiler.metodo_sena, Alquiler.MP_EFEC)
        self.assertTrue(AlquilerItem.objects.filter(alquiler=alquiler, prenda=saco).exists())

        saco.refresh_from_db()
        self.assertEqual(saco.estado, Prenda.E_RES)

    def test_eliminar_alquiler_libera_prendas(self):
        saco = Prenda.objects.create(
            codigo="SA-002",
            categoria=Prenda.C_SACO,
            marca="Boiler",
            color="Azul oscuro",
            talle="6",
            estado=Prenda.E_RES,
        )
        alquiler = self._create_alquiler("A", created_prenda=saco)

        response = self.client.post(reverse("alquileres:ver"), {
            "alq_id": alquiler.id,
            "accion": "eliminar",
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Alquiler.objects.filter(id=alquiler.id).exists())
        saco.refresh_from_db()
        self.assertEqual(saco.estado, Prenda.E_DISP)

    def test_ver_alquileres_muestra_primero_el_ultimo_cargado(self):
        viejo = self._create_alquiler("Viejo")
        nuevo = self._create_alquiler("Nuevo")

        response = self.client.get(reverse("alquileres:ver"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertLess(content.index(f"#{nuevo.id}"), content.index(f"#{viejo.id}"))

    def test_crear_alquiler_permited_usar_prenda_si_se_libera_antes_de_la_entrega(self):
        saco = Prenda.objects.create(
            codigo="SA-010",
            categoria=Prenda.C_SACO,
            marca="Boiler",
            color="Negro",
            talle="4",
            estado=Prenda.E_RES,
        )
        alquiler_actual = Alquiler.objects.create(
            fecha_visita=date(2026, 4, 10),
            fecha_reserva=date(2026, 4, 10),
            fecha_entrega=date(2026, 4, 20),
            fecha_devolucion=date(2026, 4, 25),
            cliente_nombre="Actual",
            cliente_telefono="1111",
            persona1_nombre="Actual",
            total_bruto="1000",
            sena="0",
            metodo_sena="",
            estado_alquiler=Alquiler.EST_RESERVADO,
        )
        AlquilerItem.objects.create(alquiler=alquiler_actual, persona_num=1, prenda=saco)

        payload = self._base_payload()
        payload["fecha_reserva"] = "2026-05-20"
        payload["fecha_entrega"] = "2026-05-30"
        payload["fecha_devolucion"] = "2026-06-02"
        payload["p1_saco"] = saco.codigo

        response = self.client.post(reverse("alquileres:crear"), payload, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Alquiler.objects.count(), 2)
        self.assertEqual(AlquilerItem.objects.filter(prenda=saco).count(), 2)

    def test_crear_alquiler_bloquea_prenda_si_se_pisan_las_fechas(self):
        saco = Prenda.objects.create(
            codigo="SA-011",
            categoria=Prenda.C_SACO,
            marca="Boiler",
            color="Azul oscuro",
            talle="6",
            estado=Prenda.E_RES,
        )
        alquiler_actual = Alquiler.objects.create(
            fecha_visita=date(2026, 4, 10),
            fecha_reserva=date(2026, 4, 10),
            fecha_entrega=date(2026, 4, 20),
            fecha_devolucion=date(2026, 4, 25),
            cliente_nombre="Actual",
            cliente_telefono="1111",
            persona1_nombre="Actual",
            total_bruto="1000",
            sena="0",
            metodo_sena="",
            estado_alquiler=Alquiler.EST_RESERVADO,
        )
        AlquilerItem.objects.create(alquiler=alquiler_actual, persona_num=1, prenda=saco)

        payload = self._base_payload()
        payload["fecha_reserva"] = "2026-04-15"
        payload["fecha_entrega"] = "2026-04-24"
        payload["fecha_devolucion"] = "2026-04-28"
        payload["p1_saco"] = saco.codigo

        response = self.client.post(reverse("alquileres:crear"), payload, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Alquiler.objects.count(), 1)
        self.assertContains(response, "20/04/2026 al 25/04/2026")

    def test_eliminar_alquiler_mantiene_reservada_prenda_si_tiene_otro_alquiler_activo(self):
        saco = Prenda.objects.create(
            codigo="SA-012",
            categoria=Prenda.C_SACO,
            marca="Boiler",
            color="Negro",
            talle="8",
            estado=Prenda.E_RES,
        )
        actual = Alquiler.objects.create(
            fecha_visita=date(2026, 4, 10),
            fecha_reserva=date(2026, 4, 10),
            fecha_entrega=date(2026, 4, 20),
            fecha_devolucion=date(2026, 4, 25),
            cliente_nombre="Actual",
            cliente_telefono="1111",
            persona1_nombre="Actual",
            total_bruto="1000",
            sena="0",
            metodo_sena="",
            estado_alquiler=Alquiler.EST_RESERVADO,
        )
        futuro = Alquiler.objects.create(
            fecha_visita=date(2026, 5, 1),
            fecha_reserva=date(2026, 5, 1),
            fecha_entrega=date(2026, 5, 30),
            fecha_devolucion=date(2026, 6, 2),
            cliente_nombre="Futuro",
            cliente_telefono="2222",
            persona1_nombre="Futuro",
            total_bruto="1000",
            sena="0",
            metodo_sena="",
            estado_alquiler=Alquiler.EST_RESERVADO,
        )
        AlquilerItem.objects.create(alquiler=actual, persona_num=1, prenda=saco)
        AlquilerItem.objects.create(alquiler=futuro, persona_num=1, prenda=saco)

        response = self.client.post(reverse("alquileres:ver"), {
            "alq_id": actual.id,
            "accion": "eliminar",
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        saco.refresh_from_db()
        self.assertEqual(saco.estado, Prenda.E_RES)
