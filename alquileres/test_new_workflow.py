from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from cuentas.models import Actividad, PerfilUsuario
from prendas.models import Prenda

from .models import Alquiler, AlquilerItem, Cliente
from .forms import CATS
from .views import _vincular_cliente
from .whatsapp import generar_enlace_whatsapp, mensaje_recordatorio, normalizar_telefono


class NewWorkflowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("nano", password="ClaveSegura-2026!")
        PerfilUsuario.objects.create(user=self.user, nombre="Nano", rol=PerfilUsuario.EMPLEADO, debe_cambiar_password=False)
        self.client.force_login(self.user)

    def alquiler(self, **overrides):
        today = timezone.localdate()
        values = {
            "cliente_nombre": "Juan Pérez", "cliente_telefono": "2213540416",
            "fecha_visita": today, "fecha_reserva": today, "fecha_entrega": today,
            "fecha_devolucion": today + timedelta(days=2), "persona1_nombre": "Juan",
            "total_bruto": Decimal("100000"), "sena": Decimal("20000"),
            "metodo_sena": Alquiler.MP_EFEC,
        }
        values.update(overrides)
        return Alquiler.objects.create(**values)

    def create_payload(self, prenda, **overrides):
        today = timezone.localdate()
        data = {
            "fecha_reserva": today.isoformat(), "fecha_entrega": today.isoformat(),
            "fecha_devolucion": (today + timedelta(days=2)).isoformat(),
            "cliente_nombre": "Juan Pérez", "cliente_dni": "40123456",
            "cliente_telefono": "2213540416", "persona1_nombre": "Juan",
            "personas_visibles": "1", "total_bruto": "100000", "descuento_pct": "",
            "sena": "20000", "metodo_sena": Alquiler.MP_EFEC,
        }
        for persona in range(1, 7):
            data.setdefault(f"persona{persona}_nombre", "Juan" if persona == 1 else "")
            for short, _categoria in CATS:
                data[f"p{persona}_{short}"] = prenda.codigo if persona == 1 and short == "saco" else ""
                data[f"p{persona}_{short}_numero"] = ""
            for short in ("saco", "pantalon"):
                data[f"p{persona}_ruedo_{short}_valor"] = ""
                data[f"p{persona}_ruedo_{short}_tipo"] = ""
        data.update(overrides)
        return data

    def test_dni_existente_reutiliza_cliente_y_actualiza_nombre(self):
        Cliente.objects.create(nombre="Juan Pérez", dni="40123456", telefono="2213540416")
        alquiler = self.alquiler(cliente_nombre="Juan Manuel Pérez")
        # Existir como Cliente (por ejemplo, por una visita web) no lo vuelve
        # recurrente hasta que tenga al menos un alquiler previo válido.
        self.assertFalse(_vincular_cliente(alquiler, "40123456"))
        alquiler.save(update_fields=["cliente"])
        self.assertEqual(Cliente.objects.count(), 1)
        self.assertEqual(alquiler.cliente.nombre, "Juan Manuel Pérez")

    def test_creacion_real_crea_cliente_y_recurrente_muestra_aviso(self):
        primera = Prenda.objects.create(codigo="SA-910", categoria=Prenda.C_SACO, marca="Abito", color="Negro", talle="50", origen=Prenda.O_NAC)
        response = self.client.post(reverse("alquileres:crear"), self.create_payload(primera))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("alquileres:ver"), response.url)
        self.assertEqual(Cliente.objects.count(), 1)
        self.assertIsNotNone(Alquiler.objects.get().cliente_id)
        segunda = Prenda.objects.create(codigo="SA-911", categoria=Prenda.C_SACO, marca="Abito", color="Negro", talle="52", origen=Prenda.O_NAC)
        self.client.post(reverse("alquileres:crear"), self.create_payload(segunda, cliente_nombre="Juan Manuel Pérez"))
        response = self.client.get(reverse("alquileres:crear"))
        self.assertContains(response, "Este cliente ya alquiló anteriormente")
        self.assertEqual(Cliente.objects.count(), 1)
        self.assertEqual(Cliente.objects.get().nombre, "Juan Manuel Pérez")

    def test_boton_guardar_alquiler_envia_la_accion_en_un_solo_toque(self):
        response = self.client.get(reverse("alquileres:crear"))
        self.assertContains(
            response,
            '<button class="ab-btn" type="submit" name="accion" value="crear_alquiler">Guardar alquiler</button>',
            html=True,
        )
        self.assertContains(response, 'class="ab-prenda-card ab-prenda-picker"', html=False)
        self.assertContains(response, "Tocar para cargar")

    def test_ver_alquileres_y_panel_detallado_abren_correctamente(self):
        alquiler = self.alquiler()
        listado = self.client.get(reverse("alquileres:ver"))
        self.assertEqual(listado.status_code, 200)
        self.assertContains(listado, "Ver detallado")
        self.assertContains(listado, "Editar")

        panel = self.client.get(reverse("alquileres:panel", args=[alquiler.pk, "edit"]))
        self.assertEqual(panel.status_code, 200)
        self.assertContains(panel, "Guardar cambios")
        self.assertContains(panel, alquiler.cliente_nombre)

        detalle = self.client.get(reverse("alquileres:panel", args=[alquiler.pk, "detalle"]))
        self.assertEqual(detalle.status_code, 200)
        self.assertContains(detalle, alquiler.cliente_nombre)

    def test_buscador_de_alquileres_encuentra_todos_los_datos_utiles(self):
        cliente = Cliente.objects.create(nombre="María Soto", dni="33222111", telefono="2215558899")
        alquiler = self.alquiler(cliente_nombre="María Soto", cliente_telefono="2215558899", cliente=cliente)
        prenda = Prenda.objects.create(codigo="SA-BUS-77", categoria=Prenda.C_SACO, marca="Abito", color="Azul", talle="50", origen=Prenda.O_NAC)
        AlquilerItem.objects.create(alquiler=alquiler, persona_num=1, prenda=prenda)

        for termino in ("María", "33222111", "2215558899", "SA-BUS-77", f"#{alquiler.id}"):
            with self.subTest(termino=termino):
                response = self.client.get(reverse("alquileres:ver"), {"buscar": termino})
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "María Soto")

    def test_listado_entrega_url_real_para_ver_detallado(self):
        alquiler = self.alquiler()
        response = self.client.get(reverse("alquileres:ver"))
        expected = reverse("alquileres:panel", args=[alquiler.id, "detalle"])
        self.assertContains(response, f'data-panel-url="{expected}"')

    def test_enlace_directo_abre_detalle_y_conserva_todas_las_acciones(self):
        alquiler = self.alquiler()
        response = self.client.get(reverse("alquileres:ver"), {
            "buscar": alquiler.id, "detalle": alquiler.id,
        })
        self.assertContains(response, 'class="ab-detail-toggle ab-detail-toggle-split" open', html=False)
        self.assertContains(response, "Editar")
        self.assertContains(response, "Copiar mensaje")
        self.assertContains(response, "Abrir WhatsApp")

    def test_marcar_entregado_lo_saca_de_entregas_hoy_hasta_la_devolucion(self):
        hoy = timezone.localdate()
        alquiler = self.alquiler(fecha_entrega=hoy, fecha_devolucion=hoy + timedelta(days=2))
        response = self.client.get(reverse("alquileres:home"))
        self.assertIn(alquiler, response.context["entregas_hoy_lista"])

        self.client.post(reverse("alquileres:home"), {
            "alq_id": alquiler.id, "accion": "marcar_entregado",
        })
        response = self.client.get(reverse("alquileres:home"))
        self.assertNotIn(alquiler, response.context["entregas_hoy_lista"])
        self.assertNotIn(alquiler, response.context["devoluciones_hoy_lista"])

    def test_listado_muestra_todos_y_agrupa_reservas_antes_que_finalizados(self):
        hoy = timezone.localdate()
        reservado_cercano = self.alquiler(cliente_nombre="Reserva cercana", fecha_entrega=hoy + timedelta(days=1))
        reservado_lejano = self.alquiler(cliente_nombre="Reserva lejana", fecha_entrega=hoy + timedelta(days=8))
        entregado = self.alquiler(cliente_nombre="Ya entregado", fecha_entrega=hoy - timedelta(days=3), estado_alquiler=Alquiler.EST_ENTREGADO)
        cerrado = self.alquiler(cliente_nombre="Ya cerrado", fecha_entrega=hoy - timedelta(days=10), estado_alquiler=Alquiler.EST_CERRADO)

        response = self.client.get(reverse("alquileres:ver"))
        ids = [alquiler.id for alquiler in response.context["alquileres"]]
        self.assertEqual(ids, [reservado_cercano.id, reservado_lejano.id, cerrado.id, entregado.id])

    def test_alquiler_historico_no_crea_cliente(self):
        alquiler = self.alquiler()
        self.assertIsNone(alquiler.cliente)
        self.assertEqual(Cliente.objects.count(), 0)

    def test_whatsapp_normaliza_local_y_codifica_mensaje(self):
        self.assertEqual(normalizar_telefono("2213540416"), "5492213540416")
        url = generar_enlace_whatsapp("2213540416", "Hola, Juan")
        self.assertTrue(url.startswith("https://wa.me/5492213540416?text="))
        self.assertIn("Hola%2C%20Juan", url)

    def test_recordatorio_usa_cliente_real(self):
        alquiler = self.alquiler()
        self.assertIn("Hola, Juan Pérez", mensaje_recordatorio(alquiler))

    def test_entrega_y_cierre_dejan_pago_y_prenda_disponible(self):
        prenda = Prenda.objects.create(codigo="SA-900", categoria=Prenda.C_SACO, marca="Abito", color="Negro", talle="50", origen=Prenda.O_NAC)
        alquiler = self.alquiler()
        AlquilerItem.objects.create(alquiler=alquiler, persona_num=1, prenda=prenda)
        self.client.post(reverse("alquileres:home"), {"alq_id": alquiler.id, "accion": "marcar_entregado"})
        alquiler.refresh_from_db(); prenda.refresh_from_db()
        self.assertEqual(alquiler.saldo, 0)
        self.assertEqual(alquiler.estado_alquiler, Alquiler.EST_ENTREGADO)
        self.assertEqual(prenda.estado, Prenda.E_ENT)
        self.client.post(reverse("alquileres:home"), {"alq_id": alquiler.id, "accion": "cerrar_alquiler"})
        alquiler.refresh_from_db(); prenda.refresh_from_db()
        self.assertEqual(alquiler.estado_alquiler, Alquiler.EST_CERRADO)
        self.assertEqual(prenda.estado, Prenda.E_DISP)
        self.assertTrue(Actividad.objects.filter(usuario=self.user, accion__icontains="cerrado").exists())

    def test_lavanderia_es_manual_y_se_audita(self):
        prenda = Prenda.objects.create(codigo="SA-901", categoria=Prenda.C_SACO, marca="Abito", color="Negro", talle="50", origen=Prenda.O_NAC)
        self.client.post(reverse("prendas:stock"), {"prenda_id": prenda.id, "estado": Prenda.E_LAV})
        prenda.refresh_from_db()
        self.assertEqual(prenda.estado, Prenda.E_LAV)
        self.assertTrue(Actividad.objects.filter(usuario=self.user, detalle__contains="Lavandería").exists())

    def test_dashboard_muestra_entrega_pendiente_sin_cambiar_estado(self):
        alquiler = self.alquiler(fecha_entrega=timezone.localdate() - timedelta(days=1))
        response = self.client.get(reverse("alquileres:home"))
        self.assertContains(response, "Entrega pendiente de confirmar")
        alquiler.refresh_from_db()
        self.assertEqual(alquiler.estado_alquiler, Alquiler.EST_RESERVADO)

    def test_dashboard_con_entrega_y_devolucion_muestra_tambien_semana(self):
        today = timezone.localdate()
        self.alquiler(cliente_nombre="Entrega hoy")
        self.alquiler(cliente_nombre="Devolución hoy", estado_alquiler=Alquiler.EST_ENTREGADO, fecha_devolucion=today)
        self.alquiler(cliente_nombre="Entrega semanal", fecha_entrega=today + timedelta(days=2))
        response = self.client.get(reverse("alquileres:home"))
        self.assertContains(response, "Entregas de hoy")
        self.assertContains(response, "Devoluciones de hoy")
        self.assertContains(response, "Entregas semanales")

    def test_dashboard_empleado_no_muestra_finanzas(self):
        response = self.client.get(reverse("alquileres:home"))
        self.assertNotContains(response, 'id="menu-finanzas"')
        self.assertContains(response, 'id="menu-operativo"')

    def test_dashboard_propietario_conserva_finanzas(self):
        self.user.perfil.rol = PerfilUsuario.PROPIETARIO
        self.user.perfil.save(update_fields=["rol"])
        response = self.client.get(reverse("alquileres:home"))
        self.assertContains(response, 'id="menu-finanzas"')

    def test_reporte_existente_conserva_demanda_por_talle(self):
        self.user.perfil.rol = PerfilUsuario.PROPIETARIO
        self.user.perfil.save(update_fields=["rol"])
        prenda = Prenda.objects.create(codigo="PA-920", categoria=Prenda.C_PANTALON, marca="Abito", color="Negro", talle="42", origen=Prenda.O_NAC)
        alquiler = self.alquiler()
        AlquilerItem.objects.create(alquiler=alquiler, persona_num=1, prenda=prenda)
        response = self.client.get(reverse("reportes:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Por talle")
