from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Actividad, PerfilUsuario


@override_settings(SECURE_SSL_REDIRECT=False)
class AccesoTests(TestCase):
    def crear_usuario(self, username, rol, *, debe_cambiar_password=False):
        user = User.objects.create_user(username, password="ClaveSegura-2026!")
        PerfilUsuario.objects.create(
            user=user,
            nombre=username.title(),
            rol=rol,
            debe_cambiar_password=debe_cambiar_password,
        )
        return user

    def test_sin_login_redirige_home_y_stock(self):
        for url in (reverse("alquileres:home"), reverse("prendas:stock")):
            response = self.client.get(url)
            self.assertRedirects(response, f"{reverse('cuentas:login')}?next={url}", fetch_redirect_response=False)

    @patch.dict("os.environ", {"INITIAL_SETUP_SECRET": "secreto-prueba"})
    def test_configuracion_inicial_crea_un_solo_propietario(self):
        response = self.client.post(reverse("cuentas:configuracion_inicial"), {
            "setup_secret": "secreto-prueba", "nombre": "Bautista", "username": "bautista",
            "password1": "ClaveSegura-2026!", "password2": "ClaveSegura-2026!",
        })
        self.assertRedirects(response, reverse("cuentas:login"))
        self.assertEqual(PerfilUsuario.objects.get().rol, PerfilUsuario.PROPIETARIO)
        self.assertFalse(PerfilUsuario.objects.get().debe_cambiar_password)
        self.assertTrue(User.objects.get(username="bautista").check_password("ClaveSegura-2026!"))
        self.assertRedirects(self.client.get(reverse("cuentas:configuracion_inicial")), reverse("cuentas:login"))

    def test_empleado_no_accede_finanzas_y_no_ve_actividad_financiera(self):
        empleado = self.crear_usuario("nano", PerfilUsuario.EMPLEADO)
        self.client.force_login(empleado)
        self.assertEqual(self.client.get(reverse("gastos:home")).status_code, 403)
        Actividad.objects.create(usuario=empleado, usuario_nombre="Nano", accion="Operó stock", categoria=Actividad.STOCK)
        Actividad.objects.create(usuario=empleado, usuario_nombre="Nano", accion="Creó gasto", categoria=Actividad.FINANZAS, es_financiera=True)
        content = self.client.get(reverse("cuentas:actividad")).content.decode()
        self.assertIn("Operó stock", content)
        self.assertNotIn("Creó gasto", content)

    def test_admin_finanzas_pero_no_usuarios(self):
        admin = self.crear_usuario("tadeo", PerfilUsuario.ADMINISTRADOR)
        self.client.force_login(admin)
        self.assertEqual(self.client.get(reverse("gastos:home")).status_code, 200)
        self.assertEqual(self.client.get(reverse("cuentas:usuarios")).status_code, 403)

    def test_inactivo_no_puede_iniciar_sesion(self):
        user = self.crear_usuario("lucas", PerfilUsuario.EMPLEADO)
        user.is_active = False
        user.save()
        response = self.client.post(reverse("cuentas:login"), {"username": "lucas", "password": "ClaveSegura-2026!"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_usuario_creado_por_propietario_debe_cambiar_password(self):
        propietario = self.crear_usuario("bautista", PerfilUsuario.PROPIETARIO)
        propietario.perfil.debe_cambiar_password = False
        propietario.perfil.save()
        self.client.force_login(propietario)
        response = self.client.post(reverse("cuentas:usuario_crear"), {
            "nombre": "Nano", "username": "nano", "rol": PerfilUsuario.EMPLEADO,
            "password1": "Temporal-2026!", "password2": "Temporal-2026!",
        })
        self.assertRedirects(response, reverse("cuentas:usuarios"))
        self.assertTrue(User.objects.get(username="nano").perfil.debe_cambiar_password)

    def test_cambio_personal_limpia_pendiente_y_mantiene_sesion(self):
        user = self.crear_usuario("nano", PerfilUsuario.EMPLEADO)
        self.client.force_login(user)
        response = self.client.post(reverse("cuentas:cambiar_password"), {
            "old_password": "ClaveSegura-2026!",
            "new_password1": "NuevaClave-2026!",
            "new_password2": "NuevaClave-2026!",
        })
        self.assertRedirects(response, reverse("alquileres:home"))
        user.refresh_from_db()
        self.assertTrue(user.check_password("NuevaClave-2026!"))
        self.assertFalse(user.perfil.debe_cambiar_password)
        self.assertIn("_auth_user_id", self.client.session)

    def test_password_pendiente_redirige_sin_bucle_y_permite_salir(self):
        user = self.crear_usuario(
            "pendiente",
            PerfilUsuario.EMPLEADO,
            debe_cambiar_password=True,
        )
        response = self.client.post(reverse("cuentas:login"), {
            "username": "pendiente",
            "password": "ClaveSegura-2026!",
        })
        self.assertRedirects(response, reverse("cuentas:cambiar_password"))
        self.assertEqual(self.client.get(reverse("cuentas:cambiar_password")).status_code, 200)
        self.assertRedirects(
            self.client.get(reverse("alquileres:home")),
            reverse("cuentas:cambiar_password"),
        )
        self.assertRedirects(
            self.client.post(reverse("cuentas:logout")),
            reverse("cuentas:login"),
        )

    def test_logout_post_invalida_sesion(self):
        user = self.crear_usuario("lucas", PerfilUsuario.EMPLEADO)
        self.client.force_login(user)
        self.assertRedirects(self.client.post(reverse("cuentas:logout")), reverse("cuentas:login"))
        self.assertNotIn("_auth_user_id", self.client.session)
