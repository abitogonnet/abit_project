(function () {
  const optionsNode = document.getElementById("ab-available-prendas");
  const pageOptionsByCategory = optionsNode ? JSON.parse(optionsNode.textContent) : {};
  const panelCache = new Map();

  function abNum(value) {
    const text = (value || "").toString().replace(",", ".").trim();
    const parsed = parseFloat(text);
    return Number.isNaN(parsed) ? 0 : parsed;
  }

  function abOnlyDigits(value) {
    return (value || "").toString().replace(/\D/g, "");
  }

  function abNormalizedDigits(value) {
    const digits = abOnlyDigits(value);
    if (!digits) return "";
    return digits.replace(/^0+/, "") || "0";
  }

  function abMatchesCodeNumber(code, prefix, typed) {
    if (!typed) return true;
    const rawCode = (code || "").toUpperCase();
    const fullPrefix = `${(prefix || "").toUpperCase()}-`;
    const suffix = rawCode.startsWith(fullPrefix) ? rawCode.slice(fullPrefix.length) : rawCode;
    const codeDigits = abOnlyDigits(suffix);
    const cleanTyped = abOnlyDigits(typed);
    const normalizedTyped = abNormalizedDigits(cleanTyped);
    const normalizedCode = abNormalizedDigits(codeDigits);
    return codeDigits.startsWith(cleanTyped) || normalizedCode.startsWith(normalizedTyped);
  }

  function abCloneOption(optionData) {
    const option = document.createElement("option");
    option.value = optionData.value;
    option.textContent = optionData.label;
    return option;
  }

  function abReadOptions(select) {
    return Array.from(select.options).map(function (option) {
      return { value: option.value, label: option.textContent };
    });
  }

  function abAllOptions(select) {
    if (select._allOptions) {
      return select._allOptions;
    }

    const merged = [];
    const seen = new Set();
    const categoryKey = select.dataset.categoryKey || "";
    const pageOptions = pageOptionsByCategory[categoryKey] || [];

    function pushOption(optionData) {
      const value = optionData.value || "";
      if (seen.has(value)) return;
      seen.add(value);
      merged.push(optionData);
    }

    abReadOptions(select).forEach(pushOption);
    pageOptions.forEach(pushOption);

    select._allOptions = merged;
    return merged;
  }

  function abRebuildSelect(select, options, selectedValue) {
    select.innerHTML = "";
    options.forEach(function (optionData) {
      select.appendChild(abCloneOption(optionData));
    });

    const exists = options.some(function (optionData) {
      return optionData.value === selectedValue;
    });
    select.value = exists ? selectedValue : "";
  }

  function abExpandSelect(select) {
    const allOptions = abAllOptions(select);
    const currentValue = select.value;
    abRebuildSelect(select, allOptions, currentValue);
    select.dataset.expanded = "1";
    select.dataset.filtered = "";
  }

  function abFilterCodeSelect(input) {
    const selectId = input.dataset.targetSelect;
    const select = document.getElementById(selectId);
    if (!select) return;

    const prefix = input.dataset.prefix || "";
    const typed = abOnlyDigits(input.value);
    if (input.value !== typed) {
      input.value = typed;
    }

    const allOptions = abAllOptions(select);
    const previousValue = select.value;

    if (!typed) {
      if (select.dataset.filtered === "1" || select.dataset.expanded === "1") {
        abRebuildSelect(select, allOptions, previousValue);
      }
      select.dataset.filtered = "";
      return;
    }

    const matchingOptions = allOptions.filter(function (option) {
      return !option.value || abMatchesCodeNumber(option.value, prefix, typed);
    });

    abRebuildSelect(select, matchingOptions, previousValue);
    select.dataset.filtered = "1";
  }

  function recalcEditForm(form) {
    const totalInput = form.querySelector('[name$="-total_bruto"]');
    const discountInput = form.querySelector('[name$="-descuento_pct"]');
    const senaInput = form.querySelector('[name$="-sena"]');
    const totalFinalOutput = form.querySelector(".js-edit-total-final");
    const saldoOutput = form.querySelector(".js-edit-saldo");
    if (!totalInput || !discountInput || !senaInput || !totalFinalOutput || !saldoOutput) return;

    const total = abNum(totalInput.value);
    const descuento = Math.min(Math.max(abNum(discountInput.value), 0), 100);
    const sena = Math.max(abNum(senaInput.value), 0);
    const totalFinal = Math.max(total - (total * descuento / 100), 0);
    const saldo = Math.max(totalFinal - sena, 0);

    totalFinalOutput.value = totalFinal.toFixed(2);
    saldoOutput.value = saldo.toFixed(2);
  }

  async function loadRemotePanel(host) {
    if (!host || host.dataset.loaded === "1") return;

    const panelUrl = host.dataset.panelUrl || "";
    if (!panelUrl) return;

    host.dataset.loaded = "1";
    host.innerHTML = '<div class="ab-small">Cargando...</div>';

    if (!panelCache.has(panelUrl)) {
      panelCache.set(
        panelUrl,
        fetch(panelUrl, {
          headers: { "X-Requested-With": "XMLHttpRequest" },
        }).then(function (response) {
          if (!response.ok) {
            throw new Error("No se pudo cargar el panel.");
          }
          return response.text();
        }),
      );
    }

    try {
      const html = await panelCache.get(panelUrl);
      host.innerHTML = html;
      initEditForm(host.querySelector(".js-alq-edit-form"));
    } catch (_error) {
      host.dataset.loaded = "";
      host.innerHTML = '<div class="ab-msg err">No se pudo cargar este bloque. Intenta de nuevo.</div>';
    }
  }

  function loadRemotePanels(root) {
    if (!root) return;
    root.querySelectorAll(".js-remote-panel").forEach(function (host) {
      void loadRemotePanel(host);
    });
  }

  function initEditForm(form) {
    if (!form || form.dataset.editInit === "1") return;
    form.dataset.editInit = "1";

    form.querySelectorAll(".js-code-filter").forEach(function (input) {
      input.addEventListener("input", function () {
        abFilterCodeSelect(input);
      });
    });

    form.querySelectorAll(".js-code-select").forEach(function (select) {
      select.addEventListener("focus", function () {
        abExpandSelect(select);
      });
      select.addEventListener("pointerdown", function () {
        abExpandSelect(select);
      });
    });

    ["[name$='-total_bruto']", "[name$='-descuento_pct']", "[name$='-sena']"].forEach(function (selector) {
      const input = form.querySelector(selector);
      if (input) {
        input.addEventListener("input", function () {
          recalcEditForm(form);
        });
      }
    });

    recalcEditForm(form);
  }

  document.querySelectorAll("details").forEach(function (details) {
    details.addEventListener("toggle", function () {
      if (!details.open) return;
      loadRemotePanels(details);
      initEditForm(details.querySelector(".js-alq-edit-form"));
    });
  });

  document.querySelectorAll("details[open]").forEach(function (details) {
    loadRemotePanels(details);
    initEditForm(details.querySelector(".js-alq-edit-form"));
  });
})();
