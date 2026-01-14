(function () {
  "use strict";

  // -------------------------
  // Utils
  // -------------------------
  function qs(sel, root) {
    return (root || document).querySelector(sel);
  }
  function qsa(sel, root) {
    return Array.from((root || document).querySelectorAll(sel));
  }
  function formatMoney(v) {
    return "$" + Number(v || 0).toFixed(2);
  }

  // Evita UTC (toISOString) para no “cambiar de día” por zona horaria
  function todayLocalISO() {
    const d = new Date();
    const yyyy = d.getFullYear();
    const mm = String(d.getMonth() + 1).padStart(2, "0");
    const dd = String(d.getDate()).padStart(2, "0");
    return `${yyyy}-${mm}-${dd}`;
  }

  function addDaysISO(iso, days) {
    const [y, m, d] = iso.split("-").map((x) => parseInt(x, 10));
    const dt = new Date(y, m - 1, d);
    dt.setDate(dt.getDate() + days);
    const yyyy = dt.getFullYear();
    const mm = String(dt.getMonth() + 1).padStart(2, "0");
    const dd = String(dt.getDate()).padStart(2, "0");
    return `${yyyy}-${mm}-${dd}`;
  }

  function validateDates(checkin, checkout) {
    if (!checkin || !checkout) return "Selecciona entrada y salida.";
    if (checkout <= checkin) return "La salida debe ser posterior a la entrada.";
    if (checkin < todayLocalISO()) return "No se permiten fechas en el pasado.";
    return null;
  }

  function debounce(fn, ms) {
    let t;
    return function (...args) {
      clearTimeout(t);
      t = setTimeout(() => fn.apply(this, args), ms);
    };
  }

  // -------------------------
  // HTTP
  // -------------------------
  async function refreshAvailability(checkin, checkout) {
    const url =
      `/motels/availability_http?checkin=${encodeURIComponent(checkin)}` +
      `&checkout=${encodeURIComponent(checkout)}`;

    const r = await fetch(url, {
      method: "GET",
      headers: { Accept: "application/json" },
      credentials: "same-origin",
    });

    let data;
    try {
      data = await r.json();
    } catch (e) {
      throw new Error("Respuesta inválida del servidor (no JSON).");
    }

    if (!r.ok) throw new Error((data && data.error) || "Error consultando disponibilidad.");
    return data.motels || [];
  }

  // -------------------------
  // Reserve link helpers
  // -------------------------
  function setReserveLink(btn, motelId, roomType, checkin, checkout) {
    const url =
      `/motels/reserve?motel_id=${encodeURIComponent(String(motelId))}` +
      `&room_type=${encodeURIComponent(roomType)}` +
      `&checkin=${encodeURIComponent(checkin)}` +
      `&checkout=${encodeURIComponent(checkout)}`;
    btn.setAttribute("href", url);
  }

  function enableLink(btn) {
    btn.classList.remove("disabled");
    btn.removeAttribute("aria-disabled");
  }

  function disableLink(btn) {
    btn.classList.add("disabled");
    btn.setAttribute("aria-disabled", "true");
    btn.setAttribute("href", "#");
  }

  // -------------------------
  // Selection helpers
  // -------------------------
  function getSelectedType(card) {
    return card.getAttribute("data-selected-room-type") || null;
  }

  function setSelectedType(card, type) {
    card.setAttribute("data-selected-room-type", type);
  }

  function markSelected(card, type) {
    const normal = qs('[data-room-choice="normal"]', card);
    const premium = qs('[data-room-choice="premium"]', card);

    if (normal) {
      normal.classList.remove("border-primary", "bg-light");
    }
    if (premium) {
      premium.classList.remove("border-primary", "bg-light");
    }

    const el = type === "premium" ? premium : normal;
    if (el) el.classList.add("border-primary", "bg-light");

    const hintNormal = qs("[data-hint-normal]", card);
    const hintPremium = qs("[data-hint-premium]", card);
    if (hintNormal) hintNormal.textContent = type === "normal" ? "✓ Seleccionado" : "";
    if (hintPremium) hintPremium.textContent = type === "premium" ? "✓ Seleccionado" : "";
  }

  function defaultSelectionForCard(card, m) {
    const existing = getSelectedType(card);
    if (existing === "normal" || existing === "premium") return existing;
    if (m.normal && m.normal.available > 0) return "normal";
    if (m.premium && m.premium.available > 0) return "premium";
    return "normal";
  }

  function updateReserveButton(card, motelId, m, checkinValue, checkoutValue) {
    const btn = qs("[data-action-reserve]", card);
    if (!btn) return;

    const selected = getSelectedType(card) || "normal";
    const availNormal = (m.normal && m.normal.available) || 0;
    const availPremium = (m.premium && m.premium.available) || 0;

    const nights = m.nights || 0;

    // Precios HU-04 vienen del backend:
    // normal: { price_per_day, final_total, surcharge }
    const selectedBucket = selected === "premium" ? m.premium : m.normal;
    const canReserve = selected === "premium" ? availPremium > 0 : availNormal > 0;

    // Texto del botón con total calculado
    const typeLabel = selected === "premium" ? "Premium" : "Normal";
    const total = selectedBucket ? selectedBucket.final_total : 0;
    btn.textContent = `Reservar (${typeLabel}) - ${formatMoney(total)}`;

    if (canReserve) {
      setReserveLink(btn, motelId, selected, checkinValue, checkoutValue);
      enableLink(btn);
    } else {
      disableLink(btn);
    }

    // Marcar selección
    markSelected(card, selected);

    // Si quieres reflejar noches en el UI (si tienes data-nights en template)
    qsa("[data-nights]", card).forEach((el) => (el.textContent = String(nights)));
  }

  // -------------------------
  // Render
  // -------------------------
  function renderMotels(motels, checkinValue, checkoutValue) {
    qsa("#motels_grid .card").forEach((card) => {
      const motelInput = qs("input[data-motel-id]", card);
      if (!motelInput) return;

      const motelId = Number(motelInput.value);
      const m = motels.find((x) => x.id === motelId);
      if (!m) return;

      // Pintar precios/disp (según el payload nuevo del backend)
      const priceNormal = qs("[data-price-normal]", card);
      const pricePremium = qs("[data-price-premium]", card);
      const availNormal = qs("[data-available-normal]", card);
      const availPremium = qs("[data-available-premium]", card);

      if (priceNormal) priceNormal.textContent = formatMoney(m.normal && m.normal.price_per_day);
      if (pricePremium) pricePremium.textContent = formatMoney(m.premium && m.premium.price_per_day);
      if (availNormal) availNormal.textContent = String((m.normal && m.normal.available) || 0);
      if (availPremium) availPremium.textContent = String((m.premium && m.premium.available) || 0);

      // Totales (si los agregaste al template con data-total-*)
      const totalNormal = qs("[data-total-normal]", card);
      const totalPremium = qs("[data-total-premium]", card);
      if (totalNormal) totalNormal.textContent = formatMoney(m.normal && m.normal.final_total);
      if (totalPremium) totalPremium.textContent = formatMoney(m.premium && m.premium.final_total);

      // Recargo (si agregaste data-surcharge-*)
      const surN = qs("[data-surcharge-normal]", card);
      const surP = qs("[data-surcharge-premium]", card);
      if (surN) surN.classList.toggle("d-none", !(m.normal && m.normal.surcharge));
      if (surP) surP.classList.toggle("d-none", !(m.premium && m.premium.surcharge));

      // Noches (si agregaste data-nights)
      qsa("[data-nights]", card).forEach((el) => (el.textContent = String(m.nights || 0)));

      // Status
      const status = qs("[data-status]", card);
      if (status) {
        if (!m.has_availability) {
          status.textContent = "Sin disponibilidad";
          status.className = "badge bg-danger";
        } else {
          const parts = [];
          if (m.normal && m.normal.available > 0) parts.push("Normal");
          if (m.premium && m.premium.available > 0) parts.push("Premium");
          status.textContent = "Disponible: " + (parts.length ? parts.join(" / ") : "—");
          status.className = "badge bg-success";
        }
      }

      // Si no hay disponibilidad, deshabilita Reservar y listo
      if (!m.has_availability) {
        const btn = qs("[data-action-reserve]", card);
        if (btn) {
          btn.textContent = "Reservar";
          disableLink(btn);
        }
        // Limpia hints y estilos
        const hintNormal = qs("[data-hint-normal]", card);
        const hintPremium = qs("[data-hint-premium]", card);
        if (hintNormal) hintNormal.textContent = "";
        if (hintPremium) hintPremium.textContent = "";
        markSelected(card, "normal");
        return;
      }

      // Default de selección (si nunca se eligió)
      const sel = defaultSelectionForCard(card, m);
      setSelectedType(card, sel);

      // Bind eventos de selección (una sola vez)
      const rowNormal = qs('[data-room-choice="normal"]', card);
      const rowPremium = qs('[data-room-choice="premium"]', card);

      if (rowNormal && !rowNormal._bound) {
        rowNormal._bound = true;
        const handler = () => {
          setSelectedType(card, "normal");
          updateReserveButton(card, motelId, m, checkinValue, checkoutValue);
        };
        rowNormal.addEventListener("click", handler);
        rowNormal.addEventListener("keydown", (ev) => {
          if (ev.key === "Enter" || ev.key === " ") {
            ev.preventDefault();
            handler();
          }
        });
      }

      if (rowPremium && !rowPremium._bound) {
        rowPremium._bound = true;
        const handler = () => {
          setSelectedType(card, "premium");
          updateReserveButton(card, motelId, m, checkinValue, checkoutValue);
        };
        rowPremium.addEventListener("click", handler);
        rowPremium.addEventListener("keydown", (ev) => {
          if (ev.key === "Enter" || ev.key === " ") {
            ev.preventDefault();
            handler();
          }
        });
      }

      // Actualiza el botón según selección y fechas
      updateReserveButton(card, motelId, m, checkinValue, checkoutValue);
    });
  }

  // -------------------------
  // Boot
  // -------------------------
  document.addEventListener("DOMContentLoaded", () => {
    const root = document.getElementById("motel_availability_root");
    if (!root) return;

    const checkin = qs("#checkin");
    const checkout = qs("#checkout");
    const errorBox = qs("#date_error");
    if (!checkin || !checkout || !errorBox) return;

    const t = todayLocalISO();

    // Defaults
    if (!checkin.value) checkin.value = t;
    if (!checkout.value) checkout.value = addDaysISO(checkin.value, 1);

    checkin.min = t;
    checkout.min = addDaysISO(checkin.value, 1);

    function showError(msg) {
      if (!msg) {
        errorBox.classList.add("d-none");
        errorBox.textContent = "";
      } else {
        errorBox.classList.remove("d-none");
        errorBox.textContent = msg;
      }
    }

    async function onChangeImpl() {
      // Ajusta min checkout (>= checkin + 1)
      checkout.min = addDaysISO(checkin.value, 1);

      // Auto-fix checkout si quedó inválido
      if (checkout.value <= checkin.value) {
        checkout.value = addDaysISO(checkin.value, 1);
      }

      const err = validateDates(checkin.value, checkout.value);
      if (err) {
        showError(err);
        return;
      }
      showError(null);

      try {
        const motels = await refreshAvailability(checkin.value, checkout.value);
        renderMotels(motels, checkin.value, checkout.value);
      } catch (e) {
        showError((e && e.message) || "Error consultando disponibilidad.");
      }
    }

    const onChange = debounce(onChangeImpl, 150);

    checkin.addEventListener("change", onChange);
    checkout.addEventListener("change", onChange);

    onChangeImpl();
  });
})();
