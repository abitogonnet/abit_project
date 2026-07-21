from datetime import date
from decimal import Decimal

from django.test import TestCase

from .models import Alquiler
from .views import _armar_mensaje_cliente_con_items


class PaymentLogicTests(TestCase):
    def alquiler(self, **overrides):
        values = {
            "cliente_nombre": "Cliente", "cliente_telefono": "123",
            "fecha_visita": date(2026, 7, 21), "fecha_reserva": date(2026, 7, 21),
            "fecha_entrega": date(2026, 7, 25), "fecha_devolucion": date(2026, 7, 28),
            "persona1_nombre": "Persona", "total_bruto": Decimal("200000"),
            "descuento_pct": Decimal("10"), "sena": Decimal("30000"),
            "metodo_sena": Alquiler.MP_EFEC,
        }
        values.update(overrides)
        return Alquiler.objects.create(**values)

    def test_total_final_y_saldo_se_calculan_en_un_solo_lugar(self):
        alquiler = self.alquiler()
        self.assertEqual(alquiler.total_final, Decimal("180000.00"))
        self.assertEqual(alquiler.saldo_pendiente_actual, Decimal("150000.00"))
        self.assertFalse(alquiler.esta_completamente_abonado)

    def test_pago_total_al_crear_deja_saldo_cero_y_pagado(self):
        alquiler = self.alquiler(sena=Decimal("180000"))
        self.assertEqual(alquiler.saldo, Decimal("0.00"))
        self.assertTrue(alquiler.esta_completamente_abonado)
        self.assertEqual(alquiler.saldo_pagado_en, date(2026, 7, 21))

    def test_entregado_siempre_queda_completamente_pagado(self):
        alquiler = self.alquiler(estado_alquiler=Alquiler.EST_ENTREGADO)
        self.assertEqual(alquiler.saldo, Decimal("0.00"))
        self.assertTrue(alquiler.esta_completamente_abonado)

    def test_entrega_no_reemplaza_fecha_de_pago_previa(self):
        alquiler = self.alquiler(estado_saldo=Alquiler.SAL_PAG, saldo_pagado_en=date(2026, 7, 23))
        alquiler.estado_alquiler = Alquiler.EST_ENTREGADO
        alquiler.save()
        self.assertEqual(alquiler.saldo_pagado_en, date(2026, 7, 23))
        self.assertEqual(alquiler.saldo, Decimal("0.00"))

    def test_mensaje_usa_el_mismo_saldo_y_no_muestra_resta_si_esta_pagado(self):
        alquiler = self.alquiler(estado_saldo=Alquiler.SAL_PAG, saldo_pagado_en=date(2026, 7, 23))
        mensaje = _armar_mensaje_cliente_con_items(alquiler, [])
        self.assertNotIn("Resta:", mensaje)
        self.assertEqual(alquiler.saldo_pendiente_actual, Decimal("0.00"))
