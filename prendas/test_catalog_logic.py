from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from cuentas.models import Actividad, PerfilUsuario

from .forms import CAMISA_SACO_TALLES, PANTALON_NUM, TAM_NINO_ADULTO, ZAPATOS_NUM, ColorForm, PrendaForm
from .models import Color, Prenda


class CatalogLogicTests(TestCase):
    def setUp(self):
        for nombre in ("Azul Francia", "Negro", "Marron"):
            Color.objects.get_or_create(clave_normalizada=Color.normalizar_clave(nombre), defaults={"nombre": nombre})

    def payload(self, categoria, **overrides):
        data = {"categoria": categoria, "marca": "Abito", "color": "Negro", "talle": "Adulto", "origen": Prenda.O_NAC, "notas": ""}
        data.update(overrides)
        return data

    def test_color_duplicado_no_distingue_mayusculas_ni_espacios(self):
        form = ColorForm({"nombre": "  azul   francia "})
        self.assertFalse(form.is_valid())
        self.assertIn("ya existe", str(form.errors))

    def test_corbata_conserva_color_libre(self):
        form = PrendaForm(self.payload(Prenda.C_CORBATA, color="Azul con rayas blancas", talle="Adulto"))
        self.assertTrue(form.is_valid(), form.errors)

    def test_restringidos_rechazan_color_fuera_del_catalogo(self):
        form = PrendaForm(self.payload(Prenda.C_SACO, color="Inventado", talle="50"))
        self.assertFalse(form.is_valid())
        self.assertIn("color", form.errors)

    def test_talles_son_las_listas_solicitadas(self):
        self.assertEqual(PANTALON_NUM, [str(n) for n in range(2, 77, 2)])
        self.assertEqual(ZAPATOS_NUM, [str(n) for n in range(30, 47)])
        self.assertEqual(CAMISA_SACO_TALLES, ["2", "4", "6", "8", "10", "12", "14", "16", "XS", "S", "M", "L", "XL", "2XL", "3XL", "4XL", "5XL", "50", "52", "54", "56", "58", "60", "62", "64", "66", "68", "70", "72", "74", "76"])
        self.assertEqual(TAM_NINO_ADULTO, ["Niño", "Adulto"])

    def test_origen_automatico_no_se_pide_y_sobrescribe_el_post(self):
        casos = {
            Prenda.C_CAMISA: (Prenda.O_IMP, "M", "Negro"),
            Prenda.C_ZAPATOS: (Prenda.O_NAC, "40", "Negro"),
            Prenda.C_CINTURON: (Prenda.O_NAC, "Adulto", "Negro"),
            Prenda.C_CORBATA: (Prenda.O_NAC, "Adulto", "A rayas"),
            Prenda.C_CHALECO: (Prenda.O_NAC, "M", "Negro"),
        }
        for categoria, (origen, talle, color) in casos.items():
            form = PrendaForm(self.payload(
                categoria,
                color=color,
                talle=talle,
                origen=Prenda.O_NAC if origen == Prenda.O_IMP else Prenda.O_IMP,
            ))
            self.assertTrue(form.is_valid(), form.errors)
            self.assertEqual(form.cleaned_data["origen"], origen)

    def test_origen_sigue_siendo_obligatorio_para_saco(self):
        form = PrendaForm(self.payload(Prenda.C_SACO, talle="50", origen=""))
        self.assertFalse(form.is_valid())
        self.assertIn("origen", form.errors)

    def test_pantalon_rechaza_talle_impar_aunque_se_fuerce_post(self):
        form = PrendaForm(self.payload(Prenda.C_PANTALON, talle="75"))
        self.assertFalse(form.is_valid())
        self.assertIn("talle", form.errors)

    def test_saco_y_pantalon_admiten_talle_76(self):
        for categoria in (Prenda.C_SACO, Prenda.C_PANTALON):
            with self.subTest(categoria=categoria):
                form = PrendaForm(self.payload(categoria, talle="76"))
                self.assertTrue(form.is_valid(), form.errors)

    def test_empleado_puede_agregar_color_y_se_audita(self):
        user = User.objects.create_user("nano", password="ClaveSegura-2026!")
        PerfilUsuario.objects.create(user=user, nombre="Nano", rol=PerfilUsuario.EMPLEADO)
        self.client.force_login(user)
        response = self.client.post(reverse("prendas:stock"), {"accion": "agregar_color", "nombre": "Terracota"})
        self.assertRedirects(response, reverse("prendas:stock"))
        self.assertTrue(Color.objects.filter(nombre="Terracota").exists())
        self.assertTrue(Actividad.objects.filter(usuario=user, accion="Agregó color", referencia="Terracota").exists())
