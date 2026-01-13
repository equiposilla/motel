# controllers/main.py
import json
import logging
import re
import uuid
from datetime import date, timedelta

from odoo import http, fields
from odoo.http import request

_logger = logging.getLogger(__name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^[0-9+\-\s().]{7,20}$")  # básico; ajustable por país


class MotelAvailabilityController(http.Controller):
    # ==========================================================
    # HU-01: Página pública de moteles
    # ==========================================================
    @http.route("/motels", type="http", auth="public", website=True, sitemap=True)
    def motels_page(self, **kw):
        motels = request.env["motel.motel"].sudo().search([], order="id asc", limit=4)

        # ⚠️ date.today() usa zona del servidor; mejor contextual en website
        today = fields.Date.to_string(fields.Date.context_today(request.env.user))

        return request.render(
            "motel_availability.motels_page",
            {"motels": motels, "today": today},
        )

    # ==========================================================
    # Helpers
    # ==========================================================
    def _today(self):
        """Fecha 'hoy' en contexto Odoo (mejor para website)."""
        return fields.Date.context_today(request.env.user)

    def _validate_dates(self, checkin, checkout):
        """Devuelve (d_in, d_out, error_msg)."""
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
        Asegura que el cálculo HU-01 solo use normal/premium.
        Fallback: si no existen, usa todos (para no romper en BD incompleta).
        """
        RoomType = request.env["motel.room.type"].sudo()
        rtypes = RoomType.search([("code", "in", ("normal", "premium"))])
        return rtypes or RoomType.search([])

    def _compute_availability_payload(self, d_in, d_out):
        Motel = request.env["motel.motel"].sudo()
        Room = request.env["motel.room"].sudo()
        Res = request.env["motel.reservation"].sudo()

        motels = Motel.search([], order="id asc", limit=4)
        rtypes = self._get_room_types()

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

        # Ocupadas (reservas confirmadas traslapadas)
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

        price_by_type = {rt.id: float(rt.price_per_night or 0.0) for rt in rtypes}
        code_by_type = {rt.id: (rt.code or "").strip() for rt in rtypes}

        payload = []
        for m in motels:
            normal = {"available": 0, "price": 0.0}
            premium = {"available": 0, "price": 0.0}

            for rt in rtypes:
                total = total_map.get((m.id, rt.id), 0)
                occ = occ_by_type.get((m.id, rt.id), 0)
                avail = max(total - occ, 0)
                item = {"available": avail, "price": price_by_type.get(rt.id, 0.0)}

                code = code_by_type.get(rt.id)
                if code == "normal":
                    normal = item
                elif code == "premium":
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

    def _find_available_room(self, motel_id, room_type_code, d_in, d_out):
        """Selecciona 1 habitación libre (first-fit)."""
        RoomType = request.env["motel.room.type"].sudo()
        Room = request.env["motel.room"].sudo()
        Res = request.env["motel.reservation"].sudo()

        if room_type_code not in ("normal", "premium"):
            return None

        rt = RoomType.search([("code", "=", room_type_code)], limit=1)
        if not rt:
            return None

        rooms = Room.search(
            [
                ("motel_id", "=", motel_id),
                ("room_type_id", "=", rt.id),
                ("active", "=", True),
            ],
            order="id asc",
        )
        if not rooms:
            return None

        occupied = Res.search(
            [
                ("state", "=", "confirmed"),
                ("room_id", "in", rooms.ids),
                ("checkin_date", "<", d_out),
                ("checkout_date", ">", d_in),
            ]
        ).mapped("room_id")

        free_rooms = rooms - occupied
        return free_rooms[:1] if free_rooms else None

    def _get_or_create_partner(self, first, last, email, phone):
        Partner = request.env["res.partner"].sudo()
        email_norm = (email or "").strip().lower()

        partner = Partner.search([("email", "=", email_norm)], limit=1)
        if partner:
            vals = {}
            full_name = f"{first} {last}".strip()
            if full_name and (not partner.name or not partner.name.strip()):
                vals["name"] = full_name
            if phone and (not partner.phone or not partner.phone.strip()):
                vals["phone"] = phone
            if vals:
                partner.write(vals)
            return partner

        return Partner.create(
            {"name": f"{first} {last}".strip(), "email": email_norm, "phone": phone}
        )

    def _ensure_reservation_product(self):
        """
        Producto SERVICIO estable para líneas de venta.
        Se crea vía product.template para evitar problemas de variantes.
        """
        Template = request.env["product.template"].sudo()
        tmpl = Template.search([("default_code", "=", "MOTEL_ROOM_NIGHT")], limit=1)
        if not tmpl:
            tmpl = Template.create(
                {
                    "name": "Motel Room Night",
                    "default_code": "MOTEL_ROOM_NIGHT",
                    "type": "service",
                    "sale_ok": True,
                    "purchase_ok": False,
                }
            )
        return tmpl.product_variant_id

    # ==========================================================
    # HU-01: Endpoint HTTP (JSON) para disponibilidad (fetch)
    # ==========================================================
    @http.route(
        "/motels/availability_http",
        type="http",
        auth="public",
        website=True,
        methods=["GET"],
        csrf=False,
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

    # ==========================================================
    # (Opcional) HU-01: Endpoint JSON-RPC (si usas jsonRpc)
    # ==========================================================
    @http.route("/motels/availability", type="json", auth="public", website=True)
    def motels_availability(self, checkin, checkout):
        d_in, d_out, err = self._validate_dates(checkin, checkout)
        if err:
            return {"error": err}
        return {"motels": self._compute_availability_payload(d_in, d_out)}

    # ==========================================================
    # HU-02: Formulario público de reserva
    # ==========================================================
    @http.route("/motels/reserve", type="http", auth="public", website=True, sitemap=False)
    def reserve_page(self, motel_id=None, room_type=None, checkin=None, checkout=None, **kw):
        Motel = request.env["motel.motel"].sudo()

        motel = Motel.browse(int(motel_id)) if motel_id and str(motel_id).isdigit() else Motel.browse([])
        if motel_id and (not motel or not motel.exists()):
            return request.not_found()

        today = self._today()
        today_str = fields.Date.to_string(today)
        tomorrow_str = fields.Date.to_string(today + timedelta(days=1))

        # Si vienen fechas por querystring, validarlas suavemente (si fallan, cae a defaults)
        d_in, d_out, err = self._validate_dates(checkin or today_str, checkout or tomorrow_str)
        if err:
            checkin = today_str
            checkout = tomorrow_str
        else:
            checkin = fields.Date.to_string(d_in)
            checkout = fields.Date.to_string(d_out)

        room_type = (room_type or "").strip()
        if room_type not in ("normal", "premium"):
            room_type = "normal"  # default safe

        return request.render(
            "motel_availability.reserve_page",
            {
                "motel": motel,
                "room_type": room_type,
                "checkin": checkin,
                "checkout": checkout,
                "login_url": "/web/login",
                "errors": {},
                "prefill": {},
            },
        )

    # ==========================================================
    # HU-02: Confirmación (POST)
    # ==========================================================
    @http.route("/motels/confirm", type="http", auth="public", website=True, methods=["POST"], csrf=True)
    def confirm_reservation(self, **post):
        attempt_uuid = f"ATT-{uuid.uuid4().hex[:10].upper()}"
        ip = request.httprequest.remote_addr or "unknown"
        email = (post.get("email") or "").strip().lower()

        # --- Rate limit básico (IP + email) ---
        Rate = request.env["motel.rate.limit"].sudo()
        try:
            if Rate.is_limited(f"ip:{ip}", window_minutes=10, max_hits=10) or (
                email and Rate.is_limited(f"email:{email}", window_minutes=10, max_hits=5)
            ):
                return request.render(
                    "motel_availability.reserve_error",
                    {"message": "Demasiados intentos. Intenta más tarde.", "attempt_uuid": attempt_uuid},
                )
            Rate.hit(f"ip:{ip}")
            if email:
                Rate.hit(f"email:{email}")
        except Exception:
            _logger.exception("Rate limit failure (attempt=%s, ip=%s, email=%s)", attempt_uuid, ip, email)

        # --- Validaciones mínimas CA-02 ---
        first = (post.get("first_name") or "").strip()
        last = (post.get("last_name") or "").strip()
        phone = (post.get("phone") or "").strip()
        terms = post.get("terms") == "on"

        motel_id = (post.get("motel_id") or "").strip()
        room_type = (post.get("room_type") or "").strip()
        checkin = (post.get("checkin") or "").strip()
        checkout = (post.get("checkout") or "").strip()

        errors = {}
        if not first:
            errors["first_name"] = "Nombre(s) es obligatorio."
        if not last:
            errors["last_name"] = "Apellidos es obligatorio."
        if not email or not EMAIL_RE.match(email):
            errors["email"] = "Email inválido."
        if not phone or not PHONE_RE.match(phone):
            errors["phone"] = "Teléfono inválido."
        if not terms:
            errors["terms"] = "Debes aceptar Términos y Condiciones."
        if room_type not in ("normal", "premium"):
            errors["room_type"] = "Tipo de habitación inválido."

        d_in, d_out, date_err = self._validate_dates(checkin, checkout)
        if date_err:
            errors["dates"] = date_err

        motel = None
        if motel_id.isdigit():
            motel = request.env["motel.motel"].sudo().browse(int(motel_id))
            if not motel.exists():
                errors["motel_id"] = "Motel inválido."
        else:
            errors["motel_id"] = "Motel inválido."

        if errors:
            return request.render(
                "motel_availability.reserve_page",
                {
                    "motel": motel,
                    "room_type": room_type,
                    "checkin": checkin,
                    "checkout": checkout,
                    "login_url": "/web/login",
                    "errors": errors,
                    "prefill": {"first": first, "last": last, "email": email, "phone": phone, "terms": terms},
                },
            )

        # --- Creación (CA-03) con savepoint ---
        try:
            with request.env.cr.savepoint():
                motel_id_int = int(motel_id)

                # 1) Habitación libre real
                room = self._find_available_room(motel_id_int, room_type, d_in, d_out)
                if not room:
                    return request.render(
                        "motel_availability.reserve_error",
                        {
                            "message": "No hay habitaciones disponibles para ese rango. Cambia fechas o tipo.",
                            "attempt_uuid": attempt_uuid,
                        },
                    )

                # 2) Partner (guest)
                partner = self._get_or_create_partner(first, last, email, phone)

                # 3) Sales Order
                product = self._ensure_reservation_product()
                nights = (d_out - d_in).days

                rt = request.env["motel.room.type"].sudo().search([("code", "=", room_type)], limit=1)
                price_unit = float(rt.price_per_night or 0.0) if rt else 0.0

                so = request.env["sale.order"].sudo().create(
                    {
                        "partner_id": partner.id,
                        "origin": attempt_uuid,
                        "note": f"Reserva {room.motel_id.name} / Habitación {room.name} / {checkin} → {checkout}",
                        "order_line": [
                            (
                                0,
                                0,
                                {
                                    "product_id": product.id,
                                    "name": f"Habitación {room_type.upper()} - {room.motel_id.name} ({room.name}) {checkin}→{checkout}",
                                    "product_uom_qty": nights,
                                    "price_unit": price_unit,
                                },
                            )
                        ],
                    }
                )

                # 4) Reserva
                reservation = request.env["motel.reservation"].sudo().create(
                    {
                        "attempt_uuid": attempt_uuid,
                        "room_id": room.id,
                        "checkin_date": d_in,
                        "checkout_date": d_out,
                        "state": "confirmed",
                        "guest_first_name": first,
                        "guest_last_name": last,
                        "guest_email": email,
                        "guest_phone": phone,
                        "terms_accepted": True,
                        "partner_id": partner.id,
                        "sale_order_id": so.id,
                    }
                )

            # ⚠️ IMPORTANTE: esto requiere que exista reservation.reference
            return request.redirect(f"/motels/confirmation/{reservation.reference}")

        except Exception as e:
            _logger.exception("Error confirmando reserva (attempt=%s): %s", attempt_uuid, e)
            return request.render(
                "motel_availability.reserve_error",
                {"message": "No se pudo confirmar la reserva. Intenta nuevamente.", "attempt_uuid": attempt_uuid},
            )

    # ==========================================================
    # HU-02: Confirmación (pantalla)
    # ==========================================================
    @http.route("/motels/confirmation/<string:reference>", type="http", auth="public", website=True, sitemap=False)
    def confirmation_page(self, reference, **kw):
        Res = request.env["motel.reservation"].sudo()
        reservation = Res.search([("reference", "=", reference)], limit=1)
        if not reservation:
            return request.not_found()
        return request.render("motel_availability.confirmation_page", {"reservation": reservation})
