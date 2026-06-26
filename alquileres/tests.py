from datetime import date
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .forms import AlquilerEdicionForm, AlquilerForm, SHORT_POR_CATEGORIA
from prendas.models import Prenda

from .models import Alquiler, AlquilerItem
from .views import _armar_mensaje_cliente


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
            "p1_saco_numero": "",
            "p1_pantalon": "",
            "p1_pantalon_numero": "",
            "p1_camisa": "",
            "p1_camisa_numero": "",
            "p1_chaleco": "",
            "p1_chaleco_numero": "",
            "p1_mono": "",
            "p1_mono_numero": "",
            "p1_corbata": "",
            "p1_corbata_numero": "",
            "p1_zapatos": "",
            "p1_zapatos_numero": "",
            "p1_cinturon": "",
            "p1_cinturon_numero": "",
            "p1_ruedo_pantalon_valor": "",
            "p1_ruedo_pantalon_tipo": "",
            "p1_ruedo_saco_valor": "",
            "p1_ruedo_saco_tipo": "",
            "p2_saco": "",
            "p2_saco_numero": "",
            "p2_pantalon": "",
            "p2_pantalon_numero": "",
            "p2_camisa": "",
            "p2_camisa_numero": "",
            "p2_chaleco": "",
            "p2_chaleco_numero": "",
            "p2_mono": "",
            "p2_mono_numero": "",
            "p2_corbata": "",
            "p2_corbata_numero": "",
            "p2_zapatos": "",
            "p2_zapatos_numero": "",
            "p2_cinturon": "",
            "p2_cinturon_numero": "",
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

    def _edit_payload(self, alquiler, **overrides):
        prefix = f"alq-edit-{alquiler.id}"
        payload = {
            "alq_id": alquiler.id,
            "accion": "editar",
            f"{prefix}-fecha_reserva": alquiler.fecha_reserva.strftime("%Y-%m-%d"),
            f"{prefix}-fecha_entrega": alquiler.fecha_entrega.strftime("%Y-%m-%d"),
            f"{prefix}-fecha_devolucion": alquiler.fecha_devolucion.strftime("%Y-%m-%d"),
            f"{prefix}-cliente_nombre": alquiler.cliente_nombre,
            f"{prefix}-cliente_telefono": alquiler.cliente_telefono,
            f"{prefix}-persona1_nombre": alquiler.persona1_nombre,
            f"{prefix}-persona2_nombre": alquiler.persona2_nombre,
            f"{prefix}-total_bruto": str(alquiler.total_bruto),
            f"{prefix}-descuento_pct": "" if alquiler.descuento_pct is None else str(alquiler.descuento_pct),
            f"{prefix}-sena": str(alquiler.sena),
            f"{prefix}-metodo_sena": alquiler.metodo_sena,
            f"{prefix}-p1_ruedo_pantalon_valor": "",
            f"{prefix}-p1_ruedo_pantalon_tipo": "",
            f"{prefix}-p1_ruedo_saco_valor": "",
            f"{prefix}-p1_ruedo_saco_tipo": "",
            f"{prefix}-p2_ruedo_pantalon_valor": "",
            f"{prefix}-p2_ruedo_pantalon_tipo": "",
            f"{prefix}-p2_ruedo_saco_valor": "",
            f"{prefix}-p2_ruedo_saco_tipo": "",
        }

        for item in alquiler.items.select_related("prenda"):
            short = SHORT_POR_CATEGORIA[item.prenda.categoria]
            who = f"p{item.persona_num}"
            field_name = f"{prefix}-{who}_{short}"
            payload[field_name] = item.prenda.codigo
            payload[f"{field_name}_numero"] = item.prenda.codigo.split("-", 1)[1]

            if short == "pantalon":
                payload[f"{prefix}-{who}_ruedo_pantalon_valor"] = "" if item.ruedo_valor is None else str(item.ruedo_valor)
                payload[f"{prefix}-{who}_ruedo_pantalon_tipo"] = item.ruedo_tipo
            if short == "saco":
                payload[f"{prefix}-{who}_ruedo_saco_valor"] = "" if item.ruedo_valor is None else str(item.ruedo_valor)
                payload[f"{prefix}-{who}_ruedo_saco_tipo"] = item.ruedo_tipo

        payload.update(overrides)
        return payload

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

    @patch("alquileres.views.timezone.localdate", return_value=date(2026, 4, 24))
    def test_ver_alquileres_prioriza_entrega_mas_cercana_y_deja_cerrados_al_final(self, _mock_localdate):
        cercano = self._create_alquiler("Cercano")
        cercano.fecha_entrega = date(2026, 4, 25)
        cercano.fecha_devolucion = date(2026, 4, 30)
        cercano.save()

        lejano = self._create_alquiler("Lejano")
        lejano.fecha_entrega = date(2026, 5, 20)
        lejano.fecha_devolucion = date(2026, 5, 25)
        lejano.save()

        cerrado = self._create_alquiler("Cerrado")
        cerrado.fecha_entrega = date(2026, 4, 24)
        cerrado.fecha_devolucion = date(2026, 4, 29)
        cerrado.estado_alquiler = Alquiler.EST_CERRADO
        cerrado.save()

        response = self.client.get(reverse("alquileres:ver"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertLess(content.index(f"#{cercano.id}"), content.index(f"#{lejano.id}"))
        self.assertLess(content.index(f"#{lejano.id}"), content.index(f"#{cerrado.id}"))

    def test_ver_alquileres_filtra_por_fecha_entrega_incluyendo_extremos(self):
        inicio = self._create_alquiler("Inicio")
        inicio.fecha_entrega = date(2026, 4, 20)
        inicio.fecha_devolucion = date(2026, 4, 25)
        inicio.save()

        medio = self._create_alquiler("Medio")
        medio.fecha_entrega = date(2026, 4, 22)
        medio.fecha_devolucion = date(2026, 4, 27)
        medio.save()

        fin = self._create_alquiler("Fin")
        fin.fecha_entrega = date(2026, 4, 25)
        fin.fecha_devolucion = date(2026, 4, 30)
        fin.save()

        fuera = self._create_alquiler("Fuera")
        fuera.fecha_entrega = date(2026, 4, 26)
        fuera.fecha_devolucion = date(2026, 5, 1)
        fuera.save()

        response = self.client.get(reverse("alquileres:ver"), {
            "fecha_desde": "2026-04-20",
            "fecha_hasta": "2026-04-25",
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"#{inicio.id}")
        self.assertContains(response, f"#{medio.id}")
        self.assertContains(response, f"#{fin.id}")
        self.assertNotContains(response, f"#{fuera.id}")

    def test_ver_alquileres_muestra_prendas_con_descripcion_y_sin_ver_detallado(self):
        saco = Prenda.objects.create(
            codigo="SA-030",
            categoria=Prenda.C_SACO,
            marca="Boiler",
            color="Negro",
            talle="4",
            origen=Prenda.O_NAC,
        )
        pantalon = Prenda.objects.create(
            codigo="PA-030",
            categoria=Prenda.C_PANTALON,
            marca="Oxford",
            color="Gris",
            talle="42",
            origen=Prenda.O_IMP,
        )
        alquiler = Alquiler.objects.create(
            fecha_visita=date(2026, 4, 16),
            fecha_reserva=date(2026, 4, 16),
            fecha_entrega=date(2026, 4, 20),
            fecha_devolucion=date(2026, 4, 25),
            cliente_nombre="Cliente Detalle",
            cliente_telefono="119999",
            persona1_nombre="Juan",
            persona2_nombre="Pedro",
            total_bruto="2000",
            sena="500",
            metodo_sena=Alquiler.MP_EFEC,
        )
        AlquilerItem.objects.create(
            alquiler=alquiler,
            persona_num=1,
            prenda=saco,
            ruedo_valor="12",
            ruedo_tipo=AlquilerItem.RUEDO_CM,
        )
        AlquilerItem.objects.create(
            alquiler=alquiler,
            persona_num=2,
            prenda=pantalon,
            ruedo_valor="2",
            ruedo_tipo=AlquilerItem.RUEDO_BOTON,
        )

        response = self.client.get(reverse("alquileres:ver"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Ver detallado")
        self.assertContains(response, "Editar")
        self.assertContains(response, "Juan")
        self.assertContains(response, "Pedro")
        self.assertContains(response, "Saco 030")
        self.assertContains(response, "Pantalón 030")
        self.assertContains(response, "Saco Negro Boiler talle 4 Nacional")
        self.assertContains(response, "Pantalón Gris Oxford talle 42 Importado")
        self.assertContains(response, "Ruedo de saco")
        self.assertContains(response, "Ruedo de pantalon")
        self.assertContains(response, "Boiler")
        self.assertContains(response, "Oxford")
        self.assertContains(response, "Negro")
        self.assertContains(response, "Gris")
        self.assertContains(response, "Ruedo")

    def test_ver_alquileres_muestra_resta_en_cero_cuando_el_saldo_ya_fue_pagado(self):
        alquiler = Alquiler.objects.create(
            fecha_visita=date(2026, 4, 16),
            fecha_reserva=date(2026, 4, 16),
            fecha_entrega=date(2026, 4, 20),
            fecha_devolucion=date(2026, 4, 25),
            cliente_nombre="Cliente Pago Completo",
            cliente_telefono="117777",
            persona1_nombre="Juan",
            total_bruto="2000",
            sena="500",
            metodo_sena=Alquiler.MP_EFEC,
            estado_saldo=Alquiler.SAL_PAG,
            metodo_saldo=Alquiler.MP_TRANS,
            saldo_pagado_en=date(2026, 4, 19),
        )

        response = self.client.get(reverse("alquileres:ver"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Abonado: $2000,00")
        self.assertContains(response, "Resta: $0,00")
        self.assertContains(response, "Saldo: Transferencia")

    def test_entregas_muestra_ver_detallado_en_resultados_filtrados(self):
        hoy = timezone.localdate()
        saco = Prenda.objects.create(
            codigo="SA-040",
            categoria=Prenda.C_SACO,
            marca="Boiler",
            color="Azul oscuro",
            talle="6",
        )
        pantalon = Prenda.objects.create(
            codigo="PA-040",
            categoria=Prenda.C_PANTALON,
            marca="Oxford",
            color="Negro",
            talle="40",
        )
        alquiler = Alquiler.objects.create(
            fecha_visita=hoy,
            fecha_reserva=hoy,
            fecha_entrega=hoy,
            fecha_devolucion=hoy + timezone.timedelta(days=2),
            cliente_nombre="Cliente Entrega",
            cliente_telefono="118888",
            persona1_nombre="Juan",
            persona2_nombre="Pedro",
            total_bruto="2500",
            sena="700",
            metodo_sena=Alquiler.MP_EFEC,
        )
        AlquilerItem.objects.create(
            alquiler=alquiler,
            persona_num=1,
            prenda=saco,
            ruedo_valor="11",
            ruedo_tipo=AlquilerItem.RUEDO_CM,
        )
        AlquilerItem.objects.create(
            alquiler=alquiler,
            persona_num=2,
            prenda=pantalon,
            ruedo_valor="1",
            ruedo_tipo=AlquilerItem.RUEDO_BOTON,
        )

        response = self.client.get(reverse("alquileres:entregas"), {
            "hasta": (hoy + timezone.timedelta(days=3)).strftime("%Y-%m-%d"),
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ver detallado")
        self.assertContains(response, "Editar")
        self.assertContains(response, "Retiro / entrega")
        self.assertContains(response, "Saldo restante")
        self.assertContains(response, "Juan")
        self.assertContains(response, "Pedro")
        self.assertContains(response, "SA-040")
        self.assertContains(response, "PA-040")
        self.assertContains(response, "Boiler")
        self.assertContains(response, "Oxford")

    @patch("alquileres.views.timezone.localdate", return_value=date(2026, 6, 8))
    def test_entregas_prioriza_entrega_mas_cercana_y_deja_cerrados_al_final(self, _mock_localdate):
        manana = Alquiler.objects.create(
            fecha_visita=date(2026, 6, 8),
            fecha_reserva=date(2026, 6, 8),
            fecha_entrega=date(2026, 6, 9),
            fecha_devolucion=date(2026, 6, 11),
            cliente_nombre="Cliente Manana",
            cliente_telefono="1111",
            persona1_nombre="Juan",
            total_bruto="1000",
            sena="100",
            metodo_sena=Alquiler.MP_EFEC,
        )
        lejano = Alquiler.objects.create(
            fecha_visita=date(2026, 6, 8),
            fecha_reserva=date(2026, 6, 8),
            fecha_entrega=date(2026, 6, 12),
            fecha_devolucion=date(2026, 6, 14),
            cliente_nombre="Cliente Lejano",
            cliente_telefono="2222",
            persona1_nombre="Pedro",
            total_bruto="1000",
            sena="100",
            metodo_sena=Alquiler.MP_EFEC,
        )
        cerrado = Alquiler.objects.create(
            fecha_visita=date(2026, 6, 8),
            fecha_reserva=date(2026, 6, 8),
            fecha_entrega=date(2026, 6, 8),
            fecha_devolucion=date(2026, 6, 10),
            cliente_nombre="Cliente Cerrado",
            cliente_telefono="3333",
            persona1_nombre="Luis",
            total_bruto="1000",
            sena="100",
            metodo_sena=Alquiler.MP_EFEC,
            estado_alquiler=Alquiler.EST_CERRADO,
        )

        response = self.client.get(reverse("alquileres:entregas"), {
            "hasta": "2026-06-14",
        })

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertLess(content.index(f"#{manana.id}"), content.index(f"#{lejano.id}"))
        self.assertLess(content.index(f"#{lejano.id}"), content.index(f"#{cerrado.id}"))

    def test_entregas_permite_editar_alquiler_desde_lista_filtrada(self):
        hoy = timezone.localdate()
        saco = Prenda.objects.create(
            codigo="SA-043",
            categoria=Prenda.C_SACO,
            marca="Boiler",
            color="Negro",
            talle="4",
        )
        alquiler = Alquiler.objects.create(
            fecha_visita=hoy,
            fecha_reserva=hoy,
            fecha_entrega=hoy,
            fecha_devolucion=hoy + timezone.timedelta(days=2),
            cliente_nombre="Cliente Entrega",
            cliente_telefono="118888",
            persona1_nombre="Juan",
            total_bruto="2000",
            sena="500",
            metodo_sena=Alquiler.MP_EFEC,
        )
        AlquilerItem.objects.create(alquiler=alquiler, persona_num=1, prenda=saco)

        prefix = f"alq-edit-{alquiler.id}"
        response = self.client.post(reverse("alquileres:entregas"), self._edit_payload(
            alquiler,
            **{
                "hasta": (hoy + timezone.timedelta(days=4)).strftime("%Y-%m-%d"),
                f"{prefix}-fecha_reserva": hoy.strftime("%Y-%m-%d"),
                f"{prefix}-fecha_entrega": hoy.strftime("%Y-%m-%d"),
                f"{prefix}-fecha_devolucion": (hoy + timezone.timedelta(days=3)).strftime("%Y-%m-%d"),
                f"{prefix}-cliente_nombre": "Cliente Entrega Editado",
                f"{prefix}-cliente_telefono": "119999",
                f"{prefix}-persona1_nombre": "Juan Editado",
                f"{prefix}-persona2_nombre": "",
                f"{prefix}-total_bruto": "2200",
                f"{prefix}-descuento_pct": "5",
                f"{prefix}-sena": "600",
                f"{prefix}-metodo_sena": Alquiler.MP_TRANS,
            },
        ), follow=True)

        self.assertEqual(response.status_code, 200)
        alquiler.refresh_from_db()
        self.assertEqual(alquiler.cliente_nombre, "Cliente Entrega Editado")
        self.assertEqual(alquiler.persona1_nombre, "Juan Editado")
        self.assertEqual(alquiler.metodo_sena, Alquiler.MP_TRANS)

    def test_ver_alquileres_permite_editar_nombres_pagos_y_fechas(self):
        saco = Prenda.objects.create(
            codigo="SA-041",
            categoria=Prenda.C_SACO,
            marca="Boiler",
            color="Negro",
            talle="4",
        )
        alquiler = Alquiler.objects.create(
            fecha_visita=date(2026, 4, 16),
            fecha_reserva=date(2026, 4, 16),
            fecha_entrega=date(2026, 4, 20),
            fecha_devolucion=date(2026, 4, 25),
            cliente_nombre="Cliente Original",
            cliente_telefono="1111",
            persona1_nombre="Juan",
            total_bruto="1000",
            sena="100",
            metodo_sena=Alquiler.MP_EFEC,
        )
        AlquilerItem.objects.create(alquiler=alquiler, persona_num=1, prenda=saco)

        prefix = f"alq-edit-{alquiler.id}"
        response = self.client.post(reverse("alquileres:ver"), self._edit_payload(
            alquiler,
            **{
                "fecha_desde": "",
                "fecha_hasta": "",
                f"{prefix}-fecha_reserva": "2026-04-18",
                f"{prefix}-fecha_entrega": "2026-04-22",
                f"{prefix}-fecha_devolucion": "2026-04-28",
                f"{prefix}-cliente_nombre": "Cliente Editado",
                f"{prefix}-cliente_telefono": "2222",
                f"{prefix}-persona1_nombre": "Juan Editado",
                f"{prefix}-persona2_nombre": "",
                f"{prefix}-total_bruto": "2000",
                f"{prefix}-descuento_pct": "10",
                f"{prefix}-sena": "500",
                f"{prefix}-metodo_sena": Alquiler.MP_TRANS,
            },
        ), follow=True)

        self.assertEqual(response.status_code, 200)
        alquiler.refresh_from_db()
        self.assertEqual(alquiler.cliente_nombre, "Cliente Editado")
        self.assertEqual(alquiler.cliente_telefono, "2222")
        self.assertEqual(alquiler.persona1_nombre, "Juan Editado")
        self.assertEqual(alquiler.fecha_reserva, date(2026, 4, 18))
        self.assertEqual(alquiler.fecha_entrega, date(2026, 4, 22))
        self.assertEqual(alquiler.fecha_devolucion, date(2026, 4, 28))
        self.assertEqual(alquiler.metodo_sena, Alquiler.MP_TRANS)
        self.assertEqual(alquiler.total_final, 1800)
        self.assertEqual(alquiler.saldo, 1300)

    def test_ver_alquileres_editar_conserva_fechas_si_no_se_reenvian(self):
        saco = Prenda.objects.create(
            codigo="SA-141",
            categoria=Prenda.C_SACO,
            marca="Boiler",
            color="Negro",
            talle="4",
        )
        alquiler = Alquiler.objects.create(
            fecha_visita=date(2026, 4, 16),
            fecha_reserva=date(2026, 4, 16),
            fecha_entrega=date(2026, 4, 20),
            fecha_devolucion=date(2026, 4, 25),
            cliente_nombre="Cliente Original",
            cliente_telefono="1111",
            persona1_nombre="Juan",
            total_bruto="1000",
            sena="100",
            metodo_sena=Alquiler.MP_EFEC,
        )
        AlquilerItem.objects.create(alquiler=alquiler, persona_num=1, prenda=saco)

        prefix = f"alq-edit-{alquiler.id}"
        response = self.client.post(reverse("alquileres:ver"), self._edit_payload(
            alquiler,
            **{
                "fecha_desde": "",
                "fecha_hasta": "",
                f"{prefix}-fecha_reserva": "",
                f"{prefix}-fecha_entrega": "",
                f"{prefix}-fecha_devolucion": "",
                f"{prefix}-cliente_nombre": "Cliente Sin Reescribir Fechas",
            },
        ))

        self.assertEqual(response.status_code, 302)
        alquiler.refresh_from_db()
        self.assertEqual(alquiler.cliente_nombre, "Cliente Sin Reescribir Fechas")
        self.assertEqual(alquiler.fecha_reserva, date(2026, 4, 16))
        self.assertEqual(alquiler.fecha_entrega, date(2026, 4, 20))
        self.assertEqual(alquiler.fecha_devolucion, date(2026, 4, 25))

    def test_formulario_edicion_renderiza_fechas_en_formato_html5(self):
        alquiler = Alquiler.objects.create(
            fecha_visita=date(2026, 4, 16),
            fecha_reserva=date(2026, 4, 16),
            fecha_entrega=date(2026, 4, 20),
            fecha_devolucion=date(2026, 4, 25),
            cliente_nombre="Cliente Formato",
            cliente_telefono="1111",
            persona1_nombre="Juan",
            total_bruto="1000",
            sena="100",
            metodo_sena=Alquiler.MP_EFEC,
        )

        form = AlquilerEdicionForm(
            instance=alquiler,
            prefix=f"alq-edit-{alquiler.id}",
            disponibles={short: [] for short in SHORT_POR_CATEGORIA.values()},
        )

        self.assertIn('value="2026-04-16"', str(form["fecha_reserva"]))
        self.assertIn('value="2026-04-20"', str(form["fecha_entrega"]))
        self.assertIn('value="2026-04-25"', str(form["fecha_devolucion"]))

    def test_ver_alquileres_no_deja_editar_fechas_si_pisa_otra_reserva(self):
        saco = Prenda.objects.create(
            codigo="SA-042",
            categoria=Prenda.C_SACO,
            marca="Boiler",
            color="Azul oscuro",
            talle="6",
            estado=Prenda.E_RES,
        )
        actual = Alquiler.objects.create(
            fecha_visita=date(2026, 4, 16),
            fecha_reserva=date(2026, 4, 16),
            fecha_entrega=date(2026, 4, 20),
            fecha_devolucion=date(2026, 4, 25),
            cliente_nombre="Actual",
            cliente_telefono="1111",
            persona1_nombre="Juan",
            total_bruto="1000",
            sena="100",
            metodo_sena=Alquiler.MP_EFEC,
        )
        futuro = Alquiler.objects.create(
            fecha_visita=date(2026, 5, 1),
            fecha_reserva=date(2026, 5, 1),
            fecha_entrega=date(2026, 5, 30),
            fecha_devolucion=date(2026, 6, 2),
            cliente_nombre="Futuro",
            cliente_telefono="2222",
            persona1_nombre="Pedro",
            total_bruto="1000",
            sena="100",
            metodo_sena=Alquiler.MP_EFEC,
        )
        AlquilerItem.objects.create(alquiler=actual, persona_num=1, prenda=saco)
        AlquilerItem.objects.create(alquiler=futuro, persona_num=1, prenda=saco)

        prefix = f"alq-edit-{actual.id}"
        response = self.client.post(reverse("alquileres:ver"), self._edit_payload(
            actual,
            **{
                "fecha_desde": "",
                "fecha_hasta": "",
                f"{prefix}-fecha_reserva": "2026-05-20",
                f"{prefix}-fecha_entrega": "2026-05-30",
                f"{prefix}-fecha_devolucion": "2026-06-03",
                f"{prefix}-cliente_nombre": actual.cliente_nombre,
                f"{prefix}-cliente_telefono": actual.cliente_telefono,
                f"{prefix}-persona1_nombre": actual.persona1_nombre,
                f"{prefix}-persona2_nombre": "",
                f"{prefix}-total_bruto": "1000",
                f"{prefix}-descuento_pct": "",
                f"{prefix}-sena": "100",
                f"{prefix}-metodo_sena": Alquiler.MP_EFEC,
            },
        ))

        self.assertEqual(response.status_code, 200)
        actual.refresh_from_db()
        self.assertEqual(actual.fecha_entrega, date(2026, 4, 20))
        self.assertContains(response, "SA-042")

    def test_ver_alquileres_permite_editar_prendas_y_ruedos(self):
        pantalon_original = Prenda.objects.create(
            codigo="PA-051",
            categoria=Prenda.C_PANTALON,
            marca="Oxford",
            color="Negro",
            talle="40",
        )
        pantalon_nuevo = Prenda.objects.create(
            codigo="PA-052",
            categoria=Prenda.C_PANTALON,
            marca="Oxford",
            color="Gris",
            talle="42",
        )
        alquiler = Alquiler.objects.create(
            fecha_visita=date(2026, 4, 16),
            fecha_reserva=date(2026, 4, 16),
            fecha_entrega=date(2026, 4, 20),
            fecha_devolucion=date(2026, 4, 25),
            cliente_nombre="Cliente Prendas",
            cliente_telefono="1111",
            persona1_nombre="Juan",
            total_bruto="1000",
            sena="100",
            metodo_sena=Alquiler.MP_EFEC,
        )
        AlquilerItem.objects.create(
            alquiler=alquiler,
            persona_num=1,
            prenda=pantalon_original,
            ruedo_valor="1",
            ruedo_tipo=AlquilerItem.RUEDO_CM,
        )

        prefix = f"alq-edit-{alquiler.id}"
        response = self.client.post(reverse("alquileres:ver"), self._edit_payload(
            alquiler,
            **{
                "fecha_desde": "",
                "fecha_hasta": "",
                f"{prefix}-p1_pantalon": pantalon_nuevo.codigo,
                f"{prefix}-p1_pantalon_numero": "052",
                f"{prefix}-p1_ruedo_pantalon_valor": "3",
                f"{prefix}-p1_ruedo_pantalon_tipo": AlquilerItem.RUEDO_BOTON,
            },
        ), follow=True)

        self.assertEqual(response.status_code, 200)
        item = alquiler.items.select_related("prenda").get(persona_num=1)
        self.assertEqual(item.prenda.codigo, "PA-052")
        self.assertEqual(str(item.ruedo_valor), "3.00")
        self.assertEqual(item.ruedo_tipo, AlquilerItem.RUEDO_BOTON)
        pantalon_original.refresh_from_db()
        pantalon_nuevo.refresh_from_db()
        self.assertEqual(pantalon_original.estado, Prenda.E_DISP)
        self.assertEqual(pantalon_nuevo.estado, Prenda.E_RES)

    def test_ver_alquileres_no_deja_cambiar_prenda_si_esta_ocupada(self):
        saco_actual = Prenda.objects.create(
            codigo="SA-061",
            categoria=Prenda.C_SACO,
            marca="Boiler",
            color="Negro",
            talle="4",
        )
        saco_ocupado = Prenda.objects.create(
            codigo="SA-062",
            categoria=Prenda.C_SACO,
            marca="Boiler",
            color="Azul",
            talle="6",
            estado=Prenda.E_RES,
        )
        alquiler = Alquiler.objects.create(
            fecha_visita=date(2026, 4, 16),
            fecha_reserva=date(2026, 4, 16),
            fecha_entrega=date(2026, 4, 20),
            fecha_devolucion=date(2026, 4, 25),
            cliente_nombre="Cliente Cambio",
            cliente_telefono="1111",
            persona1_nombre="Juan",
            total_bruto="1000",
            sena="100",
            metodo_sena=Alquiler.MP_EFEC,
        )
        otro = Alquiler.objects.create(
            fecha_visita=date(2026, 4, 16),
            fecha_reserva=date(2026, 4, 16),
            fecha_entrega=date(2026, 4, 22),
            fecha_devolucion=date(2026, 4, 27),
            cliente_nombre="Otro",
            cliente_telefono="2222",
            persona1_nombre="Pedro",
            total_bruto="1000",
            sena="100",
            metodo_sena=Alquiler.MP_EFEC,
        )
        AlquilerItem.objects.create(alquiler=alquiler, persona_num=1, prenda=saco_actual)
        AlquilerItem.objects.create(alquiler=otro, persona_num=1, prenda=saco_ocupado)

        prefix = f"alq-edit-{alquiler.id}"
        response = self.client.post(reverse("alquileres:ver"), self._edit_payload(
            alquiler,
            **{
                "fecha_desde": "",
                "fecha_hasta": "",
                f"{prefix}-p1_saco": saco_ocupado.codigo,
                f"{prefix}-p1_saco_numero": "062",
            },
        ))

        self.assertEqual(response.status_code, 200)
        item = alquiler.items.select_related("prenda").get(persona_num=1)
        self.assertEqual(item.prenda.codigo, "SA-061")
        self.assertContains(response, "22/04/2026 al 27/04/2026")

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

    def test_mensaje_cliente_no_muestra_la_marca(self):
        saco = Prenda.objects.create(
            codigo="SA-020",
            categoria=Prenda.C_SACO,
            marca="Boiler",
            color="Negro",
            talle="4",
        )
        alquiler = self._create_alquiler("Mensaje", created_prenda=saco)

        mensaje = _armar_mensaje_cliente(alquiler)

        self.assertIn("- Saco: Negro talle 4", mensaje)
        self.assertNotIn("Boiler", mensaje)

    def test_formulario_expone_busqueda_por_numero_y_prefijo(self):
        form = AlquilerForm(disponibles={})

        self.assertIn("p1_saco_numero", form.fields)
        self.assertEqual(form.fields["p1_saco_numero"].widget.attrs["data-prefix"], "SA")
        self.assertEqual(form.fields["p1_saco"].widget.attrs["data-prefix"], "SA")
        self.assertEqual(form.fields["p2_cinturon_numero"].widget.attrs["data-prefix"], "CI")
