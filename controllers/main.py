# controllers/main.py
import json
from datetime import date

from odoo import http, fields
from odoo.http import request


class MotelAvailabilityController(http.Controller):
    """
    HU-01:
    - /motels: página pública (Website)
    - /motels/availability: JSON-RPC (type="json") para clientes Odoo (si se usa)
    - /motels/availability_http: API HTTP GET JSON (para Website minimal + fetch)
    """

    @http.route("/motels", type="http", auth="public", website=True, sitemap=True)
    def motels_page(self, **kw):
        motels = request.env["motel.motel"].sudo().search([], order="id asc", limit=4)
        today = fields.Date.to_string(date.today())
        return request.render(
            "motel_availability.motels_page",
            {"motels": motels, "today": today},
        )

    # ----------------------------
    # Helpers (comparten lógica)
    # ----------------------------
    def _validate_dates(self, checkin, checkout):
        d_in = fields.Date.from_string(checkin) if checkin else None
        d_out = fields.Date.from_string(checkout) if checkout else None

        if not d_in or not d_out or d_out <= d_in:
            return None, None, "Rango de fechas inválido."
        if d_in < date.today():
            return None, None, "No se permiten fechas en el pasado."
        return d_in, d_out, None

    def _compute_availability_payload(self, d_in, d_out):
        Motel = request.env["motel.motel"].sudo()
        Room = request.env["motel.room"].sudo()
        Res = request.env["motel.reservation"].sudo()

        motels = Motel.search([], order="id asc", limit=4)

        # Totales por motel y tipo
        totals = Room.read_group(
            domain=[("motel_id", "in", motels.ids), ("active", "=", True)],
            fields=["motel_id", "room_type_id"],
            groupby=["motel_id", "room_type_id"],
            lazy=False,
        )
        total_map = {(r["motel_id"][0], r["room_type_id"][0]): r["__count"] for r in totals}

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
            occ_by_type = {(r["motel_id"][0], r["room_type_id"][0]): r["__count"] for r in occ2}

        # Precios / códigos por tipo
        rtypes = request.env["motel.room.type"].sudo().search([])
        price_by_type = {rt.id: float(rt.price_per_night) for rt in rtypes}
        code_by_type = {rt.id: rt.code for rt in rtypes}

        payload = []
        for m in motels:
            normal = {"available": 0, "price": 0.0}
            premium = {"available": 0, "price": 0.0}

            for rt in rtypes:
                total = total_map.get((m.id, rt.id), 0)
                occ = occ_by_type.get((m.id, rt.id), 0)
                avail = max(total - occ, 0)
                item = {"available": avail, "price": price_by_type.get(rt.id, 0.0)}

                if code_by_type.get(rt.id) == "normal":
                    normal = item
                elif code_by_type.get(rt.id) == "premium":
                    premium = item

            payload.append(
                {
                    "id": m.id,
                    "name": m.name,
                    "location": m.display_address(),
                    "room_total": m.room_total,
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
        """
        Endpoint JSON-RPC (útil si en algún momento usas el cliente rpc de Odoo).
        """
        d_in, d_out, err = self._validate_dates(checkin, checkout)
        if err:
            return {"error": err}
        return {"motels": self._compute_availability_payload(d_in, d_out)}

    # ----------------------------
    # HTTP JSON (Website minimal + fetch)
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
        """
        Endpoint HTTP estándar (GET) que devuelve JSON.
        Pensado para ser consumido con fetch() desde páginas Website minimal.
        """
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
    