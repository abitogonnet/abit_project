from urllib.parse import quote


def normalizar_telefono(value):
    digits = "".join(char for char in (value or "") if char.isdigit())
    if digits.startswith("549") and 12 <= len(digits) <= 13:
        return digits
    if digits.startswith("54") and 11 <= len(digits) <= 12:
        return "549" + digits[2:]
    digits = digits.lstrip("0")
    if 9 <= len(digits) <= 11:
        return "549" + digits
    return ""


def generar_enlace_whatsapp(telefono, mensaje):
    numero = normalizar_telefono(telefono)
    if not numero or not (mensaje or "").strip():
        return ""
    return f"https://wa.me/{numero}?text={quote(mensaje)}"


def mensaje_recordatorio(alquiler):
    return f"Hola, {alquiler.cliente_nombre}. Te hablo de Abito para recordarte que hoy podés pasar a retirar las cosas que reservaste."
