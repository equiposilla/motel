(function () {
  "use strict";

  function qs(sel, root) {
    return (root || document).querySelector(sel);
  }

  function formatMoney(v) {
    return "$" + Number(v || 0).toFixed(2);
  }

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

  async function refreshAvailability(checkin, checkout) {
    const url =
      `/motels/availability_http?checkin=${encodeURIComponent(checkin)}` +
      `&checkout=${encodeURIComponent(checkout)}`;

    const r = await fetch(url, { credentials: "same-origin" });
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || "Error consultando disponibilidad.");
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
      const motelId = Number(card.querySelector("input[data-motel-id]").value);
      const m = motels.find((x) => x.id === motelId);
      if (!m) return;

      card.querySelector("[data-price-normal]").textContent = formatMoney(m.normal.price);
      card.querySelector("[data-price-premium]").textContent = formatMoney(m.premium.price);
      card.querySelector("[data-available-normal]").textContent = m.normal.available;
      card.querySelector("[data-available-premium]").textContent = m.premium.available;

      const status = card.querySelector("[data-status]");
      const btnNormal = card.querySelector("[data-action-reserve-normal]");
      const btnPremium = card.querySelector("[data-action-reserve-premium]");

      if (!m.has_availability) {
        status.textContent = "Sin disponibilidad";
        status.className = "badge bg-danger";
        disableLink(btnNormal);
        disableLink(btnPremium);
        return;
      }

      const parts = [];
      if (m.normal.available > 0) parts.push("Normal");
      if (m.premium.available > 0) parts.push("Premium");

      status.textContent = "Disponible: " + parts.join(" / ");
      status.className = "badge bg-success";

      if (m.normal.available > 0) {
        setReserveLink(btnNormal, motelId, "normal", checkinValue, checkoutValue);
        enableLink(btnNormal);
      } else {
        disableLink(btnNormal);
      }

      if (m.premium.available > 0) {
        setReserveLink(btnPremium, motelId, "premium", checkinValue, checkoutValue);
        enableLink(btnPremium);
      } else {
        disableLink(btnPremium);
      }
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    const root = document.getElementById("motel_availability_root");
    if (!root) return;

    const checkin = qs("#checkin");
    const checkout = qs("#checkout");
    const errorBox = qs("#date_error");

    const t = todayLocalISO();
    checkin.value = t;
    checkout.value = addDaysISO(t, 1);
    checkin.min = t;
    checkout.min = addDaysISO(t, 1);

    async function onChange() {
      checkout.min = addDaysISO(checkin.value, 1);
      if (checkout.value <= checkin.value) {
        checkout.value = addDaysISO(checkin.value, 1);
      }

      const err = validateDates(checkin.value, checkout.value);
      if (err) {
        errorBox.classList.remove("d-none");
        errorBox.textContent = err;
        return;
      }
      errorBox.classList.add("d-none");

      const motels = await refreshAvailability(checkin.value, checkout.value);
      renderMotels(motels, checkin.value, checkout.value);
    }

    checkin.addEventListener("change", onChange);
    checkout.addEventListener("change", onChange);
    onChange();
  });
})();
