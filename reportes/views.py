from datetime import date, timedelta
from collections import defaultdict
import csv

from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from alquileres.models import Alquiler, AlquilerItem
from prendas.models import Prenda


def _first_day_next_month(d: date) -> date:
    if d.month == 12:
        return date(d.year + 1, 1, 1)
    return date(d.year, d.month + 1, 1)


def _weeks_in_month(year: int, month: int) -> int:
    start = date(year, month, 1)
    end = _first_day_next_month(start) - timedelta(days=1)
    return ((end.day - 1) // 7) + 1  # 1..5 aprox


def home(request):
    hoy = timezone.localdate()

    periodo = (request.GET.get("periodo") or "mensual").strip().lower()
    if periodo not in ("mensual", "semanal"):
        periodo = "mensual"

    ym = (request.GET.get("ym") or "").strip()  # "YYYY-MM"
    if ym and len(ym) == 7 and ym[4] == "-":
        try:
            year = int(ym[:4])
            month = int(ym[5:7])
            base = date(year, month, 1)
        except Exception:
            base = date(hoy.year, hoy.month, 1)
    else:
        base = date(hoy.year, hoy.month, 1)

    start = base
    end = _first_day_next_month(base)

    # =========================
    # A) REPORTE DE USO DE PRENDAS (color, talle, marca) por fecha_entrega
    # =========================
    qs = (AlquilerItem.objects
          .select_related("alquiler", "prenda")
          .filter(alquiler__fecha_entrega__gte=start, alquiler__fecha_entrega__lt=end))

    rows = qs.values_list(
        "alquiler__fecha_entrega",
        "prenda__categoria",
        "prenda__color",
        "prenda__talle",
        "prenda__marca",
    )

    cat_labels = dict(Prenda.CATEGORIAS)
    cats_order = [c for c, _ in Prenda.CATEGORIAS]

    # mensual: cat -> key -> count
    monthly_color = defaultdict(lambda: defaultdict(int))
    monthly_talle = defaultdict(lambda: defaultdict(int))
    monthly_marca = defaultdict(lambda: defaultdict(int))

    # semanal: cat -> key -> week -> count
    weekly_color = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    weekly_talle = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    weekly_marca = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))

    total_items = 0
    for f_entrega, cat, color, talle, marca in rows:
        total_items += 1

        color = (color or "").strip() or "Sin color"
        talle = (talle or "").strip() or "Sin talle"
        marca = (marca or "").strip() or "Sin marca"

        if periodo == "mensual":
            monthly_color[cat][color] += 1
            monthly_talle[cat][talle] += 1
            monthly_marca[cat][marca] += 1
        else:
            wk = ((f_entrega.day - 1) // 7) + 1
            weekly_color[cat][color][wk] += 1
            weekly_talle[cat][talle][wk] += 1
            weekly_marca[cat][marca][wk] += 1

    weeks_n = _weeks_in_month(start.year, start.month)

    def _top_k_from_monthly(d: dict, k: int = 12):
        items = sorted(d.items(), key=lambda x: (-x[1], x[0]))
        return items[:k]

    def _top_k_from_weekly(d: dict, k: int = 12):
        totals = []
        for key, byw in d.items():
            s = sum(byw.values())
            totals.append((key, s))
        totals.sort(key=lambda x: (-x[1], x[0]))
        return [k1 for k1, _ in totals[:k]]

    report = []
    for cat in cats_order:
        label = cat_labels.get(cat, cat)

        if periodo == "mensual":
            colors = _top_k_from_monthly(monthly_color.get(cat, {}), k=12)
            talles = _top_k_from_monthly(monthly_talle.get(cat, {}), k=12)
            marcas = _top_k_from_monthly(monthly_marca.get(cat, {}), k=12)
            report.append({
                "cat": cat,
                "label": label,
                "colors_month": colors,
                "talles_month": talles,
                "marcas_month": marcas,
            })
        else:
            colors_keys = _top_k_from_weekly(weekly_color.get(cat, {}), k=12)
            talles_keys = _top_k_from_weekly(weekly_talle.get(cat, {}), k=12)
            marcas_keys = _top_k_from_weekly(weekly_marca.get(cat, {}), k=12)

            colors_rows = []
            for key in colors_keys:
                byw = weekly_color[cat][key]
                row = {"key": key, "weeks": [], "total": 0}
                for w in range(1, weeks_n + 1):
                    c = int(byw.get(w, 0))
                    row["weeks"].append(c)
                    row["total"] += c
                colors_rows.append(row)

            talles_rows = []
            for key in talles_keys:
                byw = weekly_talle[cat][key]
                row = {"key": key, "weeks": [], "total": 0}
                for w in range(1, weeks_n + 1):
                    c = int(byw.get(w, 0))
                    row["weeks"].append(c)
                    row["total"] += c
                talles_rows.append(row)

            marcas_rows = []
            for key in marcas_keys:
                byw = weekly_marca[cat][key]
                row = {"key": key, "weeks": [], "total": 0}
                for w in range(1, weeks_n + 1):
                    c = int(byw.get(w, 0))
                    row["weeks"].append(c)
                    row["total"] += c
                marcas_rows.append(row)

            report.append({
                "cat": cat,
                "label": label,
                "weeks_n": weeks_n,
                "colors_week": colors_rows,
                "talles_week": talles_rows,
                "marcas_week": marcas_rows,
            })

    # =========================
    # B) INGRESOS (SEÑA + SALDO) por método
    # =========================
    metodos = dict(Alquiler.METODOS_PAGO)

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

    # Señas por fecha_reserva
    qs_senas = (Alquiler.objects
                .filter(fecha_reserva__gte=start, fecha_reserva__lt=end)
                .values_list("fecha_reserva", "sena", "metodo_sena"))

    for f, monto, mp in qs_senas:
        monto = float(monto or 0)
        mp = (mp or "").strip() or "SIN"
        if periodo == "mensual":
            ingresos_mensual["sena"][mp] += monto
            ingresos_mensual["total"][mp] += monto
        else:
            wk = ((f.day - 1) // 7) + 1
            ingresos_semanal[wk]["sena"][mp] += monto
            ingresos_semanal[wk]["total"][mp] += monto

    # Saldos pagados por saldo_pagado_en
    qs_saldos = (Alquiler.objects
                 .filter(estado_saldo=Alquiler.SAL_PAG, saldo_pagado_en__isnull=False)
                 .filter(saldo_pagado_en__gte=start, saldo_pagado_en__lt=end)
                 .values_list("saldo_pagado_en", "saldo", "metodo_saldo"))

    for f, monto, mp in qs_saldos:
        monto = float(monto or 0)
        mp = (mp or "").strip() or "SIN"
        if periodo == "mensual":
            ingresos_mensual["saldo"][mp] += monto
            ingresos_mensual["total"][mp] += monto
        else:
            wk = ((f.day - 1) // 7) + 1
            ingresos_semanal[wk]["saldo"][mp] += monto
            ingresos_semanal[wk]["total"][mp] += monto

    orden_metodos = list(metodos.keys()) + ["SIN"]

    def _fila_ingresos(dic):
        rows_i = []
        for mp in orden_metodos:
            rows_i.append({
                "mp": mp,
                "label": metodos.get(mp, "Sin método"),
                "sena": round(dic["sena"].get(mp, 0.0), 2),
                "saldo": round(dic["saldo"].get(mp, 0.0), 2),
                "total": round(dic["total"].get(mp, 0.0), 2),
            })
        tg_sena = sum(dic["sena"].values())
        tg_saldo = sum(dic["saldo"].values())
        tg_total = sum(dic["total"].values())
        return rows_i, round(tg_sena, 2), round(tg_saldo, 2), round(tg_total, 2)

    if periodo == "mensual":
        rows_i, tg_sena, tg_saldo, tg_total = _fila_ingresos(ingresos_mensual)
        ingresos_ctx = {
            "tipo": "mensual",
            "rows": rows_i,
            "tg_sena": tg_sena,
            "tg_saldo": tg_saldo,
            "tg_total": tg_total,
        }
    else:
        weeks_list = []
        for wk in range(1, weeks_n + 1):
            dic = ingresos_semanal[wk]
            rows_i, tg_sena, tg_saldo, tg_total = _fila_ingresos(dic)
            weeks_list.append({
                "wk": wk,
                "rows": rows_i,
                "tg_sena": tg_sena,
                "tg_saldo": tg_saldo,
                "tg_total": tg_total,
            })
        ingresos_ctx = {
            "tipo": "semanal",
            "weeks": weeks_list,
        }

    ctx = {
        "periodo": periodo,
        "ym_value": f"{start.year:04d}-{start.month:02d}",
        "start": start,
        "total_items": total_items,
        "report": report,
        "weeks_n": weeks_n,
        "ingresos": ingresos_ctx,
    }
    return render(request, "reportes/home.html", ctx)


def exportar_excel(request):
    """
    Exporta CSV (abre en Excel / Google Sheets).
    Exporta:
      - ingresos (señas/saldos/total) por método
      - uso de prendas por cat + color/talle/marca (mensual o semanal)
    Respeta filtros: ?periodo=mensual|semanal&ym=YYYY-MM
    """
    hoy = timezone.localdate()

    periodo = (request.GET.get("periodo") or "mensual").strip().lower()
    if periodo not in ("mensual", "semanal"):
        periodo = "mensual"

    ym = (request.GET.get("ym") or "").strip()
    if ym and len(ym) == 7 and ym[4] == "-":
        try:
            year = int(ym[:4])
            month = int(ym[5:7])
            base = date(year, month, 1)
        except Exception:
            base = date(hoy.year, hoy.month, 1)
    else:
        base = date(hoy.year, hoy.month, 1)

    start = base
    end = _first_day_next_month(base)
    weeks_n = _weeks_in_month(start.year, start.month)

    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="reportes_{ym or start.strftime("%Y-%m")}_{periodo}.csv"'

    writer = csv.writer(resp)
    writer.writerow(["SECCION", "CATEGORIA", "ATRIBUTO", "VALOR", "SEMANA", "CANTIDAD", "MONTO"])

    # =========================
    # INGRESOS
    # =========================
    metodos = dict(Alquiler.METODOS_PAGO)
    orden_metodos = list(metodos.keys()) + ["SIN"]

    ingresos_m = {
        "sena": defaultdict(float),
        "saldo": defaultdict(float),
        "total": defaultdict(float),
    }
    ingresos_w = defaultdict(lambda: {
        "sena": defaultdict(float),
        "saldo": defaultdict(float),
        "total": defaultdict(float),
    })

    qs_senas = (Alquiler.objects
                .filter(fecha_reserva__gte=start, fecha_reserva__lt=end)
                .values_list("fecha_reserva", "sena", "metodo_sena"))

    for f, monto, mp in qs_senas:
        monto = float(monto or 0)
        mp = (mp or "").strip() or "SIN"
        if periodo == "mensual":
            ingresos_m["sena"][mp] += monto
            ingresos_m["total"][mp] += monto
        else:
            wk = ((f.day - 1) // 7) + 1
            ingresos_w[wk]["sena"][mp] += monto
            ingresos_w[wk]["total"][mp] += monto

    qs_saldos = (Alquiler.objects
                 .filter(estado_saldo=Alquiler.SAL_PAG, saldo_pagado_en__isnull=False)
                 .filter(saldo_pagado_en__gte=start, saldo_pagado_en__lt=end)
                 .values_list("saldo_pagado_en", "saldo", "metodo_saldo"))

    for f, monto, mp in qs_saldos:
        monto = float(monto or 0)
        mp = (mp or "").strip() or "SIN"
        if periodo == "mensual":
            ingresos_m["saldo"][mp] += monto
            ingresos_m["total"][mp] += monto
        else:
            wk = ((f.day - 1) // 7) + 1
            ingresos_w[wk]["saldo"][mp] += monto
            ingresos_w[wk]["total"][mp] += monto

    if periodo == "mensual":
        for mp in orden_metodos:
            writer.writerow([
                "INGRESOS",
                "",
                "Metodo",
                metodos.get(mp, "Sin método"),
                "",
                "",
                round(ingresos_m["total"].get(mp, 0.0), 2)
            ])
        writer.writerow(["INGRESOS", "", "TOTAL_GENERAL", "", "", "", round(sum(ingresos_m["total"].values()), 2)])
    else:
        for wk in range(1, weeks_n + 1):
            for mp in orden_metodos:
                writer.writerow([
                    "INGRESOS",
                    "",
                    "Metodo",
                    metodos.get(mp, "Sin método"),
                    wk,
                    "",
                    round(ingresos_w[wk]["total"].get(mp, 0.0), 2)
                ])
            writer.writerow(["INGRESOS", "", "TOTAL_SEMANA", "", wk, "", round(sum(ingresos_w[wk]["total"].values()), 2)])

    # =========================
    # USO DE PRENDAS
    # =========================
    qs = (AlquilerItem.objects
          .select_related("alquiler", "prenda")
          .filter(alquiler__fecha_entrega__gte=start, alquiler__fecha_entrega__lt=end))

    for it in qs:
        p = it.prenda
        f = it.alquiler.fecha_entrega
        wk = ((f.day - 1) // 7) + 1 if periodo == "semanal" else ""

        cat_label = p.get_categoria_display()
        color = (p.color or "").strip() or "Sin color"
        talle = (p.talle or "").strip() or "Sin talle"
        marca = (p.marca or "").strip() or "Sin marca"

        writer.writerow(["TRAJES", cat_label, "Color", color, wk, 1, ""])
        writer.writerow(["TRAJES", cat_label, "Talle", talle, wk, 1, ""])
        writer.writerow(["TRAJES", cat_label, "Marca", marca, wk, 1, ""])

    return resp
