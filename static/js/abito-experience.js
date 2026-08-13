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

  document.addEventListener("pointerdown", function (event) {
    const button = event.target.closest(".ab-btn, .ab-btn2, .ab-state-btn, .ab-global-btn");
    if (!button || reduced) return;
    const rect = button.getBoundingClientRect();
    const size = Math.max(rect.width, rect.height);
    const ripple = document.createElement("span");
    ripple.className = "xp-ripple";
    ripple.style.width = ripple.style.height = size + "px";
    ripple.style.left = (event.clientX - rect.left - size / 2) + "px";
    ripple.style.top = (event.clientY - rect.top - size / 2) + "px";
    button.appendChild(ripple);
    ripple.addEventListener("animationend", function () { ripple.remove(); });
  });
})();
