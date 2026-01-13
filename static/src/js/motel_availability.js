(function () {
  "use strict";

  function qs(sel, root) {
    return (root || document).querySelector(sel);
  }

  function formatMoney(v) {
    const n = Number(v || 0);
    return "$" + n.toFixed(2);
  }

  // Evita usar toISOString() para "hoy" porque depende de UTC (puede dar ayer/mañana)
  function todayLocalISO() {
    const d = new Date();
    const yyyy = d.getFullYear();
    const mm = String(d.getMonth() + 1).padStart(2, "0");
    const dd = String(d.getDate()).padStart(2, "0");
    return `${yyyy}-${mm}-${dd}`;
  }

  function addDaysISO(iso, days) {
    // Parse ISO YYYY-MM-DD como fecha local (evita desfases)
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
      throw new Error(data && data.error ? data.error : "Error consultando disponibilidad.");
    }
    return data.motels || [];
  }

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

  function renderMotels(motels, checkinValue, checkoutValue) {
    document.querySelectorAll("#motels_grid .card").forEach((card) => {
      const motelInput = card.querySelector("input[data-motel-id]");
      if (!motelInput) return;

      const motelId = Number(motelInput.value);
      const m = motels.find((x) => x.id === motelId);
      if (!m) return;

      const elPriceNormal = card.querySelector("[data-price-normal]");
      const elPricePremium = card.querySelector("[data-price-premium]");
      const elAvailNormal = card.querySelector("[data-available-normal]");
      const elAvailPremium = card.querySelector("[data-available-premium]");
      const status = card.querySelector("[data-status]");
      const btn = card.querySelector("[data-action-reserve]");

      if (elPriceNormal) elPriceNormal.textContent = formatMoney(m.normal && m.normal.price);
      if (elPricePremium) elPricePremium.textContent = formatMoney(m.premium && m.premium.price);
      if (elAvailNormal) elAvailNormal.textContent = String((m.normal && m.normal.available) || 0);
      if (elAvailPremium) elAvailPremium.textContent = String((m.premium && m.premium.available) || 0);

      if (!status || !btn) return;

      if (!m.has_availability) {
        status.textContent = "Sin disponibilidad";
        status.className = "badge bg-danger";
        disableLink(btn);
        return;
      }

      // Decide tipo por defecto: normal si hay, si no premium
      let chosenType = null;
      if (m.normal && m.normal.available > 0) chosenType = "normal";
      else if (m.premium && m.premium.available > 0) chosenType = "premium";

      const parts = [];
      if (m.normal && m.normal.available > 0) parts.push("Normal");
      if (m.premium && m.premium.available > 0) parts.push("Premium");
      status.textContent = "Disponible: " + (parts.length ? parts.join(" / ") : "—");
      status.className = "badge bg-success";

      if (!chosenType) {
        // raro, pero por seguridad
        disableLink(btn);
        return;
      }

      setReserveLink(btn, motelId, chosenType, checkinValue, checkoutValue);
      enableLink(btn);
    });
  }


  function debounce(fn, ms) {
    let t;
    return function (...args) {
      clearTimeout(t);
      t = setTimeout(() => fn.apply(this, args), ms);
    };
  }

  document.addEventListener("DOMContentLoaded", () => {
    const root = document.getElementById("motel_availability_root");
    if (!root) return;

    const checkin = qs("#checkin");
    const checkout = qs("#checkout");
    const errorBox = qs("#date_error");
    if (!checkin || !checkout || !errorBox) return;

    const t = todayLocalISO();
    if (!checkin.value) checkin.value = t;
    if (!checkout.value) checkout.value = addDaysISO(checkin.value || t, 1);

    checkin.min = t;
    // checkout.min debe ser >= checkin (mejor UX)
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
      // Ajusta min de checkout cuando cambias checkin
      checkout.min = addDaysISO(checkin.value, 1);

      // Si checkout quedó inválido, lo corregimos automáticamente
      if (checkout.value <= checkin.value) {
        checkout.value = addDaysISO(checkin.value, 1);
      }

      const err = validateDates(checkin.value, checkout.value);
      if (err) return showError(err);
      showError(null);

      // “loading” simple (opcional): podrías poner “Consultando…”
      try {
        const motels = await refreshAvailability(checkin.value, checkout.value);
        renderMotels(motels, checkin.value, checkout.value);
      } catch (e) {
        showError(e && e.message ? e.message : "Error consultando disponibilidad.");
      }
    }

    const onChange = debounce(onChangeImpl, 150);

    checkin.addEventListener("change", onChange);
    checkout.addEventListener("change", onChange);

    onChangeImpl();
  });
})();
