/** @odoo-module **/

import { registry } from "@web/core/registry";
import { FloatField } from "@web/views/fields/float/float_field";
import { onMounted, onWillUnmount } from "@odoo/owl";

export class GeoPickerField extends FloatField {
  static template = "motel.GeoPickerField";

  setup() {
    super.setup();
    this.map = null;
    this.marker = null;

    onMounted(() => this._initMap());
    onWillUnmount(() => this._destroyMap());
  }

  _lngField() {
    return this.props?.options?.lng_field || "longitude";
  }

  async _write(lat, lng) {
    const latNum = Number(lat);
    const lngNum = Number(lng);

    const values = {};
    values[this.props.name] = Number.isFinite(latNum) ? latNum : false;
    values[this._lngField()] = Number.isFinite(lngNum) ? lngNum : false;

    // ✅ correcto en Odoo 19
    return this.props.record.update(values);
  }

  _currentLatLng() {
    const lat = this.props.record.data[this.props.name];
    const lng = this.props.record.data[this._lngField()];
    return {
      lat: (lat === false || lat === null || lat === undefined) ? null : Number(lat),
      lng: (lng === false || lng === null || lng === undefined) ? null : Number(lng),
    };
  }

  _initMap() {
    if (!window.L) {
      console.error("[geo_picker] Leaflet no está cargado (window.L missing)");
      return;
    }

    const el = this.el?.querySelector(".o_geo_picker_map");
    if (!el) return;

    const { lat, lng } = this._currentLatLng();
    const start = (Number.isFinite(lat) && Number.isFinite(lng)) ? [lat, lng] : [19.4326, -99.1332];

    this.map = L.map(el).setView(start, (start[0] === 19.4326 ? 5 : 14));
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: "&copy; OpenStreetMap",
    }).addTo(this.map);

    if (Number.isFinite(lat) && Number.isFinite(lng)) {
      this.marker = L.marker([lat, lng]).addTo(this.map);
    }

    this.map.on("click", async (ev) => {
      const p = ev.latlng;
      if (!p) return;

      if (this.marker) this.marker.setLatLng(p);
      else this.marker = L.marker(p).addTo(this.map);

      await this._write(p.lat, p.lng);
    });
  }

  _destroyMap() {
    try {
      if (this.map) {
        this.map.off();
        this.map.remove();
      }
    } catch {}
    this.map = null;
    this.marker = null;
  }

  async onClearLocation(ev) {
    ev?.preventDefault?.();
    ev?.stopPropagation?.();

    if (this.marker && this.map) {
      this.map.removeLayer(this.marker);
      this.marker = null;
    }
    await this._write(false, false);
  }
}

registry.category("fields").add("geo_picker", { component: GeoPickerField });
