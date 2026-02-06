/** @odoo-module **/

import { Component, onMounted, onWillUnmount, useRef } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

export class GeoPickerField extends Component {
  static template = "motel.GeoPickerField";
  static props = {
    ...standardFieldProps,
    options: { type: Object, optional: true }, // para options="{'lng_field': 'longitude'}"
  };

  setup() {
    this.mapRef = useRef("map");
    this.map = null;
    this.marker = null;

    onMounted(() => this._initMapSafe());
    onWillUnmount(() => this._destroyMap());
  }

  get lngField() {
    return (this.props.options && this.props.options.lng_field) || "longitude";
  }

  _getLatLngFromRecord() {
    // En campos float, value puede venir como number o false
    const lat = Number(this.props.value);
    const lng = Number(this.props.record.data[this.lngField]);
    const ok = Number.isFinite(lat) && Number.isFinite(lng) && Math.abs(lat) <= 90 && Math.abs(lng) <= 180;
    return ok ? { lat, lng } : null;
  }

  async _write(lat, lng) {
    const latNum = Number(lat);
    const lngNum = Number(lng);

    const values = {};
    values[this.props.name] = Number.isFinite(latNum) ? latNum : false;
    values[this.lngField] = Number.isFinite(lngNum) ? lngNum : false;

    // ✅ API correcta en Odoo 19
    await this.props.record.update(values);
  }

  _setMarker(lat, lng) {
    if (!this.map) return;

    if (this.marker) {
      this.marker.setLatLng([lat, lng]);
    } else {
      this.marker = window.L.marker([lat, lng], { draggable: false }).addTo(this.map);
    }
  }

  _initLeafletDefaultIconFix() {
    // Fix típico en Odoo/asset pipeline: rutas de iconos de Leaflet
    const L = window.L;
    if (!L || !L.Icon || !L.Icon.Default) return;

    const base = "/motel/static/lib/leaflet/images/";
    L.Icon.Default.mergeOptions({
      iconRetinaUrl: base + "marker-icon-2x.png",
      iconUrl: base + "marker-icon.png",
      shadowUrl: base + "marker-shadow.png",
    });
  }

  _initMapSafe() {
    const el = this.mapRef.el;

    if (!el) return;

    if (!window.L) {
      console.error("[geo_picker] Leaflet no está cargado (window.L undefined). Revisa web.assets_backend.");
      return;
    }

    // Si el contenedor está invisible o con height 0 cuando monta, Leaflet se rompe.
    // Solución: inicializar con un pequeño delay y luego invalidateSize.
    setTimeout(() => {
      try {
        this._initLeafletDefaultIconFix();

        const L = window.L;

        // Centro por defecto (CDMX) si no hay coords
        const fallback = { lat: 19.4326, lng: -99.1332 };
        const current = this._getLatLngFromRecord() || fallback;

        this.map = L.map(el, { zoomControl: true }).setView([current.lat, current.lng], 11);

        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
          maxZoom: 19,
          attribution: "&copy; OpenStreetMap",
        }).addTo(this.map);

        // Pin inicial si hay coords válidas
        const rec = this._getLatLngFromRecord();
        if (rec) {
          this._setMarker(rec.lat, rec.lng);
        }

        // Click para colocar pin
        this.map.on("click", async (ev) => {
          const lat = ev.latlng.lat;
          const lng = ev.latlng.lng;
          this._setMarker(lat, lng);
          await this._write(lat, lng);
        });

        // Ajuste de tamaño (muy importante en formularios/notebook)
        setTimeout(() => {
          if (this.map) this.map.invalidateSize(true);
        }, 150);
      } catch (e) {
        console.error("[geo_picker] init error:", e);
      }
    }, 0);
  }

  _destroyMap() {
    try {
      if (this.map) {
        this.map.off();
        this.map.remove();
      }
    } finally {
      this.map = null;
      this.marker = null;
    }
  }

  async onClearLocation(ev) {
    ev?.preventDefault?.();
    ev?.stopPropagation?.();

    if (this.marker && this.map) {
      this.map.removeLayer(this.marker);
    }
    this.marker = null;

    await this._write(false, false);
  }
}

// ✅ Registro correcto para Odoo 19
registry.category("fields").add("geo_picker", { component: GeoPickerField });
