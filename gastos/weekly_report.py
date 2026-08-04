from io import BytesIO
from decimal import Decimal
from datetime import datetime, time, timedelta

import requests
from django.conf import settings
from django.db.models import Sum
from django.utils import timezone

from .models import MovimientoFinanciero


def periodo_semanal(ahora=None):
    ahora = timezone.localtime(ahora or timezone.now())
    lunes = ahora.date() - timedelta(days=ahora.weekday())
    desde = timezone.make_aware(
        datetime.combine(lunes, time.min),
        timezone.get_current_timezone(),
    )
    return desde, ahora


def datos_informe_semanal(desde, hasta):
    movimientos = list(
        MovimientoFinanciero.objects
        .filter(
            informativo=False,
            division__isnull=True,
            fecha_hora__gte=desde,
            fecha_hora__lte=hasta,
        )
        .order_by("fecha_hora", "id")
    )
    ingresos = [item for item in movimientos if item.ingreso > 0]
    egresos = [item for item in movimientos if item.egreso > 0]
    total_ingresos = sum((item.ingreso for item in ingresos), Decimal("0"))
    total_egresos = sum((item.egreso for item in egresos), Decimal("0"))
    acumulado = (
        MovimientoFinanciero.objects
        .filter(informativo=False)
        .aggregate(ingresos=Sum("ingreso"), egresos=Sum("egreso"))
    )
    saldo_actual = (
        (acumulado["ingresos"] or Decimal("0"))
        - (acumulado["egresos"] or Decimal("0"))
    )
    return {
        "desde": desde,
        "hasta": hasta,
        "ingresos": ingresos,
        "egresos": egresos,
        "total_ingresos": total_ingresos,
        "total_egresos": total_egresos,
        "resultado": total_ingresos - total_egresos,
        "saldo_actual": saldo_actual,
    }


def _moneda(valor, *, signo=False):
    valor = Decimal(valor or 0)
    prefijo = "+" if signo and valor >= 0 else ""
    entero = f"{abs(valor):,.0f}".replace(",", ".")
    negativo = "-" if valor < 0 else ""
    return f"{prefijo}{negativo}${entero}"


def nombre_archivo(datos):
    desde = timezone.localtime(datos["desde"]).date().isoformat()
    hasta = timezone.localtime(datos["hasta"]).date().isoformat()
    return f"Informe_Abito_{desde}_{hasta}.pdf"


