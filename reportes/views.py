import csv
from collections import defaultdict
from datetime import date, timedelta
import unicodedata
from decimal import Decimal

from django.db.models import Max, Q
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from alquileres.models import Alquiler, AlquilerItem
from alquileres.services import regularizar_saldos_de_cerrados
from gastos.access import require_finanzas_access
from gastos.models import Gasto
from prendas.models import Prenda
from visitas.models import Visita


MESES_ES = [
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
]

COLOR_FILL_MAP = {
    "beige": "#cdb79e",
    "negro": "#1f1f24",
    "azul oscuro": "#1d3d63",
    "azul francia": "#2b66d9",
    "gris perla": "#c9c9cf",
    "gris oscuro": "#595b63",
    "gris": "#8c9097",
    "celeste": "#84c5f4",
    "verde oscuro": "#295f4e",
    "pistacho": "#98b65f",
    "rosa": "#d97f98",
    "violeta": "#7f5ea7",
    "bordo": "#6d213c",
    "marron": "#7a5536",
    "blanco": "#e8e6df",
    "sin color": "#b9b2a8",
}


def _first_day_next_month(day: date) -> date:
    if day.month == 12:
        return date(day.year + 1, 1, 1)
    return date(day.year, day.month + 1, 1)


def _weeks_in_month(year: int, month: int) -> int:
    start = date(year, month, 1)
    end = _first_day_next_month(start) - timedelta(days=1)
    return ((end.day - 1) // 7) + 1


def _month_label(day: date) -> str:
    return f"{MESES_ES[day.month - 1].capitalize()} {day.year}"


def _latest_reporting_month_start():
    candidates = [
        Alquiler.objects.aggregate(value=Max("fecha_entrega"))["value"],
        Alquiler.objects.aggregate(value=Max("fecha_reserva"))["value"],
        (
            Alquiler.objects
            .filter(estado_saldo=Alquiler.SAL_PAG, saldo_pagado_en__isnull=False)
            .aggregate(value=Max("saldo_pagado_en"))["value"]
        ),
    ]
    candidates = [item for item in candidates if item]
    if not candidates:
        return None

    latest = max(candidates)
    return date(latest.year, latest.month, 1)


def _normalize_color_key(value: str) -> str:
    text = unicodedata.normalize("NFD", (value or "").strip().casefold())
    return "".join(char for char in text if unicodedata.category(char) != "Mn")


def _fill_color_for_label(label: str):
    key = _normalize_color_key(label)
    return COLOR_FILL_MAP.get(key)


def _resolve_period(request):
    today = timezone.localdate()

    period = (request.GET.get("periodo") or "mensual").strip().lower()
    if period not in {"mensual", "semanal"}:
        period = "mensual"

    ym = (request.GET.get("ym") or "").strip()
    if ym and len(ym) == 7 and ym[4] == "-":
        try:
            year = int(ym[:4])
            month = int(ym[5:7])
            start = date(year, month, 1)
        except Exception:
            start = date(today.year, today.month, 1)
    else:
        start = _latest_reporting_month_start() or date(today.year, today.month, 1)

    end = _first_day_next_month(start)
    weeks_n = _weeks_in_month(start.year, start.month)
    return period, start, end, weeks_n


def _visitas_conversion(start, end, *, ahora=None):
    ahora = ahora or timezone.localtime()
    hoy = ahora.date()
    hora_actual = ahora.time()
    base = Visita.objects.filter(
        fecha_visita__gte=start,
        fecha_visita__lt=end,
    )
    canceladas = base.filter(estado=Visita.ESTADO_CANCELADA).count()
    consideradas = base.exclude(
        estado=Visita.ESTADO_CANCELADA
    ).filter(
        Q(fecha_visita__lt=hoy)
        | Q(fecha_visita=hoy, hora_visita__lte=hora_actual)
    )
    alquilaron = consideradas.filter(alquiler__isnull=False).count()
    no_alquilaron = consideradas.filter(alquiler__isnull=True).count()
    total = alquilaron + no_alquilaron
    conversion = round((alquilaron * 100) / total, 1) if total else 0
    return {
        "total": total,
        "alquilaron": alquilaron,
        "no_alquilaron": no_alquilaron,
        "conversion": conversion,
        "conversion_css": f"{conversion:.1f}",
        "canceladas": canceladas,
    }


def _top_k_from_monthly(data, limit=8):
    items = sorted(data.items(), key=lambda item: (-item[1], item[0]))
    return items[:limit]


def _top_k_from_weekly(data, limit=8):
    totals = []
    for key, by_week in data.items():
        totals.append((key, sum(by_week.values())))
    totals.sort(key=lambda item: (-item[1], item[0]))
    return [key for key, _value in totals[:limit]]


def _bar_items_from_pairs(items, tone, *, color_mode=False):
    max_value = max((value for _label, value in items), default=0) or 1
    bars = []
    for label, value in items:
        bars.append({
            "label": label,
            "value": value,
            "pct": round((value * 100) / max_value, 2),
            "tone": tone,
            "fill_color": _fill_color_for_label(label) if color_mode else None,
        })
    return bars


def _decorate_week_rows(rows, tone, *, color_mode=False):
    max_total = max((row["total"] for row in rows), default=0) or 1
    max_week = max((max(row["weeks"]) for row in rows), default=0) or 1

    decorated = []
    for row in rows:
        decorated.append({
            "label": row["key"],
            "total": row["total"],
            "total_pct": round((row["total"] * 100) / max_total, 2),
            "weeks": [
                {"value": value, "pct": round((value * 100) / max_week, 2)}
                for value in row["weeks"]
            ],
            "tone": tone,
            "fill_color": _fill_color_for_label(row["key"]) if color_mode else None,
        })
    return decorated


def _income_rows(data, metodos, order):
    rows = []
    for method in order:
        rows.append({
            "code": method,
            "label": metodos.get(method, "Sin metodo"),
            "sena": round(data["sena"].get(method, 0.0), 2),
            "saldo": round(data["saldo"].get(method, 0.0), 2),
            "total": round(data["total"].get(method, 0.0), 2),
        })

    total_sena = round(sum(data["sena"].values()), 2)
    total_saldo = round(sum(data["saldo"].values()), 2)
    total_general = round(sum(data["total"].values()), 2)
    max_total = max((row["total"] for row in rows), default=0) or 1

    for row in rows:
        row["pct_total"] = round((row["total"] * 100) / max_total, 2)
        row["pct_sena"] = round((row["sena"] * 100) / max_total, 2)
        row["pct_saldo"] = round((row["saldo"] * 100) / max_total, 2)

    return rows, total_sena, total_saldo, total_general


def home(request):
    access_response = require_finanzas_access(request)
    if access_response:
        return access_response

    regularizar_saldos_de_cerrados()
    period, start, end, weeks_n = _resolve_period(request)
    visitas_conversion = _visitas_conversion(start, end)

    item_rows = (
        AlquilerItem.objects
        .select_related("alquiler", "prenda")
        .filter(alquiler__fecha_entrega__gte=start, alquiler__fecha_entrega__lt=end)
        .values_list(
            "alquiler__fecha_entrega",
            "prenda__categoria",
            "prenda__color",
            "prenda__talle",
            "prenda__marca",
        )
    )

    monthly_color = defaultdict(lambda: defaultdict(int))
    monthly_talle = defaultdict(lambda: defaultdict(int))
    monthly_marca = defaultdict(lambda: defaultdict(int))
    monthly_gastos = defaultdict(float)

    weekly_color = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    weekly_talle = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    weekly_marca = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    weekly_gastos = defaultdict(lambda: defaultdict(float))

    total_items = 0
    for entrega, categoria, color, talle, marca in item_rows:
        total_items += 1
        color = (color or "").strip() or "Sin color"
        talle = (talle or "").strip() or "Sin talle"
        marca = (marca or "").strip() or "Sin marca"

        if period == "mensual":
            monthly_color[categoria][color] += 1
            monthly_talle[categoria][talle] += 1
            monthly_marca[categoria][marca] += 1
        else:
            week = ((entrega.day - 1) // 7) + 1
            weekly_color[categoria][color][week] += 1
            weekly_talle[categoria][talle][week] += 1
            weekly_marca[categoria][marca][week] += 1

    gastos_rows = (
        Gasto.objects
        .filter(fecha__gte=start, fecha__lt=end)
        .values_list("fecha", "categoria", "monto")
    )
    for gasto_fecha, categoria, monto in gastos_rows:
        categoria = (categoria or "").strip() or "Sin categoria"
        amount = float(monto or 0)
        if period == "mensual":
            monthly_gastos[categoria] += amount
        else:
            week = ((gasto_fecha.day - 1) // 7) + 1
            weekly_gastos[categoria][week] += amount

    report = []
    total_gastos_report = 0.0

    if period == "mensual":
        total_gastos_report = round(sum(monthly_gastos.values()), 2)
        report.append({
            "label": "Gastos",
            "mode": "mensual",
            "is_money": True,
            "cards": [
                {"title": "Por categoria", "items": _bar_items_from_pairs(_top_k_from_monthly(monthly_gastos), "secondary")},
            ],
        })
    else:
        gastos_keys = _top_k_from_weekly(weekly_gastos)
        gastos_rows = []
        for key in gastos_keys:
            row = {"key": key, "weeks": [], "total": 0}
            for week in range(1, weeks_n + 1):
                value = round(float(weekly_gastos[key].get(week, 0)), 2)
                row["weeks"].append(value)
                row["total"] += value
            gastos_rows.append(row)

        total_gastos_report = round(sum(row["total"] for row in gastos_rows), 2)
        report.append({
            "label": "Gastos",
            "mode": "semanal",
            "is_money": True,
            "weeks_labels": list(range(1, weeks_n + 1)),
            "cards": [
                {"title": "Por categoria", "rows": _decorate_week_rows(gastos_rows, "secondary")},
            ],
        })

    for categoria, label in Prenda.CATEGORIAS:
        if period == "mensual":
            colors = _bar_items_from_pairs(_top_k_from_monthly(monthly_color.get(categoria, {})), "accent", color_mode=True)
            talles = _bar_items_from_pairs(_top_k_from_monthly(monthly_talle.get(categoria, {})), "secondary")
            marcas = _bar_items_from_pairs(_top_k_from_monthly(monthly_marca.get(categoria, {})), "warn")
            report.append({
                "label": label,
                "mode": "mensual",
                "is_money": False,
                "cards": [
                    {"title": "Por color", "items": colors},
                    {"title": "Por talle", "items": talles},
                    {"title": "Por marca", "items": marcas},
                ],
            })
        else:
            color_keys = _top_k_from_weekly(weekly_color.get(categoria, {}))
            talle_keys = _top_k_from_weekly(weekly_talle.get(categoria, {}))
            marca_keys = _top_k_from_weekly(weekly_marca.get(categoria, {}))

            color_rows = []
            for key in color_keys:
                row = {"key": key, "weeks": [], "total": 0}
                for week in range(1, weeks_n + 1):
                    value = int(weekly_color[categoria][key].get(week, 0))
                    row["weeks"].append(value)
                    row["total"] += value
                color_rows.append(row)

            talle_rows = []
            for key in talle_keys:
                row = {"key": key, "weeks": [], "total": 0}
                for week in range(1, weeks_n + 1):
                    value = int(weekly_talle[categoria][key].get(week, 0))
                    row["weeks"].append(value)
                    row["total"] += value
                talle_rows.append(row)

            marca_rows = []
            for key in marca_keys:
                row = {"key": key, "weeks": [], "total": 0}
                for week in range(1, weeks_n + 1):
                    value = int(weekly_marca[categoria][key].get(week, 0))
                    row["weeks"].append(value)
                    row["total"] += value
                marca_rows.append(row)

            report.append({
                "label": label,
                "mode": "semanal",
                "is_money": False,
                "weeks_labels": list(range(1, weeks_n + 1)),
                "cards": [
                    {"title": "Por color", "rows": _decorate_week_rows(color_rows, "accent", color_mode=True)},
                    {"title": "Por talle", "rows": _decorate_week_rows(talle_rows, "secondary")},
                    {"title": "Por marca", "rows": _decorate_week_rows(marca_rows, "warn")},
                ],
            })

    methods = dict(Alquiler.METODOS_PAGO)
    method_order = list(methods.keys()) + ["SIN"]

    ingresos_mensual = {
        "sena": defaultdict(float),
        "saldo": defaultdict(float),
        "total": defaultdict(float),
    }
    ingresos_semanal = defaultdict(lambda: {
        "sena": defaultdict(float),
        "saldo": defaultdict(float),
        "total": defaultdict(float),
    })

    senas = (
        Alquiler.objects
        .filter(fecha_reserva__gte=start, fecha_reserva__lt=end)
        .values_list("fecha_reserva", "sena", "metodo_sena")
    )
    for paid_date, amount, method in senas:
        amount = float(amount or 0)
        method = (method or "").strip() or "SIN"
        if period == "mensual":
            ingresos_mensual["sena"][method] += amount
            ingresos_mensual["total"][method] += amount
        else:
            week = ((paid_date.day - 1) // 7) + 1
            ingresos_semanal[week]["sena"][method] += amount
            ingresos_semanal[week]["total"][method] += amount

    saldos = (
        Alquiler.objects
        .filter(estado_saldo=Alquiler.SAL_PAG, saldo_pagado_en__isnull=False)
        .filter(saldo_pagado_en__gte=start, saldo_pagado_en__lt=end)
        .values_list("saldo_pagado_en", "total_final", "sena", "saldo_a_favor_aplicado", "metodo_saldo")
    )
    for paid_date, total_final, sena, credito, method in saldos:
        amount = max(Decimal("0"), total_final - sena - credito)
        amount = float(amount or 0)
        method = (method or "").strip() or "SIN"
        if period == "mensual":
            ingresos_mensual["saldo"][method] += amount
            ingresos_mensual["total"][method] += amount
        else:
            week = ((paid_date.day - 1) // 7) + 1
            ingresos_semanal[week]["saldo"][method] += amount
            ingresos_semanal[week]["total"][method] += amount

    if period == "mensual":
        rows, total_sena, total_saldo, total_general = _income_rows(ingresos_mensual, methods, method_order)
        ingresos_ctx = {
            "tipo": "mensual",
            "rows": rows,
            "total_sena": total_sena,
            "total_saldo": total_saldo,
            "total_general": total_general,
        }
    else:
        weeks = []
        totals_by_week = []
        for week in range(1, weeks_n + 1):
            rows, total_sena, total_saldo, total_general = _income_rows(ingresos_semanal[week], methods, method_order)
            weeks.append({
                "wk": week,
                "rows": rows,
                "total_sena": total_sena,
                "total_saldo": total_saldo,
                "total_general": total_general,
            })
            totals_by_week.append(total_general)

        max_week_total = max(totals_by_week, default=0) or 1
        for block in weeks:
            block["pct_total"] = round((block["total_general"] * 100) / max_week_total, 2)

        ingresos_ctx = {
            "tipo": "semanal",
            "weeks": weeks,
        }
        total_general = round(sum(totals_by_week), 2)

    summary = [
        {"label": "Mes analizado", "value": _month_label(start)},
        {"label": "Prendas alquiladas", "value": total_items},
        {"label": "Semanas del mes", "value": weeks_n},
        {"label": "Ingresos cobrados en el mes", "value": total_general, "money": True},
        {"label": "Gastos del mes", "value": total_gastos_report, "money": True},
    ]

    return render(request, "reportes/home.html", {
        "periodo": period,
        "ym_value": f"{start.year:04d}-{start.month:02d}",
        "month_label": _month_label(start),
        "start": start,
        "weeks_n": weeks_n,
        "total_items": total_items,
        "ingresos": ingresos_ctx,
        "report": report,
        "summary": summary,
        "visitas_conversion": visitas_conversion,
    })


def exportar_excel(request):
    access_response = require_finanzas_access(request)
    if access_response:
        return access_response

    regularizar_saldos_de_cerrados()
    period, start, end, weeks_n = _resolve_period(request)
    ym_value = f"{start.year:04d}-{start.month:02d}"

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="reportes_{ym_value}_{period}.csv"'

    writer = csv.writer(response)
    writer.writerow(["SECCION", "CATEGORIA", "ATRIBUTO", "VALOR", "SEMANA", "CANTIDAD", "MONTO"])

    methods = dict(Alquiler.METODOS_PAGO)
    method_order = list(methods.keys()) + ["SIN"]

    ingresos_mensual = {
        "sena": defaultdict(float),
        "saldo": defaultdict(float),
        "total": defaultdict(float),
    }
    ingresos_semanal = defaultdict(lambda: {
        "sena": defaultdict(float),
        "saldo": defaultdict(float),
        "total": defaultdict(float),
    })

    senas = (
        Alquiler.objects
        .filter(fecha_reserva__gte=start, fecha_reserva__lt=end)
        .values_list("fecha_reserva", "sena", "metodo_sena")
    )
    for paid_date, amount, method in senas:
        amount = float(amount or 0)
        method = (method or "").strip() or "SIN"
        if period == "mensual":
            ingresos_mensual["sena"][method] += amount
            ingresos_mensual["total"][method] += amount
        else:
            week = ((paid_date.day - 1) // 7) + 1
            ingresos_semanal[week]["sena"][method] += amount
            ingresos_semanal[week]["total"][method] += amount

    saldos = (
        Alquiler.objects
        .filter(estado_saldo=Alquiler.SAL_PAG, saldo_pagado_en__isnull=False)
        .filter(saldo_pagado_en__gte=start, saldo_pagado_en__lt=end)
        .values_list("saldo_pagado_en", "total_final", "sena", "saldo_a_favor_aplicado", "metodo_saldo")
    )
    for paid_date, total_final, sena, credito, method in saldos:
        amount = max(Decimal("0"), total_final - sena - credito)
        amount = float(amount or 0)
        method = (method or "").strip() or "SIN"
        if period == "mensual":
            ingresos_mensual["saldo"][method] += amount
            ingresos_mensual["total"][method] += amount
        else:
            week = ((paid_date.day - 1) // 7) + 1
            ingresos_semanal[week]["saldo"][method] += amount
            ingresos_semanal[week]["total"][method] += amount

    if period == "mensual":
        for method in method_order:
            writer.writerow([
                "INGRESOS",
                "",
                "Metodo",
                methods.get(method, "Sin metodo"),
                "",
                "",
                round(ingresos_mensual["total"].get(method, 0.0), 2),
            ])
        writer.writerow(["INGRESOS", "", "TOTAL_GENERAL", "", "", "", round(sum(ingresos_mensual["total"].values()), 2)])
    else:
        for week in range(1, weeks_n + 1):
            for method in method_order:
                writer.writerow([
                    "INGRESOS",
                    "",
                    "Metodo",
                    methods.get(method, "Sin metodo"),
                    week,
                    "",
                    round(ingresos_semanal[week]["total"].get(method, 0.0), 2),
                ])
            writer.writerow(["INGRESOS", "", "TOTAL_SEMANA", "", week, "", round(sum(ingresos_semanal[week]["total"].values()), 2)])

    gastos_rows = (
        Gasto.objects
        .filter(fecha__gte=start, fecha__lt=end)
        .values_list("fecha", "categoria", "monto")
    )
    for gasto_fecha, categoria, monto in gastos_rows:
        week = ((gasto_fecha.day - 1) // 7) + 1 if period == "semanal" else ""
        writer.writerow([
            "GASTOS",
            categoria or "Sin categoria",
            "Categoria",
            categoria or "Sin categoria",
            week,
            "",
            round(float(monto or 0), 2),
        ])

    items = (
        AlquilerItem.objects
        .select_related("alquiler", "prenda")
        .filter(alquiler__fecha_entrega__gte=start, alquiler__fecha_entrega__lt=end)
    )
    for item in items:
        prenda = item.prenda
        entrega = item.alquiler.fecha_entrega
        week = ((entrega.day - 1) // 7) + 1 if period == "semanal" else ""
        writer.writerow(["PRENDAS", prenda.get_categoria_display(), "Color", prenda.color or "Sin color", week, 1, ""])
        writer.writerow(["PRENDAS", prenda.get_categoria_display(), "Talle", prenda.talle or "Sin talle", week, 1, ""])
        writer.writerow(["PRENDAS", prenda.get_categoria_display(), "Marca", prenda.marca or "Sin marca", week, 1, ""])

    return response
