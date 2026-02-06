/** @odoo-module **/

function qs(sel, root) { return (root || document).querySelector(sel); }
function show(el) { el && el.classList.remove("d-none"); }
function hide(el) { el && el.classList.add("d-none"); }

function escapeHtml(str) {
  return String(str)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function isValidLatLng(lat, lng) {
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) return false;
  if (lat < -90 || lat > 90) return false;
  if (lng < -180 || lng > 180) return false;
  if (lat === 0 && lng === 0) return false; // regla práctica para “no geocodificado”
  return true;
}

async function fetchMotels() {
  const r = await fetch("/motels/map_data", {
    method: "POST",
    headers: { "Content-Type": "application/json", "Accept": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify({}),
  });

  const raw = await r.json().catch(() => null);
  console.debug("[motel_map] raw response:", raw);

  if (!r.ok) {
    throw new Error(`HTTP ${r.status} ${r.statusText}`);
  }

  // Odoo type="json" devuelve JSON-RPC: {result:{...}}
  const payload = raw && raw.result ? raw.result : raw;
  console.debug("[motel_map] parsed result:", payload);

  if (!payload) throw new Error("Respuesta vacía del servidor.");
  return payload;
}

function initMapUI(motels) {
  if (!window.L) throw new Error("Leaflet no cargó (window.L no existe).");
  if (!L.markerClusterGroup) throw new Error("MarkerCluster no cargó (L.markerClusterGroup no existe).");

  const el = document.getElementById("motels_map");
  if (!el) throw new Error("No existe #motels_map en el DOM.");
  if (el.offsetHeight < 50) throw new Error(`El contenedor del mapa tiene altura muy pequeña: ${el.offsetHeight}px`);

  const tileUrl = window.motelMapTileUrl || "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";
  const attribution = window.motelMapAttribution || "&copy; OpenStreetMap";

  // Vista default CDMX
  const map = L.map("motels_map", { zoomControl: true }).setView([19.4326, -99.1332], 11);
  L.tileLayer(tileUrl, { maxZoom: 19, attribution }).addTo(map);

  const cluster = L.markerClusterGroup({ chunkedLoading: true });

  const bounds = [];
  const invalid = [];

  for (const m of motels) {
    const lat = Number(m.lat);
    const lng = Number(m.lng);

    if (!isValidLatLng(lat, lng)) {
      invalid.push({ id: m.id, name: m.name, lat: m.lat, lng: m.lng });
      continue;
    }

    const popup = `
      <div style="min-width:220px">
        <div style="font-weight:700">${escapeHtml(m.name || "")}</div>
        <div style="margin:6px 0;color:#6b7280">${escapeHtml(m.address || "")}</div>
        <a class="btn btn-sm btn-primary" href="${m.detail_url || "#"}">Ver detalle</a>
      </div>`;

    cluster.addLayer(L.marker([lat, lng], { title: m.name || "Motel" }).bindPopup(popup));
    bounds.push([lat, lng]);
  }

  if (invalid.length) {
    console.warn("[motel_map] motels sin coords válidas:", invalid);
  }

  map.addLayer(cluster);

  if (bounds.length) {
    map.fitBounds(bounds, { padding: [30, 30] });
  } else {
    throw new Error("No hay coordenadas válidas para mostrar en el mapa (lat/lng = 0 o inválidas).");
  }
}

async function boot() {
  const root = qs("#motel_map_root");
  if (!root) return;

  const status = qs("#map_status", root);
  const errBox = qs("#map_error", root);
  const errMsg = qs("#map_error_msg", root);
  const empty = qs("#map_empty", root);
  const retry = qs("#map_retry", root);

  async function load() {
    hide(errBox); hide(empty);
    show(status);
    status.textContent = "Cargando mapa…";

    try {
      const data = await fetchMotels();
      hide(status);

      if (!data.ok) {
        show(errBox);
        errMsg.textContent = data.error || "No se pudo cargar el mapa.";
        return;
      }

      const motels = data.motels || [];
      if (!motels.length) {
        show(empty);
        return;
      }

      initMapUI(motels);

    } catch (e) {
      console.error("[motel_map] load error:", e);
      hide(status);
      show(errBox);
      errMsg.textContent = e?.message || "No se pudo cargar el mapa.";
    }
  }

  retry && retry.addEventListener("click", load);
  load();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", boot);
} else {
  boot();
}
