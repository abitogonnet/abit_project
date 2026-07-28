from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import ConfiguracionSitio


class ConfiguracionSitioAdminTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="secret123",
        )
        self.client.force_login(self.user)

    def test_changelist_redirects_to_singleton_change_form(self):
        response = self.client.get(reverse("admin:core_configuracionsitio_changelist"))

        config = ConfiguracionSitio.objects.get()
        self.assertRedirects(
            response,
            reverse("admin:core_configuracionsitio_change", args=[config.pk]),
        )

    def test_change_form_allows_saving_visit_address(self):
        config = ConfiguracionSitio.load()
        response = self.client.post(
            reverse("admin:core_configuracionsitio_change", args=[config.pk]),
            {
                "whatsapp_url": "https://wa.me/message/IXNVRCQIC6YFF1",
                "instagram_url": "https://www.instagram.com/abito.gonnet/",
                "direccion_post_reserva": "Calle 123, Gonnet",
                "mensaje_confirmacion": "Te esperamos.",
                "_save": "Save",
            },
        )

        self.assertEqual(response.status_code, 302)

        config.refresh_from_db()
        self.assertEqual(config.direccion_post_reserva, "Calle 123, Gonnet")


class HomeConversionTests(TestCase):
    def test_home_uses_conversion_copy_and_reservation_cta(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Alquilá un traje que te quede bien")
        self.assertContains(response, reverse("visitas:reservar"))
        self.assertContains(response, "Catálogo real")
        self.assertContains(response, "Cuatro pasos, cero vueltas raras")

    def test_home_hides_empty_catalog_filters(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-filter="all"', html=False)
        self.assertNotContains(response, 'data-filter="camisa"', html=False)
        self.assertNotContains(response, 'data-filter="zapato"', html=False)
        self.assertNotContains(response, 'data-filter="combo"', html=False)