def generar_pdf(datos):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    )

    output = BytesIO()
    doc = SimpleDocTemplate(
        output, pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm,
        topMargin=16 * mm, bottomMargin=16 * mm,
        title="Informe financiero semanal de Abito",
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="AbitoTitle", parent=styles["Title"], fontName="Helvetica-Bold",
        fontSize=20, leading=23, textColor=colors.HexColor("#20231f"),
        alignment=TA_CENTER, spaceAfter=5 * mm,
    ))
    styles.add(ParagraphStyle(
        name="Section", parent=styles["Heading2"], fontName="Helvetica-Bold",
        fontSize=12, textColor=colors.HexColor("#556b2f"), spaceBefore=6 * mm,
        spaceAfter=3 * mm,
    ))
    styles.add(ParagraphStyle(
        name="Right", parent=styles["BodyText"], alignment=TA_RIGHT,
    ))
    desde = timezone.localtime(datos["desde"])
    hasta = timezone.localtime(datos["hasta"])
    periodo = f"{desde:%d/%m/%Y} – {hasta:%d/%m/%Y %H:%M}"
    story = [
        Paragraph("ABITO", styles["AbitoTitle"]),
        Paragraph("INFORME FINANCIERO SEMANAL", styles["Heading1"]),
        Paragraph(f"<b>Período:</b> {periodo}", styles["BodyText"]),
        Paragraph("RESUMEN", styles["Section"]),
    ]
    resumen = [
        ["Ingresos de la semana", _moneda(datos["total_ingresos"])],
        ["Egresos de la semana", _moneda(-datos["total_egresos"])],
        ["Resultado neto", _moneda(datos["resultado"], signo=True)],
        ["SALDO ACTUAL", _moneda(datos["saldo_actual"])],
    ]
    tabla = Table(resumen, colWidths=[105 * mm, 48 * mm])
    tabla.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f2f1e8")),
        ("TEXTCOLOR", (0, 3), (-1, 3), colors.HexColor("#33451f")),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTNAME", (0, 2), (-1, -1), "Helvetica-Bold"),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#c9c9bd")),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#deded5")),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.append(tabla)

    for titulo, items, campo, total in (
        ("INGRESOS", datos["ingresos"], "ingreso", datos["total_ingresos"]),
        ("EGRESOS", datos["egresos"], "egreso", datos["total_egresos"]),
    ):
        story.append(Paragraph(titulo, styles["Section"]))
        if not items:
            story.append(Paragraph("Sin movimientos en el período.", styles["BodyText"]))
        else:
            filas = [["Fecha", "Concepto", "Referencia", "Importe"]]
            for item in items:
                importe = getattr(item, campo)
                if campo == "egreso":
                    importe = -importe
                filas.append([
                    timezone.localtime(item.fecha_hora).strftime("%d/%m %H:%M"),
                    item.concepto,
                    item.referencia or "—",
                    _moneda(importe, signo=campo == "ingreso"),
                ])
            detalle = Table(filas, colWidths=[28 * mm, 50 * mm, 48 * mm, 27 * mm], repeatRows=1)
            detalle.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#556b2f")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ALIGN", (-1, 1), (-1, -1), "RIGHT"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d6d6cc")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]))
            story.append(detalle)
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph(
            f"<b>Total {titulo.lower()}:</b> {_moneda(total)}",
            styles["Right"],
        ))

    story.extend([
        Spacer(1, 6 * mm),
        KeepTogether([
            Paragraph(f"<b>RESULTADO SEMANAL:</b> {_moneda(datos['resultado'], signo=True)}", styles["Heading2"]),
            Paragraph(f"<b>SALDO ACTUAL:</b> {_moneda(datos['saldo_actual'])}", styles["Heading2"]),
            Spacer(1, 5 * mm),
            Paragraph(
                f"Generado por Abito · {timezone.localtime():%d/%m/%Y %H:%M}",
                styles["BodyText"],
            ),
        ]),
    ])
    doc.build(story)
    return output.getvalue()


def whatsapp_configurado():
    return bool(settings.WHATSAPP_ACCESS_TOKEN and settings.WHATSAPP_PHONE_NUMBER_ID)


def enviar_documento_whatsapp(pdf, archivo, destinatario, caption):
    base = (
        f"https://graph.facebook.com/{settings.WHATSAPP_GRAPH_API_VERSION}/"
        f"{settings.WHATSAPP_PHONE_NUMBER_ID}"
    )
    headers = {"Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}"}
    try:
        upload = requests.post(
            f"{base}/media",
            headers=headers,
            data={"messaging_product": "whatsapp"},
            files={"file": (archivo, pdf, "application/pdf")},
            timeout=45,
        )
        upload.raise_for_status()
        media_id = upload.json()["id"]
        sent = requests.post(
            f"{base}/messages",
            headers={**headers, "Content-Type": "application/json"},
            json={
                "messaging_product": "whatsapp",
                "to": "".join(filter(str.isdigit, destinatario)),
                "type": "document",
                "document": {"id": media_id, "filename": archivo, "caption": caption},
            },
            timeout=45,
        )
        sent.raise_for_status()
        payload = sent.json()
        message_id = (payload.get("messages") or [{}])[0].get("id", "")
        return {"estado": "enviado", "message_id": message_id, "media_id": media_id}
    except (requests.RequestException, KeyError, ValueError) as exc:
        detalle = str(exc)
        if getattr(exc, "response", None) is not None:
            try:
                detalle = exc.response.json().get("error", {}).get("message", detalle)
            except ValueError:
                pass
        return {"estado": "fallido", "error": detalle[:300]}
