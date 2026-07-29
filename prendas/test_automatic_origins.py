from importlib import import_module

from django.apps import apps
from django.test import TestCase

from .models import Prenda


class AutomaticOriginMigrationTests(TestCase):
    def test_normalizacion_es_persistente_completa_e_idempotente(self):
        casos = [
            ("CA-991", Prenda.C_CAMISA, Prenda.O_NAC, Prenda.O_IMP),
            ("ZA-991", Prenda.C_ZAPATOS, "", Prenda.O_NAC),
            ("CI-991", Prenda.C_CINTURON, Prenda.O_IMP, Prenda.O_NAC),
            ("CO-991", Prenda.C_CORBATA, "", Prenda.O_NAC),
        ]
        Prenda.objects.bulk_create([
            Prenda(codigo=codigo, categoria=categoria, origen=origen_incorrecto)
            for codigo, categoria, origen_incorrecto, _esperado in casos
        ])
        normalizar = import_module(
            "prendas.migrations.0008_normalize_automatic_origins"
        ).normalizar_origenes

        normalizar(apps, None)
        normalizar(apps, None)

        for codigo, _categoria, _incorrecto, esperado in casos:
            self.assertEqual(
                Prenda.objects.get(codigo=codigo).origen,
                esperado,
            )
        self.assertFalse(
            Prenda.incompletas().filter(
                categoria__in=Prenda.ORIGEN_AUTOMATICO_POR_CATEGORIA,
            ).exists()
        )
