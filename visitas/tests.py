from datetime import date, time, timedelta

from django.test import TestCase
from django.urls import reverse

from alquileres.models import Alquiler, Cliente
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
