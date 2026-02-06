from odoo import http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)


class MotelMapController(http.Controller):

    @http.route("/motels/map", type="http", auth="public", website=True, sitemap=True)
    def motels_map_page(self, **kw):
        return request.render("motel.motels_map_page", {})

    @http.route("/motels/map_data", type="json", auth="public", website=True, csrf=False)
    def motels_map_data(self, **kw):
        try:
            # IMPORTANTE: en website/public, usa sudo para leer moteles sin romper por reglas
            motels = request.env["motel.motel"].sudo().search([])

            out = []
            invalid = 0
            for m in motels:
                lat = m.latitude
                lng = m.longitude

                # Normaliza: si viene false/None, lo dejamos en None (NO 0.0)
                lat = float(lat) if lat not in (False, None) else None
                lng = float(lng) if lng not in (False, None) else None

                # Validación real (Leaflet no acepta None/NaN, y 0/0 normalmente es “sin geocodificar”)
                valid = (
                    lat is not None and lng is not None
                    and -90.0 <= lat <= 90.0
                    and -180.0 <= lng <= 180.0
                    and not (lat == 0.0 and lng == 0.0)
                )
                if not valid:
                    invalid += 1

                out.append({
                    "id": m.id,
                    "name": m.name or "",
                    "address": (m.city or "") if not hasattr(m, "display_address") else (m.display_address() or ""),
                    "detail_url": f"/motels/{m.id}",
                    "lat": lat,
                    "lng": lng,
                    "valid": valid,
                })

            meta = {
                "total": len(out),
                "valid": len(out) - invalid,
                "invalid": invalid,
            }

            _logger.info("[motel_map] payload total=%s valid=%s invalid=%s", meta["total"], meta["valid"], meta["invalid"])
            return {"ok": True, "motels": out, "meta": meta}

        except Exception as e:
            _logger.exception("[motel_map] error: %s", e)
            return {"ok": False, "error": "No se pudo cargar el mapa."}
