(function () {
  "use strict";

  function formatMoney(v) {
    return "$" + Number(v).toFixed(2);
  }
  function todayISO() {
    return new Date().toISOString().slice(0, 10);
  }
  function addDaysISO(iso, days) {
    const d = new Date(iso + "T00:00:00");
    d.setDate(d.getDate() + days);
    return d.toISOString().slice(0, 10);
  }
  function validateDates(checkin, checkout) {
    if (!checkin || !checkout) return "Selecciona entrada y salida.";
    if (checkout <= checkin) return "La salida debe ser posterior a la entrada.";
    if (checkin < todayISO()) return "No se permiten fechas en el pasado.";
    return null;
  }

  async function refreshAvailability(checkin, checkout) {
    // endpoint HTTP (GET) que devuelve JSON
    const url =
      `/motels/availability_http?checkin=${encodeURIComponent(checkin)}` +
      `&checkout=${encodeURIComponent(checkout)}`;
    const r = await fetch(url, { method: "GET" });
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || "Error consultando disponibilidad.");
    return data.motels;
  }

  function renderMotels(motels) {
    document.querySelectorAll("#motels_grid .card").forEach((card) => {
      const motelId = Number(card.querySelector("input[data-motel-id]").value);
      const m = motels.find((x) => x.id === motelId);
      if (!m) return;

      card.querySelector("[data-price-normal]").textContent = formatMoney(m.normal.price);
      card.querySelector("[data-price-premium]").textContent = formatMoney(m.premium.price);
      card.querySelector("[data-available-normal]").textContent = String(m.normal.available);
      card.querySelector("[data-available-premium]").textContent = String(m.premium.available);

      const status = card.querySelector("[data-status]");
      const btn = card.querySelector("[data-action-reserve]");

      if (!m.has_availability) {
        status.textContent = "Sin disponibilidad";
        status.className = "badge bg-danger";
        btn.disabled = true;
      } else {
        const parts = [];
        if (m.normal.available > 0) parts.push("Normal");
        if (m.premium.available > 0) parts.push("Premium");
        status.textContent = "Disponible: " + parts.join(" / ");
        status.className = "badge bg-success";
        btn.disabled = false; 
      }
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    const root = document.getElementById("motel_availability_root");
    if (!root) return;

    const checkin = document.getElementById("checkin");
    const checkout = document.getElementById("checkout");
    const errorBox = document.getElementById("date_error");

    const t = todayISO();
    checkin.value = t;
    checkout.value = addDaysISO(t, 1);
    checkin.min = t;
    checkout.min = t;

    function showError(msg) {
      if (!msg) {
        errorBox.classList.add("d-none");
        errorBox.textContent = "";
      } else {
        errorBox.classList.remove("d-none");
        errorBox.textContent = msg;
      }
    }

    async function onChange() {
      const err = validateDates(checkin.value, checkout.value);
      if (err) return showError(err);
      showError(null);

      try {
        const motels = await refreshAvailability(checkin.value, checkout.value);
        renderMotels(motels);
      } catch (e) {
        showError(e.message || "Error consultando disponibilidad.");
      }
    }

    checkin.addEventListener("change", onChange);
    checkout.addEventListener("change", onChange);
    onChange();
  });
})();
