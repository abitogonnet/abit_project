import csv
from collections import defaultdict
from datetime import date, timedelta

from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from alquileres.models import Alquiler, AlquilerItem
from prendas.models import Prenda


def _first_day_next_month(day: date) -> date:
    if day.month == 12:
        return date(day.year + 1, 1, 1)
    return date(day.year, day.month + 1, 1)


def _weeks_in_month(year: int, month: int) -> int:
    start = date(year, month, 1)
    end = _first_day_next_month(start) - timedelta(days=1)
    return ((end.day - 1) // 7) + 1


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
        start = date(today.year, today.month, 1)

    end = _first_day_next_month(start)
    weeks_n = _weeks_in_month(start.year, start.month)
    return period, start, end, weeks_n


def _top_k_from_monthly(data, limit=8):
    items = sorted(data.items(), key=lambda item: (-item[1], item[0]))
    return items[:limit]


def _top_k_from_weekly(data, limit=8):
    totals = []
    for key, by_week in data.items():
        totals.append((key, sum(by_week.values())))
    totals.sort(key=lambda item: (-item[1], item[0]))
    return [key for key, _value in totals[:limit]]


def _bar_items_from_pairs(items, tone):
    max_value = max((value for _label, value in items), default=0) or 1
    bars = []
    for label, value in items:
        bars.append({
            "label": label,
            "value": value,
            "pct": round((value * 100) / max_value, 2),
            "tone": tone,
        })
    return bars


def _decorate_week_rows(rows, tone):
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
    period, start, end, weeks_n = _resolve_period(request)

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

    weekly_color = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    weekly_talle = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    weekly_marca = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))

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

    report = []
    for categoria, label in Prenda.CATEGORIAS:
        if period == "mensual":
            colors = _bar_items_from_pairs(_top_k_from_monthly(monthly_color.get(categoria, {})), "accent")
            talles = _bar_items_from_pairs(_top_k_from_monthly(monthly_talle.get(categoria, {})), "secondary")
            marcas = _bar_items_from_pairs(_top_k_from_monthly(monthly_marca.get(categoria, {})), "warn")
            report.append({
                "label": label,
                "mode": "mensual",
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
                "weeks_labels": list(range(1, weeks_n + 1)),
                "cards": [
                    {"title": "Por color", "rows": _decorate_week_rows(color_rows, "accent")},
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
        .values_list("saldo_pagado_en", "saldo", "metodo_saldo")
    )
    for paid_date, amount, method in saldos:
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
        {"label": "Periodo", "value": start.strftime("%m/%Y")},
        {"label": "Prendas movidas", "value": total_items},
        {"label": "Semanas del mes", "value": weeks_n},
        {"label": "Ingresos del periodo", "value": f"${total_general:.2f}"},
    ]

    return render(request, "reportes/home.html", {
        "periodo": period,
        "ym_value": f"{start.year:04d}-{start.month:02d}",
        "start": start,
        "weeks_n": weeks_n,
        "total_items": total_items,
        "ingresos": ingresos_ctx,
        "report": report,
        "summary": summary,
    })


def exportar_excel(request):
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
        .values_list("saldo_pagado_en", "saldo", "metodo_saldo")
    )
    for paid_date, amount, method in saldos:
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
