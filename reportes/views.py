from datetime import date, timedelta
from collections import defaultdict, OrderedDict

from django.shortcuts import render
from django.utils import timezone

from alquileres.models import AlquilerItem
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
    """
    Reportes de uso de prendas (por fecha_entrega):
      - Mensual o Semanal
      - Mes elegible por input type="month"
      - Separado por categoría
      - Dentro de cada categoría: por Color y por Talle
    """
    hoy = timezone.localdate()

    # GET params
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

    # Traigo filas mínimas y calculo todo en Python
    qs = (AlquilerItem.objects
          .select_related("alquiler", "prenda")
          .filter(alquiler__fecha_entrega__gte=start, alquiler__fecha_entrega__lt=end))

    rows = qs.values_list(
        "alquiler__fecha_entrega",
        "prenda__categoria",
        "prenda__color",
        "prenda__talle",
    )

    cat_labels = dict(Prenda.CATEGORIAS)
    cats_order = [c for c, _ in Prenda.CATEGORIAS]  # orden fijo

    # Estructuras:
    # mensual:  cat -> key -> count
    monthly_color = defaultdict(lambda: defaultdict(int))
    monthly_talle = defaultdict(lambda: defaultdict(int))

    # semanal:  cat -> key -> week -> count
    weekly_color = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    weekly_talle = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))

    total_items = 0
    for f_entrega, cat, color, talle in rows:
        total_items += 1
        color = (color or "").strip() or "Sin color"
        talle = (talle or "").strip() or "Sin talle"

        if periodo == "mensual":
            monthly_color[cat][color] += 1
            monthly_talle[cat][talle] += 1
        else:
            wk = ((f_entrega.day - 1) // 7) + 1
            weekly_color[cat][color][wk] += 1
            weekly_talle[cat][talle][wk] += 1

    weeks_n = _weeks_in_month(start.year, start.month)

    def _top_k_from_monthly(d: dict, k: int = 12):
        # devuelve lista [(key,count)] ordenada desc
        items = sorted(d.items(), key=lambda x: (-x[1], x[0]))
        return items[:k]

    def _top_k_from_weekly(d: dict, k: int = 12):
        # d: key -> week->count
        totals = []
        for key, byw in d.items():
            s = sum(byw.values())
            totals.append((key, s))
        totals.sort(key=lambda x: (-x[1], x[0]))
        top_keys = [k1 for k1, _ in totals[:k]]
        return top_keys

    # Armo context “listo para template” por categoría (para mantener orden)
    report = []
    for cat in cats_order:
        label = cat_labels.get(cat, cat)

        if periodo == "mensual":
            colors = _top_k_from_monthly(monthly_color.get(cat, {}), k=12)
            talles = _top_k_from_monthly(monthly_talle.get(cat, {}), k=12)
            report.append({
                "cat": cat,
                "label": label,
                "colors_month": colors,   # [(color,count)]
                "talles_month": talles,   # [(talle,count)]
            })
        else:
            colors_keys = _top_k_from_weekly(weekly_color.get(cat, {}), k=12)
            talles_keys = _top_k_from_weekly(weekly_talle.get(cat, {}), k=12)

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

            report.append({
                "cat": cat,
                "label": label,
                "weeks_n": weeks_n,
                "colors_week": colors_rows,  # [{key,weeks[],total}]
                "talles_week": talles_rows,
            })

    ctx = {
        "periodo": periodo,
        "ym_value": f"{start.year:04d}-{start.month:02d}",
        "start": start,
        "total_items": total_items,
        "report": report,
        "weeks_n": weeks_n,
    }
    return render(request, "reportes/home.html", ctx)
