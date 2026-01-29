# controllers/main.py
import json
import logging
import re
import uuid
from datetime import timedelta

from odoo import http, fields
from odoo.http import request

_logger = logging.getLogger(__name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^[0-9+\-\s().]{7,20}$")


class MotelAvailabilityController(http.Controller):
    """
    HU-01:
      - /motels (website)
      - /motels/availability_http (HTTP GET JSON para fetch)
      - /motels/availability (JSON-RPC opcional)

    HU-02:
      - /motels/reserve (GET)
      - /motels/confirm (POST)
      - /motels/confirmation/<reference> (GET)

    HU-04:
      - normal: 100/día
      - premium: 200/día
      - >= 6 noches => +50% sobre total base
      - backend única fuente
    """

    PRICE_PER_DAY = {"normal": 100.0, "premium": 200.0}
    LONG_STAY_MIN_DAYS = 6
    LONG_STAY_MULTIPLIER = 1.5

    
    # Funciones complementarias

    def _today(self):
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

    def _compute_price(self, room_type_code, d_in, d_out, has_pets=False, wants_wifi=False):
        if room_type_code not in ("normal", "premium"):
            return None, "Tipo de habitación inválido."

        nights = (d_out - d_in).days
        if nights <= 0:
            return None, "Rango de fechas inválido."

        base_per_day = self.PRICE_PER_DAY[room_type_code]
        base_total = base_per_day * nights

        surcharge = nights >= self.LONG_STAY_MIN_DAYS
        subtotal = base_total * self.LONG_STAY_MULTIPLIER if surcharge else base_total

        pet_fee = 25.0 if has_pets else 0.0
        wifi_per_day = 2.0 if wants_wifi else 0.0
        wifi_total = wifi_per_day * nights

        final_total = subtotal + pet_fee + wifi_total

        return {
            "room_type": room_type_code,
            "nights": nights,
            "base_per_day": base_per_day,
            "base_total": base_total,
            "surcharge_applied": surcharge,
            "subtotal_after_surcharge": subtotal,
            "pet_fee": pet_fee,
            "wifi_per_day": wifi_per_day,
            "wifi_total": wifi_total,
            "final_total": final_total,
            "has_pets": bool(has_pets),
            "wants_wifi": bool(wants_wifi),
        }, None

    def _get_room_types(self):
        RoomType = request.env["motel.room.type"].sudo()
        rtypes = RoomType.search([("code", "in", ("normal", "premium"))])
        return rtypes or RoomType.search([])

    def _compute_availability_payload(self, d_in, d_out):
        Motel = request.env["motel.motel"].sudo()
        Room = request.env["motel.room"].sudo()
        Res = request.env["motel.reservation"].sudo()

        motels = Motel.search([], order="id asc", limit=4)
        rtypes = self._get_room_types()
        nights = (d_out - d_in).days

        # totales por motel y tipo
        totals = Room.read_group(
            domain=[("motel_id", "in", motels.ids), ("active", "=", True)],
            fields=["motel_id", "room_type_id"],
            groupby=["motel_id", "room_type_id"],
            lazy=False,
        )
        total_map = {
            (r["motel_id"][0], r["room_type_id"][0]): r["__count"]
            for r in totals
            if r.get("motel_id") and r.get("room_type_id")
        }

        occupied = Res.read_group(
            domain=[
                ("state", "!=", "cancelled"),
                ("payment_state", "in", ("pending", "paid")),
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
            occ_by_type = {
                (r["motel_id"][0], r["room_type_id"][0]): r["__count"]
                for r in occ2
                if r.get("motel_id") and r.get("room_type_id")
            }

        code_by_type = {rt.id: (rt.code or "").strip() for rt in rtypes}

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

            payload.append({
                "id": m.id,
                "name": m.name,
                "location": m.display_address(),
                "room_total": m.room_total,
                "nights": nights,
                "normal": normal,
                "premium": premium,
                "has_availability": (normal["available"] + premium["available"]) > 0,
            })

        return payload
    

    def _get_or_create_partner(self, first, last, email, phone):
        """Crea/reutiliza res.partner por email (contacto)."""
        Partner = request.env["res.partner"].sudo()
        email_norm = (email or "").strip().lower()
        full_name = f"{first} {last}".strip()

        if not email_norm:
            # fallback muy raro (pero evita crash)
            return Partner.create({"name": full_name or "Guest"})

        partner = Partner.search([("email", "=", email_norm)], limit=1)
        if partner:
            vals = {}
            if full_name and (not partner.name or not partner.name.strip()):
                vals["name"] = full_name
            if phone and (not partner.phone or not partner.phone.strip()):
                vals["phone"] = phone
            if vals:
                partner.write(vals)
            return partner

        return Partner.create({
            "name": full_name or email_norm,
            "email": email_norm,
            "phone": phone,
            "company_type": "person",
        })

    def _ensure_reservation_product(self):
        """
        Producto servicio estable para líneas de Sale Order.
        Usamos product.template y devolvemos la variante.
        """
        Template = request.env["product.template"].sudo()
        tmpl = Template.search([("default_code", "=", "MOTEL_ROOM_NIGHT")], limit=1)
        if not tmpl:
            tmpl = Template.create({
                "name": "Motel Room Night",
                "default_code": "MOTEL_ROOM_NIGHT",
                "type": "service",
                "sale_ok": True,
                "purchase_ok": False,
            })
        return tmpl.product_variant_id

    def _create_sale_order_for_reservation(self, partner, room, room_type, checkin, checkout, pricing, attempt_uuid):
        """
        Crea SO con:
          - línea base: nights * base_per_day
          - línea recargo (+50%) si aplica (una línea separada para auditoría)
        """
        SaleOrder = request.env["sale.order"].sudo()
        product = self._ensure_reservation_product()

        nights = int(pricing["nights"])
        base_per_day = float(pricing["base_per_day"])
        base_total = float(pricing["base_total"])
        surcharge_applied = bool(pricing["surcharge_applied"])

        order_lines = [
            (0, 0, {
                "product_id": product.id,
                "name": f"Habitación {room_type.upper()} - {room.motel_id.name} ({room.name}) {checkin}→{checkout}",
                "product_uom_qty": nights,
                "price_unit": base_per_day,
            })
        ]

        if surcharge_applied:
            surcharge_amount = base_total * 0.5
            order_lines.append(
                (0, 0, {
                    "product_id": product.id,
                    "name": "Recargo estancia larga (+50%)",
                    "product_uom_qty": 1,
                    "price_unit": surcharge_amount,
                })
            )

        so = SaleOrder.create({
            "partner_id": partner.id,
            "origin": attempt_uuid,
            "note": f"Reserva {room.motel_id.name} / {room.name} / {checkin} → {checkout} / {room_type}",
            "order_line": order_lines,
        })

        return so


    @http.route("/motels", type="http", auth="public", website=True, sitemap=True)
    def motels_page(self, **kw):
        motels = request.env["motel.motel"].sudo().search([], order="id asc", limit=4)
        today = fields.Date.to_string(self._today())
        return request.render("motel.motels_page", {"motels": motels, "today": today})


    @http.route("/motels/availability_http", type="http", auth="public", methods=["GET"], csrf=False, website=True)
    def motels_availability_http(self, checkin=None, checkout=None, **kw):
        d_in, d_out, err = self._validate_dates(checkin, checkout)
        if err:
            return request.make_response(
                json.dumps({"error": err}),
                headers=[("Content-Type", "application/json")],
                status=400,
            )
        return request.make_response(
            json.dumps({"motels": self._compute_availability_payload(d_in, d_out)}),
            headers=[("Content-Type", "application/json")],
            status=200,
        )

    @http.route("/motels/availability", type="json", auth="public", website=True)
    def motels_availability(self, checkin, checkout):
        d_in, d_out, err = self._validate_dates(checkin, checkout)
        if err:
            return {"error": err}
        return {"motels": self._compute_availability_payload(d_in, d_out)}

    @http.route("/motels/reserve", type="http", auth="public", website=True, sitemap=False)
    def reserve_page(self, motel_id=None, room_type=None, checkin=None, checkout=None, **kw):
        Motel = request.env["motel.motel"].sudo()

        # 1) Validar motel_id
        motel = Motel.browse(int(motel_id)) if motel_id and str(motel_id).isdigit() else Motel.browse([])
        if motel_id and (not motel or not motel.exists()):
            return request.not_found()

        # 2) Defaults de fechas
        today = self._today()
        checkin = (checkin or fields.Date.to_string(today)).strip()
        checkout = (checkout or fields.Date.to_string(today + timedelta(days=1))).strip()

        # 3) Normalizar room_type con default seguro
        room_type = (room_type or "").strip().lower()
        if room_type not in ("normal", "premium"):
            room_type = "normal"

        # 4) Validar fechas + calcular pricing
        d_in, d_out, err = self._validate_dates(checkin, checkout)

        has_pets = (kw.get("has_pets") in ("1", "true", "on", "yes"))
        wants_wifi = (kw.get("wants_wifi") in ("1", "true", "on", "yes"))

        pricing = None
        if not err:
            pricing, perr = self._compute_price(room_type, d_in, d_out, has_pets=has_pets, wants_wifi=wants_wifi)
            if perr:
                err = perr

        # 5) Render
        # Nota: devolvemos pricing aunque haya erroes del formulario (en este GET no hay),
        # pero si err existe, el template ya mostrará el warning.
        return request.render("motel.reserve_page", {
            "motel": motel,
            "room_type": room_type,
            "checkin": checkin,
            "checkout": checkout,
            "pricing": pricing,
            "has_pets": has_pets, 
            "wants_wifi": wants_wifi,
            "login_url": "/web/login",
            "errors": {},   # en GET no hay errors de form
            "prefill": {"has_pets": has_pets, "wants_wifi": wants_wifi},
        })


    def _find_available_room(self, motel_id, room_type_code, d_in, d_out):
        RoomType = request.env["motel.room.type"].sudo()
        Room = request.env["motel.room"].sudo()
        Res = request.env["motel.reservation"].sudo()

        rt = RoomType.search([("code", "=", room_type_code)], limit=1)
        if not rt:
            return None

        rooms = Room.search([
            ("motel_id", "=", motel_id),
            ("room_type_id", "=", rt.id),
            ("active", "=", True),
        ], order="id asc")
        if not rooms:
            return None

        occupied = Res.search([
            ("state", "!=", "cancelled"),
            ("payment_state", "in", ("pending", "paid")),
            ("room_id", "in", rooms.ids),
            ("checkin_date", "<", d_out),
            ("checkout_date", ">", d_in),
        ]).mapped("room_id")

        free_rooms = rooms - occupied
        return free_rooms[:1] if free_rooms else None

   
    @http.route("/motels/confirm", type="http", auth="public", website=True, methods=["POST"], csrf=True)
    def confirm_reservation(self, **post):
        attempt_uuid = f"ATT-{uuid.uuid4().hex[:10].upper()}"

        first = (post.get("first_name") or "").strip()
        last = (post.get("last_name") or "").strip()
        email = (post.get("email") or "").strip().lower()
        phone = (post.get("phone") or "").strip()
        terms = post.get("terms") == "on"
        has_pets = post.get("has_pets") == "on"
        wants_wifi = post.get("wants_wifi") == "on"

        motel_id = (post.get("motel_id") or "").strip()
        room_type = (post.get("room_type") or "").strip()
        checkin = (post.get("checkin") or "").strip()
        checkout = (post.get("checkout") or "").strip()

        payment_method = (post.get("payment_method") or "advance").strip()
        # CA-01: web solo anticipado
        if payment_method != "advance":
            return request.render("motel.reserve_error", {
                "message": "En la web solo se permite pago anticipado.",
                "attempt_uuid": attempt_uuid,
            })

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

        pricing = None
        if d_in and d_out and room_type in ("normal", "premium"):
            pricing, perr = self._compute_price(room_type, d_in, d_out, has_pets=has_pets, wants_wifi=wants_wifi)
            if perr:
                errors["pricing"] = perr
                pricing = None

        if errors:
            return request.render("motel.reserve_page", {
                "motel": motel,
                "room_type": room_type,
                "checkin": checkin,
                "checkout": checkout,
                "pricing": pricing,
                "login_url": "/web/login",
                "errors": errors,
                "prefill": {"first": first, "last": last, "email": email, "phone": phone, "terms": terms , "has_pets": has_pets, "wants_wifi": wants_wifi},
            })

        try:
            with request.env.cr.savepoint():
                room = self._find_available_room(int(motel_id), room_type, d_in, d_out)
                if not room:
                    return request.render("motel.reserve_error", {
                        "message": "No hay habitaciones disponibles para ese rango. Cambia fechas o tipo.",
                        "attempt_uuid": attempt_uuid,
                    })

                # 1) crear Contacto (partner)
                partner = self._get_or_create_partner(first, last, email, phone)

                # 2) crear Orden de venta
                so = self._create_sale_order_for_reservation(
                    partner=partner,
                    room=room,
                    room_type=room_type,
                    checkin=checkin,
                    checkout=checkout,
                    pricing=pricing,
                    attempt_uuid=attempt_uuid,
                )
                correlation_id = f"WEB-{uuid.uuid4().hex[:12].upper()}"

                # 3) Reserva vinculada a partner + SO
                reservation = request.env["motel.reservation"].sudo().create({
                    "attempt_uuid": attempt_uuid,
                    "room_id": room.id,
                    "checkin_date": d_in,
                    "checkout_date": d_out,
                    "state": "draft",
                    "room_type_code": room_type,

                    "partner_id": partner.id,
                    "sale_order_id": so.id,

                    "guest_first_name": first,
                    "guest_last_name": last,
                    "guest_email": email,
                    "guest_phone": phone,
                    "terms_accepted": True,
                    "has_pets": has_pets,
                    "wants_wifi": wants_wifi,
                    "channel": "web",
                    "payment_method": "advance",
                    "payment_state": "pending",
                    "payment_correlation_id": correlation_id,
                })

                request.env["motel.payment.log"].sudo().create({
                "reservation_id": reservation.id,
                "channel": "web",
                "action": "web_tx",
                "state": "pending",
                "correlation_id": correlation_id,
                "performed_by_user_id": request.env.user.id if request.env.user else False,
                "note": "Checkout web iniciado; pendiente de pago anticipado.",
                })

            return request.redirect(f"/motels/pay/{reservation.attempt_uuid}")
            

        except Exception as e:
            _logger.exception("Error confirmando reserva (attempt=%s)", attempt_uuid)
            return request.render("motel.reserve_error", {
                "message": f"No se pudo confirmar la reserva: {e}",
                "attempt_uuid": attempt_uuid,
            })


    @http.route("/motels/pay/<string:attempt_uuid>", type="http", auth="public", website=True, sitemap=False)
    def pay_page(self, attempt_uuid, **kw):
        reservation = request.env["motel.reservation"].sudo().search([("attempt_uuid", "=", attempt_uuid)], limit=1)
        if not reservation:
            return request.not_found()
            # CA-01 bloqueo duro
        if reservation.channel == "web" and reservation.payment_method != "advance":
            return request.render("motel.reserve_error", {
                "message": "En la web solo se permite pago anticipado.",
                "attempt_uuid": attempt_uuid,
            })

        return request.render("motel.payment_page", {"reservation": reservation})

    @http.route("/motels/pay/submit", type="http", auth="public", website=True, methods=["POST"], csrf=True)
    def pay_submit(self, **post):
        attempt_uuid = post.get("attempt_uuid")
        outcome = (post.get("outcome") or "success").strip()  # demo: success | fail

        reservation = request.env["motel.reservation"].sudo().search([("attempt_uuid", "=", attempt_uuid)], limit=1)
        if not reservation:
            return request.not_found()

        if reservation.channel == "web" and reservation.payment_method != "advance":
            return request.render("motel.reserve_error", {
                "message": "En la web solo se permite pago anticipado.",
                "attempt_uuid": attempt_uuid,
            })

        correlation_id = reservation.payment_correlation_id or f"WEB-{uuid.uuid4().hex[:12].upper()}"
        gateway_ref = f"GW-{uuid.uuid4().hex[:10].upper()}"

        if outcome == "success":
            reservation.action_mark_paid(reference=gateway_ref, correlation_id=correlation_id, by_user=request.env.user)

            request.env["motel.payment.log"].sudo().create({
                "reservation_id": reservation.id,
                "channel": "web",
                "action": "web_tx",
                "state": "paid",
                "correlation_id": correlation_id,
                "provider_reference": gateway_ref,
                "performed_by_user_id": request.env.user.id if request.env.user else False,
                "note": "Pago anticipado web exitoso.",
            })
            return request.redirect(f"/motels/confirmation/{reservation.reference}")

        # fail
        reservation.action_mark_payment_failed(correlation_id=correlation_id)
        request.env["motel.payment.log"].sudo().create({
            "reservation_id": reservation.id,
            "channel": "web",
            "action": "web_tx",
            "state": "failed",
            "correlation_id": correlation_id,
            "provider_reference": "",
            "performed_by_user_id": request.env.user.id if request.env.user else False,
            "note": "Pago anticipado web fallido (simulado).",
        })
        return request.redirect(f"/motels/pay_failed/{reservation.attempt_uuid}")

    @http.route("/motels/pay/reception", type="http", auth="public", website=True, methods=["POST"], csrf=True)
    def pay_in_reception(self, **post):
        attempt_uuid = post.get("attempt_uuid")
        reservation = request.env["motel.reservation"].sudo().search([("attempt_uuid", "=", attempt_uuid)], limit=1)
        if not reservation:
            return request.not_found()

        # Cambia la reserva para pago en sitio (sin confirmar SO)
        correlation_id = reservation.payment_correlation_id or f"WEB-{uuid.uuid4().hex[:12].upper()}"
        reservation.write({
            "channel": "reception",           # si quieres reflejar el canal operativo
            "payment_method": "on_site",
            "payment_state": "pending",
            "payment_correlation_id": correlation_id,
        })

        PaymentLog = request.env["motel.payment.log"].sudo()

        web_log = PaymentLog.search([
            ("reservation_id", "=", reservation.id),
            ("action", "=", "web_tx"),
            ("state", "=", "pending"),
            ("correlation_id", "=", correlation_id),
        ], limit=1, order="id desc")

        note_msg = "Cliente eligió pagar en recepción desde la web. Reserva queda pendiente (sin cobro)."

        if web_log:
            web_log.write({"note": note_msg})
        else:
            PaymentLog.create({
                "reservation_id": reservation.id,
                "channel": "web",
                "action": "web_tx",
                "state": "pending",
                "correlation_id": correlation_id,
                "performed_by_user_id": request.env.user.id if request.env.user else False,
                "note": note_msg,
            })

        return request.redirect(f"/motels/pending/{reservation.reference}")




    @http.route("/motels/pending/<string:reference>", type="http", auth="public", website=True, sitemap=False)
    def pending_page(self, reference, **kw):
        reservation = request.env["motel.reservation"].sudo().search([("reference", "=", reference)], limit=1)
        if not reservation:
            return request.not_found()
        return request.render("motel.pending_payment_page", {"reservation": reservation})


    
    @http.route("/motels/pay_failed/<string:attempt_uuid>", type="http", auth="public", website=True, sitemap=False)
    def pay_failed(self, attempt_uuid, **kw):
        reservation = request.env["motel.reservation"].sudo().search([("attempt_uuid", "=", attempt_uuid)], limit=1)
        if not reservation:
            return request.not_found()
        return request.render("motel.payment_failed_page", {"reservation": reservation})


    @http.route("/motels/confirmation/<string:reference>", type="http", auth="public", website=True, sitemap=False)
    def confirmation_page(self, reference, **kw):
        reservation = request.env["motel.reservation"].sudo().search([("reference", "=", reference)], limit=1)
        if not reservation:
            return request.not_found()
        return request.render("motel.confirmation_page", {"reservation": reservation})


    # ------------------------------------------------------------
    # HU-05: Cancelaciones y reembolsos (web) - SEGURO (token + email)
    #   - GET  /motels/cancel/<attempt_uuid>         -> muestra quote + pide email
    #   - POST /motels/cancel/confirm                -> valida email + ejecuta cancelación
    #   - GET  /motels/cancelled/<attempt_uuid>      -> página final
    # ------------------------------------------------------------

    def _get_reservation_by_attempt_or_404(self, attempt_uuid):
        reservation = request.env["motel.reservation"].sudo().search(
            [("attempt_uuid", "=", attempt_uuid)],
            limit=1
        )
        return reservation if reservation else None

    @http.route("/motels/cancel/<string:attempt_uuid>", type="http", auth="public",
                website=True, sitemap=False, methods=["GET"])
    def cancel_page(self, attempt_uuid, **kw):
        reservation = self._get_reservation_by_attempt_or_404(attempt_uuid)
        if not reservation:
            return request.not_found()

        if reservation.state == "cancelled":
            return request.redirect(f"/motels/cancelled/{reservation.attempt_uuid}")

        # Quote (CA-02/CA-03)
        try:
            quote = reservation.get_cancellation_quote()
        except Exception as e:
            _logger.exception("Error calculando quote de cancelación (attempt=%s)", attempt_uuid)
            return request.render("motel.reserve_error", {
                "message": f"No se pudo calcular el reembolso: {e}",
                "attempt_uuid": reservation.attempt_uuid or "",
            })

        # Email opcional prellenado desde querystring (pero NO lo validamos aquí)
        email_prefill = (kw.get("email") or "").strip().lower()

        return request.render("motel.cancel_page", {
            "reservation": reservation,
            "quote": quote,
            "email_prefill": email_prefill,
        })

    @http.route("/motels/cancel/confirm", type="http", auth="public",
                website=True, methods=["POST"], csrf=True)
    def cancel_confirm(self, **post):
        attempt_uuid = (post.get("attempt_uuid") or "").strip()
        email = (post.get("email") or "").strip().lower()
        confirm = (post.get("confirm") or "").strip()

        if not attempt_uuid:
            return request.not_found()

        reservation = self._get_reservation_by_attempt_or_404(attempt_uuid)
        if not reservation:
            return request.not_found()

        # Anti-cancelación por “adivinar token”: además exigimos email match
        expected_email = (reservation.guest_email or "").strip().lower()
        if not email or email != expected_email:
            # Re-render de la página con error (sin revelar demasiado)
            try:
                quote = reservation.get_cancellation_quote()
            except Exception:
                quote = {}
            return request.render("motel.cancel_page", {
                "reservation": reservation,
                "quote": quote,
                "email_prefill": email,
                "error": "El email no coincide con el de la reserva.",
            })

        if confirm.lower() not in ("yes", "true", "1", "on"):
            return request.redirect(f"/motels/cancel/{reservation.attempt_uuid}")

        # Recalcular quote en servidor por seguridad (evita manipulación)
        try:
            _ = reservation.get_cancellation_quote()
        except Exception as e:
            _logger.exception("Error recalculando quote de cancelación (attempt=%s)", attempt_uuid)
            return request.render("motel.reserve_error", {
                "message": f"No se pudo recalcular el reembolso: {e}",
                "attempt_uuid": reservation.attempt_uuid or "",
            })

        # Ejecutar cancelación (CA-04/CA-05/CA-06)
        try:
            reservation.action_cancel_with_policy(channel="web")
        except Exception as e:
            _logger.exception("Error ejecutando cancelación (attempt=%s)", attempt_uuid)
            return request.render("motel.reserve_error", {
                "message": f"No se pudo cancelar la reserva: {e}",
                "attempt_uuid": reservation.attempt_uuid or "",
            })

        return request.redirect(f"/motels/cancelled/{reservation.attempt_uuid}")

    @http.route("/motels/cancelled/<string:attempt_uuid>", type="http", auth="public",
                website=True, sitemap=False, methods=["GET"])
    def cancelled_page(self, attempt_uuid, **kw):
        reservation = self._get_reservation_by_attempt_or_404(attempt_uuid)
        if not reservation:
            return request.not_found()

        return request.render("motel.cancelled_page", {
            "reservation": reservation,
        })
