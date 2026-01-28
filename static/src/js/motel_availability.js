(function () {
  "use strict";

  // ============================================================
  // Utils
  // ============================================================
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

  // ============================================================
  // API
  // ============================================================
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

  // ============================================================
  // STATE (/motels)
  // ============================================================
  const STATE = {
    byMotelId: Object.create(null),
    boundCards: new WeakSet(),
    checkinEl: null,
    checkoutEl: null,
  };

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
  // Selection helpers (/motels)
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

    if (normal) normal.classList.remove("border-primary", "bg-light", "border-2");
    if (premium) premium.classList.remove("border-primary", "bg-light", "border-2");

    const el = type === "premium" ? premium : normal;
    if (el) el.classList.add("border-primary", "bg-light", "border-2");

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

  function getCurrentDates() {
    const checkinValue = STATE.checkinEl ? STATE.checkinEl.value : "";
    const checkoutValue = STATE.checkoutEl ? STATE.checkoutEl.value : "";
    return { checkinValue, checkoutValue };
  }

  function updateReserveButton(card, motelId) {
    const btn = qs("[data-action-reserve]", card);
    if (!btn) return;

    const m = STATE.byMotelId[motelId];
    if (!m) {
      disableLink(btn);
      btn.textContent = "Reservar";
      return;
    }

    const selected = getSelectedType(card) || "normal";
    const { checkinValue, checkoutValue } = getCurrentDates();

    const err = validateDates(checkinValue, checkoutValue);
    if (err) {
      disableLink(btn);
      btn.textContent = "Reservar";
      return;
    }

    const selectedBucket = selected === "premium" ? m.premium : m.normal;
    const available = Number((selectedBucket && selectedBucket.available) || 0);

    const typeLabel = selected === "premium" ? "Premium" : "Normal";
    const total = Number((selectedBucket && selectedBucket.final_total) || 0);
    btn.textContent = `Reservar (${typeLabel}) - ${formatMoney(total)}`;

    if (available > 0) {
      setReserveLink(btn, motelId, selected, checkinValue, checkoutValue);
      enableLink(btn);
    } else {
      disableLink(btn);
    }

    markSelected(card, selected);

    qsa("[data-nights]", card).forEach((el) => (el.textContent = String(m.nights || 0)));
  }

  function renderCard(card, m) {
    const motelInput = qs("input[data-motel-id]", card);
    if (!motelInput) return;

    const motelId = Number(motelInput.value);
    if (!motelId) return;

    STATE.byMotelId[motelId] = m;

    const priceNormal = qs("[data-price-normal]", card);
    const pricePremium = qs("[data-price-premium]", card);
    const availNormal = qs("[data-available-normal]", card);
    const availPremium = qs("[data-available-premium]", card);

    if (priceNormal) priceNormal.textContent = formatMoney(m.normal && m.normal.price_per_day);
    if (pricePremium) pricePremium.textContent = formatMoney(m.premium && m.premium.price_per_day);
    if (availNormal) availNormal.textContent = String((m.normal && m.normal.available) || 0);
    if (availPremium) availPremium.textContent = String((m.premium && m.premium.available) || 0);

    const totalNormal = qs("[data-total-normal]", card);
    const totalPremium = qs("[data-total-premium]", card);
    if (totalNormal) totalNormal.textContent = formatMoney(m.normal && m.normal.final_total);
    if (totalPremium) totalPremium.textContent = formatMoney(m.premium && m.premium.final_total);

    const surN = qs("[data-surcharge-normal]", card);
    const surP = qs("[data-surcharge-premium]", card);
    if (surN) surN.classList.toggle("d-none", !(m.normal && m.normal.surcharge));
    if (surP) surP.classList.toggle("d-none", !(m.premium && m.premium.surcharge));

    qsa("[data-nights]", card).forEach((el) => (el.textContent = String(m.nights || 0)));

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

    if (m.has_availability) {
      const sel = defaultSelectionForCard(card, m);
      setSelectedType(card, sel);
      markSelected(card, sel);
    } else {
      const btn = qs("[data-action-reserve]", card);
      if (btn) {
        btn.textContent = "Reservar";
        disableLink(btn);
      }
      markSelected(card, "normal");
      return;
    }

    updateReserveButton(card, motelId);
    bindCardEventsOnce(card, motelId);
  }

  function bindCardEventsOnce(card, motelId) {
    if (STATE.boundCards.has(card)) return;
    STATE.boundCards.add(card);

    const rowNormal = qs('[data-room-choice="normal"]', card);
    const rowPremium = qs('[data-room-choice="premium"]', card);

    const onSelect = (type) => {
      setSelectedType(card, type);
      markSelected(card, type);
      updateReserveButton(card, motelId);
    };

    if (rowNormal) {
      rowNormal.addEventListener("click", () => onSelect("normal"));
      rowNormal.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" || ev.key === " ") {
          ev.preventDefault();
          onSelect("normal");
        }
      });
    }

    if (rowPremium) {
      rowPremium.addEventListener("click", () => onSelect("premium"));
      rowPremium.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" || ev.key === " ") {
          ev.preventDefault();
          onSelect("premium");
        }
      });
    }
  }

  function renderMotels(motels) {
    qsa("#motels_grid .card").forEach((card) => {
      const motelInput = qs("input[data-motel-id]", card);
      if (!motelInput) return;

      const motelId = Number(motelInput.value);
      const m = motels.find((x) => x.id === motelId);
      if (!m) return;

      renderCard(card, m);
    });
  }

  // ============================================================
  // /motels/reserve - Live pricing for Extras (pets + wifi)
  // ============================================================
  function initReserveLivePricing() {
    const box = document.getElementById("pricing_box");
    if (!box) return; // Solo /motels/reserve

    const cbPets = document.getElementById("has_pets");
    const cbWifi = document.getElementById("wants_wifi");
    if (!cbPets || !cbWifi) return;

    // Datos base (del backend) expuestos como data-*
    const nights = Number(box.dataset.nights || 0);
    const baseTotal = Number(box.dataset.baseTotal || 0);
    const surcharge = String(box.dataset.surcharge || "0") === "1";

    const longMult = Number(box.dataset.longMult || 1.5);
    const petFlat = Number(box.dataset.petFlat || 25);
    const wifiPerNight = Number(box.dataset.wifiPerNight || 2);

    const elSubtotal = document.getElementById("ui_subtotal");
    const elPet = document.getElementById("ui_pet_fee");
    const elWifi = document.getElementById("ui_wifi_fee");
    const elFinal = document.getElementById("ui_final_total");

    function money(v) {
      return Number(v || 0).toFixed(2);
    }

    function recompute() {
      const petFee = cbPets.checked ? petFlat : 0;
      const wifiFee = cbWifi.checked ? wifiPerNight * nights : 0;

      const subtotal = surcharge ? baseTotal * longMult : baseTotal;
      const finalTotal = subtotal + petFee + wifiFee;

      if (elSubtotal) elSubtotal.textContent = money(subtotal);
      if (elPet) elPet.textContent = money(petFee);
      if (elWifi) elWifi.textContent = money(wifiFee);
      if (elFinal) elFinal.textContent = money(finalTotal);
    }

    cbPets.addEventListener("change", recompute);
    cbWifi.addEventListener("change", recompute);

    // Estado inicial (si vienen pre-chequeados)
    recompute();
  }

  // ============================================================
  // Boot
  // ============================================================
  document.addEventListener("DOMContentLoaded", () => {
    // 1) /motels: disponibilidad + cards
    const root = document.getElementById("motel_root");
    if (root) {
      const checkin = qs("#checkin");
      const checkout = qs("#checkout");
      const errorBox = qs("#date_error");
      if (checkin && checkout && errorBox) {
        STATE.checkinEl = checkin;
        STATE.checkoutEl = checkout;

        const t = todayLocalISO();
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
          checkout.min = addDaysISO(checkin.value, 1);
          if (checkout.value <= checkin.value) {
            checkout.value = addDaysISO(checkin.value, 1);
          }

          const err = validateDates(checkin.value, checkout.value);
          if (err) {
            showError(err);
            qsa("#motels_grid .card").forEach((card) => {
              const motelId = Number(qs("input[data-motel-id]", card)?.value || 0);
              if (motelId) updateReserveButton(card, motelId);
            });
            return;
          }

          showError(null);

          try {
            const motels = await refreshAvailability(checkin.value, checkout.value);
            renderMotels(motels);
            qsa("#motels_grid .card").forEach((card) => {
              const motelId = Number(qs("input[data-motel-id]", card)?.value || 0);
              if (motelId) updateReserveButton(card, motelId);
            });
          } catch (e) {
            showError((e && e.message) || "Error consultando disponibilidad.");
          }
        }

        const onChange = debounce(onChangeImpl, 150);
        checkin.addEventListener("change", onChange);
        checkout.addEventListener("change", onChange);

        onChangeImpl();
      }
    }

    // 2) /motels/reserve: pricing live extras
    initReserveLivePricing();
  });
})();
