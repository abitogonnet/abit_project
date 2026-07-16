from django.contrib import messages
from django.shortcuts import redirect, render


FINANZAS_PASSWORD = "Abito"
FINANZAS_SESSION_KEY = "gastos_access_ok"


def require_finanzas_access(request, *, title="Finanzas protegidas"):
    if request.session.get(FINANZAS_SESSION_KEY):
        return None

    next_path = (request.POST.get("next_path") or request.get_full_path() or request.path or "").strip()
    if not next_path.startswith("/"):
        next_path = request.path

    error_msg = ""
    if request.method == "POST" and request.POST.get("access_action") == "unlock":
        password = (request.POST.get("access_password") or "").strip()
        if password == FINANZAS_PASSWORD:
            request.session[FINANZAS_SESSION_KEY] = True
            messages.success(request, "Acceso a finanzas habilitado.")
            return redirect(next_path or request.path)
        error_msg = "Contrasena incorrecta."

    return render(request, "gastos/lock.html", {
        "error_msg": error_msg,
        "lock_title": title,
        "next_path": next_path or request.path,
    })
