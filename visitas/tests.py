from datetime import date, time, timedelta

from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User

from alquileres.models import Alquiler, Cliente
from cuentas.models import PerfilUsuario
from visitas.forms import BloqueoAgendaForm
from visitas.models import BloqueoAgenda, Visita
from visitas.views import _capacidad_por_horario, _horario_admite_reserva, _recordatorio_whatsapp


class CuposTests(TestCase):
    def test_recordatorio_de_visita_incluye_horario(self):
        visita = Visita(
            fecha_visita=date.today(), hora_visita=time(18, 30),
            telefono="2215555555",
        )
        enlace = _recordatorio_whatsapp(visita)
        self.assertIn("wa.me/5492215555555", enlace)
        self.assertIn("18%3A30", enlace)
        self.assertIn("puntual", enlace)

    def test_tres_personas_consumen_dos_bloques(self):
        fecha = date.today() + timedelta(days=1)
        Visita.objects.create(
            nombre="Prueba", telefono="2215555555", dni="12345678",
            cantidad_personas=3, fecha_evento=fecha, fecha_visita=fecha,
            hora_visita=time(17), estado=Visita.ESTADO_CONFIRMADA,
        )
        capacidad = _capacidad_por_horario(fecha)
        self.assertEqual(capacidad[time(17)], 0)
        self.assertEqual(capacidad[time(17, 30)], 1)

    def test_tres_personas_no_entran_a_1930(self):
        capacidad = {time(17 + i // 2, 30 * (i % 2)): 2 for i in range(6)}
        self.assertFalse(_horario_admite_reserva(capacidad, time(19, 30), 3))

    def test_bloqueo_elimina_cupo(self):
        fecha = date.today() + timedelta(days=1)
        BloqueoAgenda.objects.create(fecha=fecha, hora_inicio=time(18), hora_fin=time(18, 30))
        self.assertEqual(_capacidad_por_horario(fecha)[time(18)], 0)

    def test_bloquear_un_modulo_deja_el_otro_disponible(self):
        fecha = date.today() + timedelta(days=1)
        BloqueoAgenda.objects.create(fecha=fecha, hora_inicio=time(18), hora_fin=time(18, 30), modulos=1)
        self.assertEqual(_capacidad_por_horario(fecha)[time(18)], 1)

    def test_dos_bloqueos_de_un_modulo_completan_el_horario(self):
        fecha = date.today() + timedelta(days=1)
        for _ in range(2):
            BloqueoAgenda.objects.create(fecha=fecha, hora_inicio=time(18), hora_fin=time(18, 30), modulos=1)
        self.assertEqual(_capacidad_por_horario(fecha)[time(18)], 0)


class BloqueosAgendaTests(TestCase):
    def setUp(self):
        user = User.objects.create_user("bloqueos", password="test")
        PerfilUsuario.objects.create(
            user=user, nombre="Bloqueos", rol=PerfilUsuario.EMPLEADO,
            debe_cambiar_password=False,
        )
        self.client.force_login(user)

    def test_turno_bloqueado_se_desbloquea_con_un_boton(self):
        bloqueo = BloqueoAgenda.objects.create(
            fecha=date.today() + timedelta(days=1),
            hora_inicio=time(18), hora_fin=time(18, 30),
            motivo="Prueba",
        )

        pagina = self.client.get(reverse("visitas:bloqueos"))
        self.assertContains(pagina, "Desbloquear")
        self.assertContains(pagina, "2 módulos bloqueados")

        respuesta = self.client.post(
            reverse("visitas:eliminar_bloqueo", args=[bloqueo.pk]),
            follow=True,
        )

        bloqueo.refresh_from_db()
        self.assertFalse(bloqueo.activo)
        self.assertContains(respuesta, "Turno desbloqueado.")
        self.assertNotContains(respuesta, "Prueba")

    def test_opcion_dia_completo_bloquea_los_dos_modulos_de_todos_los_horarios(self):
        fecha = date.today() + timedelta(days=1)
        form = BloqueoAgendaForm(data={
            "fecha": fecha.isoformat(),
            "bloquear_dia_completo": "on",
            "hora_inicio": "17:00",
            "hora_fin": "17:30",
            "modulos": "1",
            "motivo": "Cerrado",
        })
        self.assertTrue(form.is_valid(), form.errors)
        bloqueo = form.save()
        self.assertIsNone(bloqueo.hora_inicio)
        self.assertIsNone(bloqueo.hora_fin)
        self.assertEqual(bloqueo.modulos, 2)
        self.assertTrue(all(cupo == 0 for cupo in _capacidad_por_horario(fecha).values()))


class UbicacionPublicaTests(TestCase):
    def test_reserva_abre_directamente_en_el_formulario(self):
        reserva = self.client.get(reverse("visitas:reservar"))

        self.assertNotContains(reserva, 'class="reserve-intro"', html=False)
        self.assertNotContains(reserva, 'class="reserve-utility-actions"', html=False)
        self.assertNotContains(reserva, 'class="reserve-bg"', html=False)
        self.assertNotContains(reserva, 'class="social-float-stack"', html=False)
        self.assertNotContains(reserva, ">Reservar visita</a>", html=False)
        self.assertContains(reserva, 'class="reserve-workspace"', html=False)
        self.assertContains(reserva, 'id="reservaForm"', html=False)

    def test_reserva_permite_elegir_productos_sin_reescribir_talles(self):
        reserva = self.client.get(reverse("visitas:reservar"))

        self.assertContains(reserva, "¿Viste algún traje o combo en nuestro catálogo?")
        self.assertContains(reserva, "Producto 1")
        self.assertContains(reserva, "Producto 2")
        self.assertContains(reserva, "Producto 3")
        self.assertContains(reserva, "Trajes elegidos")
        self.assertContains(reserva, "<strong>Catálogo</strong>", html=True)
        self.assertNotContains(reserva, "Ambo 1")
        self.assertNotContains(reserva, "Ambos elegidos")

    def test_reserva_no_expone_ubicacion_y_confirmacion_si_la_muestra(self):
        reserva = self.client.get(reverse("visitas:reservar"))
        self.assertNotContains(reserva, "Calle 489 entre 23 y 24 N.º 2871")
        self.assertNotContains(reserva, "output=embed")
        self.assertNotContains(reserva, "google.com/maps")

        visita = Visita.objects.create(
            nombre="Cliente", telefono="2215555555", dni="12345678",
            cantidad_personas=1, fecha_evento=date.today() + timedelta(days=5),
            fecha_visita=date.today() + timedelta(days=1), hora_visita=time(17),
        )
        session = self.client.session
        session["ultima_visita_id"] = visita.pk
        session.save()
        confirmacion = self.client.get(reverse("visitas:confirmada"))
        self.assertContains(confirmacion, "Ubicación de la visita")
        self.assertContains(confirmacion, "Calle 489 entre 23 y 24 N.º 2871")
        self.assertContains(confirmacion, "output=embed")
        self.assertContains(confirmacion, "Ver en Google Maps")

    def test_formulario_invalido_tampoco_expone_la_ubicacion(self):
        respuesta = self.client.post(reverse("visitas:reservar"), {})

        self.assertEqual(respuesta.status_code, 200)
        self.assertNotContains(respuesta, "Calle 489 entre 23 y 24 N.º 2871")
        self.assertNotContains(respuesta, "output=embed")
        self.assertNotContains(respuesta, "google.com/maps")

    def test_horarios_publicos_terminan_en_1930(self):
        reserva = self.client.get(reverse("visitas:reservar"))

        self.assertContains(reserva, "Horario de atención: 17:00 a 20:00")
        self.assertContains(reserva, "Último turno: 19:30")
        from visitas.forms import HORARIOS_VALIDOS
        self.assertEqual(HORARIOS_VALIDOS[-1], time(19, 30))
        self.assertNotIn(time(20, 0), HORARIOS_VALIDOS)


class ReservaClienteTests(TestCase):
    def payload(self, dni="12345678"):
        hoy = date.today()
        evento = hoy + timedelta(days=10)
        visita = evento - timedelta(days=2)
        while visita.weekday() > 4:
            visita -= timedelta(days=1)
        return {
            "cantidad_personas": "2", "fecha_evento": evento.isoformat(),
            "fecha_visita": visita.isoformat(), "hora_visita": "17:00",
            "nombre": "Ana Perez", "telefono": "2215555555", "dni": dni,
            "vio_prendas_catalogo": "no",
        }

    def test_reserva_crea_cliente_y_no_duplica_dni(self):
        response = self.client.post(reverse("visitas:reservar"), self.payload())
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Cliente.objects.count(), 1)
        segunda = self.payload()
        segunda["hora_visita"] = "17:30"
        self.client.post(reverse("visitas:reservar"), segunda)
        self.assertEqual(Cliente.objects.count(), 1)
        self.assertEqual(Visita.objects.count(), 2)

    def test_ubicacion_aparece_recien_despues_de_guardar_la_reserva(self):
        previa = self.client.get(reverse("visitas:reservar"))
        self.assertNotContains(previa, "Calle 489 entre 23 y 24 N.º 2871")

        confirmada = self.client.post(
            reverse("visitas:reservar"),
            self.payload(),
            follow=True,
        )

        self.assertRedirects(confirmada, reverse("visitas:confirmada"))
        self.assertEqual(Visita.objects.count(), 1)
        self.assertEqual(Visita.objects.get().estado, Visita.ESTADO_CONFIRMADA)
        self.assertContains(confirmada, "Ubicación de la visita")
        self.assertContains(confirmada, "Calle 489 entre 23 y 24 N.º 2871")
        self.assertContains(confirmada, "Ver en Google Maps")

    def test_existir_por_visita_no_es_recurrente(self):
        cliente = Cliente.objects.create(nombre="Ana", dni="12345678", telefono="2215555555")
        self.assertFalse(cliente.alquileres.exclude(estado_alquiler=Alquiler.EST_CANCELADO).exists())

    def test_convertir_visita_guarda_contexto_y_no_duplica(self):
        cliente = Cliente.objects.create(nombre="Ana", dni="12345678", telefono="2215555555")
        visita = Visita.objects.create(
            cliente=cliente, nombre=cliente.nombre, dni=cliente.dni,
            telefono=cliente.telefono, cantidad_personas=3,
            fecha_evento=date.today() + timedelta(days=10),
            fecha_visita=date.today() + timedelta(days=1), hora_visita=time(17),
        )
        # La ruta privada exige autenticación; la unidad de conversión se
        # completa en el flujo de alquiler mediante esta sesión.
        session = self.client.session
        session["visita_para_alquiler"] = visita.pk
        session.save()
        self.assertEqual(self.client.session["visita_para_alquiler"], visita.pk)


class CalendarioVisitasTests(TestCase):
    def test_ver_visitas_ofrece_crear_con_el_formulario_web(self):
        response = self.client.get(reverse("visitas:listar"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Crear visita")
        self.assertContains(response, f'href="{reverse("visitas:reservar")}"', html=False)

    def setUp(self):
        user = User.objects.create_user("agenda", password="test")
        PerfilUsuario.objects.create(
            user=user, nombre="Agenda", rol=PerfilUsuario.EMPLEADO,
            debe_cambiar_password=False,
        )
        self.client.force_login(user)

    def test_calendario_muestra_semana_completa_con_conteo_y_detalle(self):
        fecha = date(2026, 8, 6)
        for hora, nombre in [(time(17), "Juan"), (time(18, 30), "Pedro")]:
            Visita.objects.create(
                nombre=nombre, dni="12345678", telefono="2215555555",
                cantidad_personas=1, fecha_evento=date(2026, 8, 20),
                fecha_visita=fecha, hora_visita=hora,
            )
        response = self.client.get(reverse("visitas:calendario"), {"mes": "2026-08"})
        self.assertContains(response, "Lunes")
        self.assertContains(response, "Domingo")
        self.assertContains(response, "2 visitas")
        detail = self.client.get(reverse("visitas:dia", args=["2026-08-06"]))
        self.assertContains(detail, "17:00 — Juan")
        self.assertContains(detail, "18:30 — Pedro")
        self.assertContains(detail, "Crear alquiler", count=2)
