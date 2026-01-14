# controllers/main.py
import json
from datetime import timedelta

from odoo import http, fields
from odoo.http import request


class MotelAvailabilityController(http.Controller):
    """
    HU-01:
    - /motels: página pública (Website)
    - /motels/availability: JSON-RPC (type="json")
    - /motels/availability_http: HTTP GET JSON (para fetch desde website)

    HU-04:
    - Precios base: normal=100, premium=200
    - Estancias >= 6 noches => +50% sobre total base
    - El backend es la fuente única del cálculo (UI solo muestra lo que recibe)
    """

    # ----------------------------
    # HU-04 Pricing rules (fuente única)
    # ----------------------------
    PRICE_PER_DAY = {"normal": 100.0, "premium": 200.0}
    LONG_STAY_MIN_DAYS = 6
    LONG_STAY_MULTIPLIER = 1.5

    # ----------------------------
    # Página HU-01
    # ----------------------------
    @http.route("/motels", type="http", auth="public", website=True, sitemap=True)
    def motels_page(self, **kw):
        motels = request.env["motel.motel"].sudo().search([], order="id asc", limit=4)
        today = fields.Date.to_string(fields.Date.context_today(request.env.user))
        return request.render("motel_availability.motels_page", {"motels": motels, "today": today})

    # ----------------------------
    # Helpers
    # ----------------------------
    def _today(self):
        return fields.Date.context_today(request.env.user)

    def _validate_dates(self, checkin, checkout):
        d_in = fields.Date.from_string(checkin) if checkin else None
        d_out = fields.Date.from_string(checkout) if checkout else None

        if not d_in or not d_out:
            return None, None, "Selecciona fecha de entrada y salida."
        if d_out <= d_in:
            return None, None, "La salida debe ser posterior a la entrada."
        if d_in < self._today():
            return None, None, "No se permiten fechas en el pasado."
        return d_in, d_out, None

    def _get_room_types(self):
        """
        Para HU-01: solo normal/premium (si existen).
        Fallback a todos para no romper instalaciones incompletas.
        """
        RoomType = request.env["motel.room.type"].sudo()
        rtypes = RoomType.search([("code", "in", ("normal", "premium"))])
        return rtypes or RoomType.search([])

    def _compute_price(self, room_type_code, d_in, d_out):
        """
        HU-04:
        - normal: 100/día
        - premium: 200/día
        - >=6 noches => total * 1.5

        Retorna (pricing_dict, error_msg)
        """
        if room_type_code not in ("normal", "premium"):
            return None, "Tipo de habitación inválido."

        nights = (d_out - d_in).days
        if nights <= 0:
            return None, "Rango de fechas inválido."

        base_per_day = self.PRICE_PER_DAY[room_type_code]
        base_total = base_per_day * nights
        surcharge = nights >= self.LONG_STAY_MIN_DAYS
        final_total = base_total * self.LONG_STAY_MULTIPLIER if surcharge else base_total

        return {
            "room_type": room_type_code,
            "nights": nights,
            "base_per_day": base_per_day,
            "base_total": base_total,
            "surcharge_applied": surcharge,
            "final_total": final_total,
        }, None

    def _compute_availability_payload(self, d_in, d_out):
        Motel = request.env["motel.motel"].sudo()
        Room = request.env["motel.room"].sudo()
        Res = request.env["motel.reservation"].sudo()

        motels = Motel.search([], order="id asc", limit=4)
        rtypes = self._get_room_types()

        nights = (d_out - d_in).days

        # Totales por motel y tipo
        totals = Room.read_group(
            domain=[("motel_id", "in", motels.ids), ("active", "=", True)],
            fields=["motel_id", "room_type_id"],
            groupby=["motel_id", "room_type_id"],
            lazy=False,
        )
        total_map = {}
        for r in totals:
            if r.get("motel_id") and r.get("room_type_id"):
                total_map[(r["motel_id"][0], r["room_type_id"][0])] = r["__count"]

        # Habitaciones ocupadas por traslape (solo confirmed)
        occupied = Res.read_group(
            domain=[
                ("state", "=", "confirmed"),
                ("motel_id", "in", motels.ids),
                ("checkin_date", "<", d_out),
                ("checkout_date", ">", d_in),
            ],
            fields=["room_id"],
            groupby=["room_id"],
            lazy=False,
        )
        occupied_room_ids = [r["room_id"][0] for r in occupied if r.get("room_id")]

        # Ocupación por tipo
        occ_by_type = {}
        if occupied_room_ids:
            occ2 = Room.read_group(
                domain=[("id", "in", occupied_room_ids)],
                fields=["motel_id", "room_type_id"],
                groupby=["motel_id", "room_type_id"],
                lazy=False,
            )
            for r in occ2:
                if r.get("motel_id") and r.get("room_type_id"):
                    occ_by_type[(r["motel_id"][0], r["room_type_id"][0])] = r["__count"]

        # Map de códigos por type-id (para asignar avail a normal/premium)
        code_by_type = {rt.id: (rt.code or "").strip() for rt in rtypes}

        # Precios calculados HU-04 (por fechas)
        normal_pr, _ = self._compute_price("normal", d_in, d_out)
        premium_pr, _ = self._compute_price("premium", d_in, d_out)

        payload = []
        for m in motels:
            normal = {
                "available": 0,
                "price_per_day": normal_pr["base_per_day"],
                "final_total": normal_pr["final_total"],
                "surcharge": normal_pr["surcharge_applied"],
            }
            premium = {
                "available": 0,
                "price_per_day": premium_pr["base_per_day"],
                "final_total": premium_pr["final_total"],
                "surcharge": premium_pr["surcharge_applied"],
            }

            for rt in rtypes:
                total = total_map.get((m.id, rt.id), 0)
                occ = occ_by_type.get((m.id, rt.id), 0)
                avail = max(total - occ, 0)

                code = code_by_type.get(rt.id)
                if code == "normal":
                    normal["available"] = avail
                elif code == "premium":
                    premium["available"] = avail

            payload.append(
                {
                    "id": m.id,
                    "name": m.name,
                    "location": m.display_address(),
                    "room_total": m.room_total,
                    "nights": nights,
                    "normal": normal,
                    "premium": premium,
                    "has_availability": (normal["available"] + premium["available"]) > 0,
                }
            )

        return payload

    # ----------------------------
    # JSON-RPC (type="json")
    # ----------------------------
    @http.route("/motels/availability", type="json", auth="public", website=True)
    def motels_availability(self, checkin, checkout):
        d_in, d_out, err = self._validate_dates(checkin, checkout)
        if err:
            return {"error": err}
        return {"motels": self._compute_availability_payload(d_in, d_out)}

    # ----------------------------
    # HTTP JSON (Website + fetch)
    # ----------------------------
    @http.route(
        "/motels/availability_http",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        website=True,
    )
    def motels_availability_http(self, checkin=None, checkout=None, **kw):
        d_in, d_out, err = self._validate_dates(checkin, checkout)
        if err:
            return request.make_response(
                json.dumps({"error": err}),
                headers=[("Content-Type", "application/json")],
                status=400,
            )

        payload = self._compute_availability_payload(d_in, d_out)
        return request.make_response(
            json.dumps({"motels": payload}),
            headers=[("Content-Type", "application/json")],
            status=200,
        )
