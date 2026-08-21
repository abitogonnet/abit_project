(function () {
  "use strict";
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const body = document.body;

  const progress = document.createElement("div");
  progress.className = "xp-page-progress";
  progress.setAttribute("aria-hidden", "true");
  body.appendChild(progress);

  const scrollRoot = document.querySelector(".ab-main") || document.documentElement;
  function updateScroll() {
    const total = Math.max(scrollRoot.scrollHeight - scrollRoot.clientHeight, 1);
    progress.style.setProperty("--xp-progress", ((scrollRoot.scrollTop / total) * 100) + "%");
    const nav = document.querySelector(".ab-global-actions");
    if (nav) nav.classList.toggle("is-scrolled", scrollRoot.scrollTop > 24);
  }
  scrollRoot.addEventListener("scroll", updateScroll, { passive: true });
  updateScroll();

  if (!reduced) {
    let frame = 0;
    document.addEventListener("pointermove", function (event) {
      if (frame) return;
      frame = requestAnimationFrame(function () {
        body.style.setProperty("--xp-x", ((event.clientX / innerWidth) * 100).toFixed(1) + "%");
        body.style.setProperty("--xp-y", ((event.clientY / innerHeight) * 100).toFixed(1) + "%");
        const card = event.target.closest(".ab-home-menu-btn, .ab-summary-card");
        if (card) {
          const rect = card.getBoundingClientRect();
          card.style.setProperty("--card-x", (event.clientX - rect.left) + "px");
          card.style.setProperty("--card-y", (event.clientY - rect.top) + "px");
        }
        frame = 0;
      });
    }, { passive: true });
  }

  const revealNodes = document.querySelectorAll(".ab-pagehero, .ab-section-card, .ab-card, .ab-rental-card, .ab-entity-card");
  revealNodes.forEach(function (node, index) {
    node.dataset.xpReveal = "";
    node.style.setProperty("--xp-delay", Math.min(index % 6, 5) * 65 + "ms");
  });
  if (reduced || !("IntersectionObserver" in window)) {
    revealNodes.forEach(function (node) { node.classList.add("is-visible"); });
  } else {
    const observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("is-visible");
        observer.unobserve(entry.target);
      });
    }, { threshold: .06, rootMargin: "0px 0px -20px" });
    revealNodes.forEach(function (node) { observer.observe(node); });
  }

  const clickTargetSelector = ".ab-btn, .ab-btn2, .ab-state-btn, .ab-global-btn, .ab-home-menu-btn, .ab-mobile-nav-panel a, .ab-mobile-nav-panel button";
  document.addEventListener("pointerdown", function (event) {
    const button = event.target.closest(clickTargetSelector);
    if (!button || reduced) return;
    button.classList.remove("xp-clicked");
    void button.offsetWidth;
    button.classList.add("xp-clicked");
    const rect = button.getBoundingClientRect();
    const size = Math.max(rect.width, rect.height);
    const ripple = document.createElement("span");
    ripple.className = "xp-ripple";
    ripple.style.width = ripple.style.height = size + "px";
    ripple.style.left = (event.clientX - rect.left - size / 2) + "px";
    ripple.style.top = (event.clientY - rect.top - size / 2) + "px";
    button.appendChild(ripple);
    ripple.addEventListener("animationend", function () { ripple.remove(); });
    window.setTimeout(function () { button.classList.remove("xp-clicked"); }, 720);
  });

  document.querySelectorAll("[data-client-search]").forEach(function (root) {
    const input = root.querySelector("input");
    const results = root.querySelector(".ab-client-search-results");
    let timer;
    input.addEventListener("input", function () {
      clearTimeout(timer);
      const query = input.value.trim();
      if (query.length < 2) { results.hidden = true; results.innerHTML = ""; return; }
      timer = setTimeout(async function () {
        const response = await fetch("/alquileres/api/clientes/buscar/?q=" + encodeURIComponent(query));
        const data = await response.json();
        results.innerHTML = (data.resultados || []).map(function (cliente) {
          return '<article><a href="' + cliente.url + '"><strong>' + cliente.nombre + '</strong><small>DNI ' + cliente.dni + ' · ' + cliente.telefono + '</small></a><div><a href="' + cliente.crear_url + '">Crear alquiler</a>' + (cliente.whatsapp_url ? '<a href="' + cliente.whatsapp_url + '" target="_blank" rel="noopener">WhatsApp</a>' : '') + '</div></article>';
        }).join("") || '<p>No encontramos clientes.</p>';
        results.hidden = false;
      }, 220);
    });
    document.addEventListener("pointerdown", function (event) { if (!root.contains(event.target)) results.hidden = true; });
  });

  const dangerousValues = new Set(["cerrar_alquiler", "cancelar_alquiler", "eliminar"]);
  document.querySelectorAll('button[onclick*="confirm"], input[onclick*="confirm"]').forEach(function (control) {
    control.removeAttribute("onclick");
  });
  const dialog = document.createElement("dialog");
  dialog.className = "xp-confirm-dialog";
  dialog.innerHTML = '<form method="dialog"><p class="ab-kicker">Confirmación</p><h2>¿Querés continuar?</h2><p data-confirm-copy>Esta acción modifica información importante.</p><div class="ab-actions"><button class="ab-btn2" value="cancel">Volver</button><button class="ab-btn" value="confirm">Confirmar</button></div></form>';
  body.appendChild(dialog);
  document.querySelectorAll('a[href*="cancelar"]').forEach(function (link) {
    link.removeAttribute("onclick");
    link.addEventListener("click", function (event) {
      if (link.dataset.xpConfirmed === "1") return;
      event.preventDefault();
      dialog.querySelector("[data-confirm-copy]").textContent = "Vas a cancelar esta visita.";
      dialog.showModal();
      dialog.addEventListener("close", function onClose() {
        dialog.removeEventListener("close", onClose);
        if (dialog.returnValue !== "confirm") return;
        link.dataset.xpConfirmed = "1";
        link.click();
      });
    });
  });
  document.addEventListener("submit", function (event) {
    const submitter = event.submitter;
    const mustConfirm = submitter && (dangerousValues.has(submitter.value) || /desbloquear/i.test(submitter.textContent));
    if (!mustConfirm || event.target.dataset.xpConfirmed === "1") return;
    event.preventDefault();
    event.stopImmediatePropagation();
    dialog.querySelector("[data-confirm-copy]").textContent = "Vas a " + submitter.textContent.trim().toLowerCase() + ".";
    dialog.showModal();
    dialog.addEventListener("close", function onClose() {
      dialog.removeEventListener("close", onClose);
      if (dialog.returnValue !== "confirm") return;
      event.target.dataset.xpConfirmed = "1";
      event.target.requestSubmit(submitter);
    });
  }, true);

})();
