/** @odoo-module **/

import {
  Component,
  onMounted,
  onWillUnmount,
  onPatched,
  onWillUpdateProps,
  useRef,
} from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

export class GeoPickerField extends Component {
  static template = "motel.GeoPickerField";
  static props = {
    ...standardFieldProps,
    options: { type: Object, optional: true }, // options="{'lng_field': 'longitude'}"
  };

  setup() {
    this.mapRef = useRef("map");
    this.map = null;
    this.marker = null;
    this._resizeObs = null;

    onMounted(() => this._initMapSafe());
    onPatched(() => this._invalidateMapSize());
    onWillUnmount(() => this._destroyMap());

    // Si cambia el record/valores, sincroniza el pin (más confiable que useEffect aquí)
    onWillUpdateProps((nextProps) => this._syncFromNextProps(nextProps));
  }

  // -----------------------------
  // Config / helpers
  // -----------------------------
  get lngField() {
    return (this.props.options && this.props.options.lng_field) || "longitude";
  }

  _toNum(v) {
    if (v === false || v === null || v === undefined || v === "") return null;
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }

  _isValidLatLng(lat, lng) {
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) return false;
    if (Math.abs(lat) > 90 || Math.abs(lng) > 180) return false;
    // opcional: 0,0 como vacío
    if (lat === 0 && lng === 0) return false;
    return true;
  }

  _getLatLngFromProps(props = this.props) {
    // lat preferido: props.value, fallback record.data[name]
    const latCandidate =
      props.value !== undefined ? props.value : props.record?.data?.[props.name];

    const lat = this._toNum(latCandidate);
    const lng = this._toNum(props.record?.data?.[this.lngField]);

    if (lat === null || lng === null) return null;
    return this._isValidLatLng(lat, lng) ? { lat, lng } : null;
  }

  async _write(lat, lng) {
    const latNum = this._toNum(lat);
    const lngNum = this._toNum(lng);

    const ok =
      latNum !== null &&
      lngNum !== null &&
      this._isValidLatLng(latNum, lngNum);

    const values = {};
    values[this.props.name] = ok ? latNum : false;
    values[this.lngField] = ok ? lngNum : false;

    // ✅ Odoo 19
    return this.props.record.update(values);
  }

  // -----------------------------
  // Leaflet icon fix (anti-duplicación)
  // -----------------------------
  _initLeafletDefaultIconFix() {
    const L = window.L;
    if (!L?.Icon?.Default) return;

    // Evita aplicar el fix dos veces (puede generar comportamientos raros)
    if (L.Icon.Default.__motelFixed) return;
    L.Icon.Default.__motelFixed = true;

    // Fix clásico: en bundles a veces _getIconUrl arma rutas relativas que terminan duplicadas.
    try {
      delete L.Icon.Default.prototype._getIconUrl;
    } catch {}

    // ✅ tus rutas reales (absolutas desde root)
    const base = "/motel/static/lib/leaflet/images/";
    L.Icon.Default.mergeOptions({
      iconRetinaUrl: base + "marker-icon-2x.png",
      iconUrl: base + "marker-icon.png",
      shadowUrl: base + "marker-shadow.png",
    });
  }

  // -----------------------------
  // Map init / size / destroy
  // -----------------------------
  _initMapSafe() {
    const el = this.mapRef.el;

    if (!el) {
      console.error("[geo_picker] No hay contenedor (t-ref='map').");
      return;
    }
    if (!window.L) {
      console.error(
        "[geo_picker] Leaflet no cargó (window.L undefined). Revisa web.assets_backend."
      );
      return;
    }

    // En notebooks/tabs a veces monta con height=0 -> Leaflet se rompe: init async + invalidate
    setTimeout(() => {
      try {
        this._initLeafletDefaultIconFix();
        const L = window.L;

        const fallback = { lat: 19.4326, lng: -99.1332 };
        const rec = this._getLatLngFromProps();
        const current = rec || fallback;

        const zoom = rec ? 14 : 5;

        this.map = L.map(el, { zoomControl: true }).setView(
          [current.lat, current.lng],
          zoom
        );

        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
          maxZoom: 19,
          attribution: "&copy; OpenStreetMap",
        }).addTo(this.map);

        // Marker inicial (si hay coords)
        this._syncMarkerFromProps(true);

        // Click para colocar pin (respeta readonly)
        this.map.on("click", async (ev) => {
          if (this.props.readonly) return;

          const lat = ev?.latlng?.lat;
          const lng = ev?.latlng?.lng;
          if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;

          this._setMarker(lat, lng, true);
          await this._write(lat, lng);
        });

        // ✅ ResizeObserver para notebook tabs / cambios de tamaño
        this._resizeObs = new ResizeObserver(() => this._invalidateMapSize());
        this._resizeObs.observe(el);

        // invalidates iniciales
        setTimeout(() => this._invalidateMapSize(), 0);
        setTimeout(() => this._invalidateMapSize(), 150);
      } catch (e) {
        console.error("[geo_picker] init error:", e);
      }
    }, 0);
  }

  _invalidateMapSize() {
    try {
      const el = this.mapRef?.el;
      if (!this.map || !el) return;
      if (el.offsetHeight === 0 || el.offsetWidth === 0) return; // evita romper Leaflet en hidden
      this.map.invalidateSize(true);
    } catch {}
  }

  _destroyMap() {
    try {
      if (this._resizeObs && this.mapRef.el) {
        this._resizeObs.unobserve(this.mapRef.el);
      }
      this._resizeObs = null;

      if (this.map) {
        this.map.off();
        this.map.remove();
      }
    } catch {
      // noop
    } finally {
      this.map = null;
      this.marker = null;
    }
  }

  // -----------------------------
  // Marker sync / drag
  // -----------------------------
  _setMarker(lat, lng, draggable = true) {
    if (!this.map || !window.L) return;
    const L = window.L;

    const ll = [lat, lng];

    if (!this.marker) {
      this.marker = L.marker(ll, { draggable }).addTo(this.map);

      if (draggable) {
        this.marker.on("dragend", async () => {
          if (this.props.readonly) return;

          const p = this.marker?.getLatLng?.();
          if (!p) return;

          this._setMarker(p.lat, p.lng, true);
          await this._write(p.lat, p.lng);
        });
      }
    } else {
      this.marker.setLatLng(ll);
    }
  }

  _removeMarker() {
    if (this.marker && this.map) {
      try {
        this.map.removeLayer(this.marker);
      } catch {}
    }
    this.marker = null;
  }

  _syncMarkerFromProps(first = false, props = this.props) {
    if (!this.map) return;

    const rec = this._getLatLngFromProps(props);

    if (rec) {
      this._setMarker(rec.lat, rec.lng, !this.props.readonly);
      if (first) this.map.setView([rec.lat, rec.lng], 14);
    } else {
      this._removeMarker();
      if (first) this.map.setView([19.4326, -99.1332], 5);
    }
  }

  _syncFromNextProps(nextProps) {
    // Se ejecuta aunque el mapa no exista todavía; no pasa nada
    if (!this.map) return;

    const next = this._getLatLngFromProps(nextProps);
    const cur = this._getLatLngFromProps(this.props);

    const changed =
      (next && !cur) ||
      (!next && cur) ||
      (next && cur && (next.lat !== cur.lat || next.lng !== cur.lng));

    if (changed) {
      this._syncMarkerFromProps(false, nextProps);
      setTimeout(() => this._invalidateMapSize(), 0);
    }
  }

  // -----------------------------
  // UI
  // -----------------------------
  async onClearLocation(ev) {
    ev?.preventDefault?.();
    ev?.stopPropagation?.();

    if (this.props.readonly) return;

    this._removeMarker();
    await this._write(false, false);

    // recentrar a fallback
    this._syncMarkerFromProps(true);
  }
}

registry.category("fields").add("geo_picker", { component: GeoPickerField });
