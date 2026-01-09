from django.shortcuts import render
from .models import Traje, Alquiler, Gasto
from datetime import datetime, date
import re
from django.db.models import Count

def index(request):
    error = ''
    mensaje = ''
    url_wsp = ''
    prendas = Traje.objects.all()
    alquileres = Alquiler.objects.all().order_by('-fecha_visita')

    seccion = request.GET.get('seccion', 'crear_alquiler')
    prendas_no_disponibles = []
    alquileres_a_devolver = []
    atrasados = []
    gastos = Gasto.objects.all().order_by('-fecha')

    # Reportes básicos
    reporte_prendas = (
        Traje.objects
        .values('prenda')
        .annotate(cantidad_alquileres=Count('alquileres'))
        .order_by('-cantidad_alquileres')
    )

    reporte_colores = (
        Traje.objects
        .values('color')
        .annotate(cantidad_alquileres=Count('alquileres'))
        .order_by('-cantidad_alquileres')
    )

    reporte_talles = (
        Traje.objects
        .values('talle')
        .annotate(cantidad_alquileres=Count('alquileres'))
        .order_by('-cantidad_alquileres')
    )

    if request.method == 'POST':
        accion = request.POST.get('accion')

        if accion == 'crear_alquiler':
            nombre = request.POST.get('nombre')
            celular = request.POST.get('celular')
            prendas_codigos = request.POST.getlist('prendas')
            ruedo_pant = request.POST.get('ruedo_pantalon')
            ruedo_saco = request.POST.get('ruedo_saco')
            fecha_visita = request.POST.get('fecha_visita')
            fecha_retiro = request.POST.get('fecha_retiro')
            fecha_devolucion = request.POST.get('fecha_devolucion')
            fecha_evento = request.POST.get('fecha_evento')
            total = request.POST.get('total')
            sena = request.POST.get('sena')
            metodo_sena = request.POST.get('metodo_sena')
            saldo = request.POST.get('saldo')
            metodo_saldo = request.POST.get('metodo_saldo')
            notas = request.POST.get('notas')

            if not all([nombre, celular, prendas_codigos, fecha_visita, fecha_retiro,
                        fecha_devolucion, total, sena, metodo_sena, saldo, metodo_saldo]):
                error = "Por favor completa todos los campos obligatorios."
                seccion = 'crear_alquiler'
            else:
                try:
                    fechas_retiro = datetime.strptime(fecha_retiro, "%Y-%m-%d").date()
                    fechas_devolucion = datetime.strptime(fecha_devolucion, "%Y-%m-%d").date()

                    for codigo in prendas_codigos:
                        conflictos = Alquiler.objects.filter(
                            prendas__codigo=codigo,
                            fecha_retiro__lte=fechas_devolucion,
                            fecha_devolucion__gte=fechas_retiro
                        )
                        if conflictos.exists():
                            error = f"El traje {codigo} ya está alquilado para esas fechas."
                            seccion = 'crear_alquiler'
                            break

                    if not error:
                        alquiler = Alquiler.objects.create(
                            nombre_cliente=nombre,
                            celular_cliente=celular,
                            ruedo_pantalon=ruedo_pant or None,
                            ruedo_saco=ruedo_saco or None,
                            fecha_visita=fecha_visita,
                            fecha_retiro=fecha_retiro,
                            fecha_devolucion=fecha_devolucion,
                            fecha_evento=fecha_evento or None,
                            total_a_abonar=total,
                            seña=sena,
                            metodo_pago_sena=metodo_sena,
                            saldo_restante=saldo,
                            metodo_pago_saldo=metodo_saldo,
                            notas_adicionales=notas
                        )
                        for codigo in prendas_codigos:
                            traje = Traje.objects.get(codigo=codigo)
                            alquiler.prendas.add(traje)

                        detalle_prendas = [f"- {t.prenda} (Código: {t.codigo})" for t in alquiler.prendas.all()]
                        if alquiler.ruedo_pantalon:
                            detalle_prendas.append(f"Ruedo pantalón: {alquiler.ruedo_pantalon}")
                        if alquiler.ruedo_saco:
                            detalle_prendas.append(f"Ruedo saco: {alquiler.ruedo_saco}")

                        mensaje = (
                            "Te mando el detallado de tu reserva en Abit:\n"
                            + "\n".join(detalle_prendas)
                            + f"\n\nSeñá pagada: ${alquiler.seña} ({alquiler.metodo_pago_sena})"
                            + f"\nRestante: ${alquiler.saldo_restante} ({alquiler.metodo_pago_saldo})"
                            + f"\nFecha de retiro: {alquiler.fecha_retiro}"
                            + f"\nFecha de devolución: {alquiler.fecha_devolucion}"
                        )
                        mensaje_encoded = mensaje.replace(' ', '%20').replace('\n', '%0A')
                        url_wsp = f"https://api.whatsapp.com/send?phone={alquiler.celular_cliente}&text={mensaje_encoded}"
                        seccion = 'crear_alquiler'
                except Exception as e:
                    error = "Error inesperado: " + str(e)
                    seccion = 'crear_alquiler'

        elif accion == 'cargar_traje':
            codigo = request.POST.get('codigo', '').upper()
            prenda = request.POST.get('prenda')
            marca = request.POST.get('marca')
            talle = request.POST.get('talle')
            color = request.POST.get('color')
            estado = request.POST.get('estado', 'Disponible')

            if not all([codigo, prenda, marca, talle, color]):
                error = "Por favor completa todos los campos obligatorios para cargar un traje."
                seccion = 'cargar_traje'
            else:
                if not re.match(r'^[A-Z]{2}-\d{3}$', codigo):
                    error = "El código debe tener formato: dos letras, un guión, y tres números (ej: SA-001)."
                    seccion = 'cargar_traje'
                else:
                    if Traje.objects.filter(codigo=codigo).exists():
                        error = "Ya existe un traje con ese código."
                        seccion = 'cargar_traje'
                    else:
                        nuevo_traje = Traje(
                            codigo=codigo,
                            prenda=prenda,
                            marca=marca,
                            talle=talle,
                            color=color,
                            estado=estado
                        )
                        nuevo_traje.save()
                        mensaje = f"Traje {codigo} - {prenda} cargado con éxito."
                        seccion = 'cargar_traje'

        elif accion == 'ver_disponibilidad':
            fecha_inicio = request.POST.get('fecha_inicio')
            fecha_fin = request.POST.get('fecha_fin')
            seccion = 'ver_disponibilidad'
            if not fecha_inicio or not fecha_fin:
                error = "Por favor ingresa ambas fechas."
            else:
                try:
                    inicio = datetime.strptime(fecha_inicio, "%Y-%m-%d").date()
                    fin = datetime.strptime(fecha_fin, "%Y-%m-%d").date()
                    if fin < inicio:
                        error = "La fecha final debe ser mayor o igual que la inicial."
                    else:
                        alquileres_ocupados = Alquiler.objects.filter(
                            fecha_retiro__lte=fin,
                            fecha_devolucion__gte=inicio
                        ).distinct()
                        prendas_no_disponibles = Traje.objects.filter(
                            alquileres__in=alquileres_ocupados
                        ).distinct()
                except Exception as e:
                    error = f"Error al procesar las fechas: {str(e)}"

        elif accion == 'ver_devoluciones':
            fecha_consulta = request.POST.get('fecha_devolucion')
            seccion = 'ver_devoluciones'
            if not fecha_consulta:
                error = "Por favor ingresa la fecha a consultar."
            else:
                try:
                    fecha_obj = datetime.strptime(fecha_consulta, "%Y-%m-%d").date()
                    alquileres_a_devolver = Alquiler.objects.filter(fecha_devolucion=fecha_obj)
                    hoy = date.today()
                    atrasados = Alquiler.objects.filter(fecha_devolucion__lt=hoy)
                except Exception as e:
                    error = f"Error al procesar la fecha: {str(e)}"

        elif accion == 'cargar_gasto':
            fecha_gasto = request.POST.get('fecha_gasto')
            monto = request.POST.get('monto')
            detalle = request.POST.get('detalle')
            seccion = 'gastos'

            if not fecha_gasto or not monto:
                error = "Fecha y monto son obligatorios para cargar un gasto."
            else:
                try:
                    gasto = Gasto(fecha=fecha_gasto, monto=monto, detalle=detalle)
                    gasto.save()
                    mensaje = "Gasto agregado correctamente."
                except Exception as e:
                    error = f"Error al guardar gasto: {str(e)}"


    return render(request, 'alquileres/index.html', {
        'prendas': prendas,
        'alquileres': alquileres,
        'error': error,
        'mensaje': mensaje,
        'url_wsp': url_wsp,
        'seccion': seccion,
        'prendas_no_disponibles': prendas_no_disponibles if 'prendas_no_disponibles' in locals() else [],
        'alquileres_a_devolver': alquileres_a_devolver if 'alquileres_a_devolver' in locals() else [],
        'atrasados': atrasados if 'atrasados' in locals() else [],
        'gastos': gastos,
        'reporte_prendas': reporte_prendas,
        'reporte_colores': reporte_colores,
        'reporte_talles': reporte_talles,
    })