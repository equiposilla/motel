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

    if (!r.ok) {
      throw new Error((data && data.error) || "Error consultando disponibilidad.");
    }
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
  // Selection UI helpers
  // -------------------------
  function getSelectedType(card) {
    // Persistencia por card (no global) porque cada motel puede tener elección distinta
    return card.getAttribute("data-selected-room-type") || null;
  }

  function setSelectedType(card, type) {
    card.setAttribute("data-selected-room-type", type);
  }

  function markSelected(card, type) {
    const normal = qs('[data-room-choice="normal"]', card);
    const premium = qs('[data-room-choice="premium"]', card);

    // Limpia marcas
    if (normal) {
      normal.classList.remove("border-primary");
      normal.classList.remove("bg-light");
    }
    if (premium) {
      premium.classList.remove("border-primary");
      premium.classList.remove("bg-light");
    }

    // Marca el seleccionado
    const selectedEl = type === "premium" ? premium : normal;
    if (selectedEl) {
      selectedEl.classList.add("border-primary");
      selectedEl.classList.add("bg-light");
    }

    // Hint textual
    const hintNormal = qs("[data-hint-normal]", card);
    const hintPremium = qs("[data-hint-premium]", card);
    if (hintNormal) hintNormal.textContent = type === "normal" ? "✓ Seleccionado" : "";
    if (hintPremium) hintPremium.textContent = type === "premium" ? "✓ Seleccionado" : "";
  }

  function updateReserveButton(card, motelId, m, checkinValue, checkoutValue) {
    const btn = qs("[data-action-reserve]", card);
    if (!btn) return;

    const selected = getSelectedType(card) || "normal";
    const availNormal = (m.normal && m.normal.available) || 0;
    const availPremium = (m.premium && m.premium.available) || 0;

    // Si el seleccionado no tiene disponibilidad, no lo “cambiamos” automáticamente:
    // solo deshabilitamos para que el usuario elija el otro tipo.
    let canReserve = false;

    if (selected === "normal") {
      canReserve = availNormal > 0;
    } else {
      canReserve = availPremium > 0;
    }

    // Actualiza texto del botón según selección
    const label = selected === "premium" ? "Reservar (Premium)" : "Reservar (Normal)";
    btn.textContent = label;

    if (canReserve) {
      setReserveLink(btn, motelId, selected, checkinValue, checkoutValue);
      enableLink(btn);
    } else {
      disableLink(btn);
    }

    // Pinta selección (aunque no haya disponibilidad, se marca igual)
    markSelected(card, selected);
  }

  function defaultSelectionForCard(card, m) {
    // Si ya eligió antes, respétalo
    const existing = getSelectedType(card);
    if (existing === "normal" || existing === "premium") return existing;

    // Default: normal si hay, sino premium si hay, sino normal
    if (m.normal && m.normal.available > 0) return "normal";
    if (m.premium && m.premium.available > 0) return "premium";
    return "normal";
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

      // Pintar precios y disponibilidad (con checks de existencia)
      const elPriceNormal = qs("[data-price-normal]", card);
      const elPricePremium = qs("[data-price-premium]", card);
      const elAvailNormal = qs("[data-available-normal]", card);
      const elAvailPremium = qs("[data-available-premium]", card);

      if (elPriceNormal) elPriceNormal.textContent = formatMoney(m.normal && m.normal.price);
      if (elPricePremium) elPricePremium.textContent = formatMoney(m.premium && m.premium.price);
      if (elAvailNormal) elAvailNormal.textContent = String((m.normal && m.normal.available) || 0);
      if (elAvailPremium) elAvailPremium.textContent = String((m.premium && m.premium.available) || 0);

      // Estado general
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

      // Si NO hay disponibilidad de nada: deshabilitar botón y limpiar hints
      if (!m.has_availability) {
        const btn = qs("[data-action-reserve]", card);
        if (btn) {
          btn.textContent = "Reservar";
          disableLink(btn);
        }
        const hintNormal = qs("[data-hint-normal]", card);
        const hintPremium = qs("[data-hint-premium]", card);
        if (hintNormal) hintNormal.textContent = "";
        if (hintPremium) hintPremium.textContent = "";
        // Limpia estilos de selección
        markSelected(card, "normal"); // marca algo por consistencia visual
        return;
      }

      // Default de selección por card (si nunca se eligió)
      const sel = defaultSelectionForCard(card, m);
      setSelectedType(card, sel);

      // Bind de eventos de selección (una sola vez por elemento)
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

      // Actualiza botón de reserva según selección actual
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

    // Defaults UX
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
      // Ajusta min checkout siempre basado en checkin
      checkout.min = addDaysISO(checkin.value, 1);

      // Auto-fix si checkout quedó inválido
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
