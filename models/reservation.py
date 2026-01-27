# models/reservation.py
import uuid
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class MotelReservation(models.Model):
    _name = "motel.reservation"
    _description = "Room Reservation"
    _order = "checkin_date desc, id desc"

    PRICE_PER_DAY = {"normal": 100.0, "premium": 200.0}
    LONG_STAY_MIN_DAYS = 6
    LONG_STAY_MULTIPLIER = 1.5
    PET_FEE = 25.0          
    WIFI_FEE_PER_DAY = 2.0  

    reference = fields.Char(
        string="Reference",
        readonly=True,
        copy=False,
        index=True,
        default="New",
    )
    attempt_uuid = fields.Char(string="Attempt ID", copy=False, index=True)

    room_id = fields.Many2one("motel.room", string="Room", required=True, ondelete="restrict")
    motel_id = fields.Many2one(related="room_id.motel_id", store=True, readonly=True)

    checkin_date = fields.Date(string="Check-in", required=True)
    checkout_date = fields.Date(string="Check-out", required=True)
    has_pets = fields.Boolean(string="Has Pets", default=False)
    wants_wifi = fields.Boolean(string="Wants Wi-Fi", default=False)

    state = fields.Selection(
        [("draft", "Draft"), ("confirmed", "Confirmed"), ("cancelled", "Cancelled")],
        default="draft",
        required=True,
    )

    partner_id = fields.Many2one("res.partner", string="Customer", ondelete="set null")
    guest_first_name = fields.Char(string="Guest First Name")
    guest_last_name = fields.Char(string="Guest Last Name")
    guest_email = fields.Char(string="Guest Email")
    guest_phone = fields.Char(string="Guest Phone")
    terms_accepted = fields.Boolean(string="Terms Accepted", default=False)


    sale_order_id = fields.Many2one("sale.order", string="Sale Order", ondelete="set null")

    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        required=True,
        default=lambda self: self.env.company.currency_id.id,
    )

    room_type_code = fields.Selection(
        [("normal", "Normal"), ("premium", "Premium")],
        string="Room Type",
        required=True,
        default="normal",
    )

    nights = fields.Integer(
        string="Nights",
        compute="_compute_pricing",
        store=True,
        readonly=True,
    )

    base_price_per_day = fields.Float(
        string="Base Price / Day",
        compute="_compute_pricing",
        store=True,
        readonly=True,
    )

    pet_fee = fields.Monetary(
        string="Pet Fee",
        currency_field="currency_id",
        compute="_compute_pricing",
        store=True,
        readonly=True,
    )

    wifi_fee_total = fields.Monetary(
        string="Wi-Fi Total",
        currency_field="currency_id",
        compute="_compute_pricing",
        store=True,
        readonly=True,
    )

    base_total = fields.Monetary(
        string="Base Total",
        currency_field="currency_id",
        compute="_compute_pricing",
        store=True,
        readonly=True,
    )

    surcharge_applied = fields.Boolean(
        string="Long-stay Surcharge Applied",
        compute="_compute_pricing",
        store=True,
        readonly=True,
    )

    final_total = fields.Monetary(
        string="Final Total",
        currency_field="currency_id",
        compute="_compute_pricing",
        store=True,
        readonly=True,
    )

    channel = fields.Selection(
        [("web", "Web"), ("reception", "Reception")],
        string="Channel",
        required=True,
        default="web",
        index=True,
    )

    payment_method = fields.Selection(
        [("advance", "Pay in advance"), ("on_site", "Pay on site")],
        string="Payment Method",
        required=True,
        default="advance",
        index=True,
    )

    payment_state = fields.Selection(
        [
            ("pending", "Pending payment"),   # recepción / on_site
            ("paid", "Paid"),                 # web pago ok / recepción cobrada
            ("failed", "Payment failed"),     # web pago fallido
        ],
        string="Payment Status",
        required=True,
        default="pending",  # web todavía no pagó hasta que inicie pago
        index=True,
    )

    payment_reference = fields.Char(string="Payment Reference", copy=False, index=True)
    payment_correlation_id = fields.Char(string="Correlation ID", copy=False, index=True)
    paid_at = fields.Datetime(string="Paid At", readonly=True, copy=False)
    paid_by_user_id = fields.Many2one("res.users", string="Paid By", readonly=True, copy=False)

    @api.depends("room_type_code", "checkin_date", "checkout_date", "has_pets", "wants_wifi")
    def _compute_pricing(self):
        """
        - Normal: 100/día
        - Premium: 200/día
        - >=6 noches => subtotal * 1.5
        - Mascotas: +25 fijo
        - Wi-Fi: +2 por noche
        """
        for rec in self:
            # Defaults seguros (si algo falta, no quedan valores viejos)
            rec.nights = 0
            rec.base_price_per_day = 0.0
            rec.base_total = 0.0
            rec.surcharge_applied = False
            rec.pet_fee = 0.0
            rec.wifi_fee_total = 0.0
            rec.final_total = 0.0

            if not rec.checkin_date or not rec.checkout_date:
                continue

            nights = (rec.checkout_date - rec.checkin_date).days
            if nights <= 0:
                continue

            if rec.room_type_code not in rec.PRICE_PER_DAY:
                continue

            base_per_day = rec.PRICE_PER_DAY[rec.room_type_code]
            base_total = base_per_day * nights

            surcharge = nights >= rec.LONG_STAY_MIN_DAYS
            subtotal = base_total * rec.LONG_STAY_MULTIPLIER if surcharge else base_total

            pet_fee = rec.PET_FEE if rec.has_pets else 0.0
            wifi_total = (rec.WIFI_FEE_PER_DAY * nights) if rec.wants_wifi else 0.0

            rec.nights = nights
            rec.base_price_per_day = base_per_day
            rec.base_total = base_total
            rec.surcharge_applied = surcharge
            rec.pet_fee = pet_fee
            rec.wifi_fee_total = wifi_total
            rec.final_total = subtotal + pet_fee + wifi_total
            
    @api.constrains("checkin_date", "checkout_date")
    def _check_dates(self):
        for rec in self:
            if rec.checkin_date and rec.checkout_date and rec.checkout_date <= rec.checkin_date:
                raise ValidationError("La fecha de salida debe ser posterior a la de entrada.")

    @api.constrains("checkin_date")
    def _check_not_past(self):
        for rec in self:
            if rec.checkin_date and rec.checkin_date < fields.Date.context_today(rec):
                raise ValidationError("No se permiten fechas en el pasado.")

    @api.constrains("room_type_code")
    def _check_room_type_code(self):
        for rec in self:
            if rec.room_type_code and rec.room_type_code not in ("normal", "premium"):
                raise ValidationError("Tipo de habitación inválido.")

    @api.constrains("nights", "checkin_date", "checkout_date")
    def _check_nights_match_dates(self):
        for rec in self:
            if rec.checkin_date and rec.checkout_date:
                expected = (rec.checkout_date - rec.checkin_date).days
                if expected <= 0:
                    raise ValidationError("Rango de fechas inválido.")
                # nights es compute+store; si hay inconsistencia, es señal de corrupción
                if rec.nights != expected:
                    raise ValidationError("El número de noches no coincide con las fechas.")

    @api.constrains("channel", "payment_method")
    def _check_channel_payment_rules(self):
        for rec in self:
            if rec.channel == "web" and rec.payment_method != "advance":
                raise ValidationError("En la web solo se permite pago anticipado.")

    @api.onchange("channel", "payment_method")
    def _onchange_channel_payment(self):
        for rec in self:
            if rec.channel == "web":
                rec.payment_method = "advance"
                # en web puede ser pending/failed según pasarela
            elif rec.channel == "reception":
                if rec.payment_method == "on_site":
                    # En recepción, en sitio inicia pendiente
                    if rec.payment_state in (False, "failed"):
                        rec.payment_state = "pending"

    def action_mark_paid(self, reference=None, correlation_id=None, by_user=None):
        """Marca pagado + auditoría (CA-04/05)."""
        self.ensure_one()
        self.write({
            "payment_state": "paid",
            "payment_reference": reference or self.payment_reference,
            "payment_correlation_id": correlation_id or self.payment_correlation_id,
            "paid_at": fields.Datetime.now(),
            "paid_by_user_id": (by_user or self.env.user).id,
        })
        # Si venía de web, ahora sí confirmamos la reserva (CA-02)
        if self.state != "confirmed":
            self.write({"state": "confirmed"})

    def action_mark_payment_failed(self, correlation_id=None):
        self.ensure_one()
        self.write({
            "payment_state": "failed",
            "payment_correlation_id": correlation_id or self.payment_correlation_id,
        })

    def action_register_on_site_payment(self):
        """Recepción cobra y marca pagado (CA-03/04/05)."""
        for rec in self:
            if rec.channel != "reception" or rec.payment_method != "on_site":
                raise ValidationError("Solo aplica a reservas de recepción con pago en sitio.")
            if rec.payment_state in ("paid",):
                continue

            correlation_id = rec.payment_correlation_id or f"REC-{uuid.uuid4().hex[:12].upper()}"
            reference = rec.payment_reference or f"REC-CASH-{rec.reference}"

            rec.write({
                "payment_state": "paid",
                "payment_reference": reference,
                "payment_correlation_id": correlation_id,
                "paid_at": fields.Datetime.now(),
                "paid_by_user_id": self.env.user.id,
            })

            # Confirmar la reserva si aún no lo está
            if rec.state != "confirmed":
                rec.state = "confirmed"

            if rec.sale_order_id:
                if rec.sale_order_id.state in ("draft", "sent"):
                    rec.sale_order_id.sudo().action_confirm()
                elif rec.sale_order_id.state == "cancel":
                    raise ValidationError("La orden de venta está cancelada. No se puede confirmar automáticamente.")
            else:
                raise ValidationError("No hay Orden de Venta vinculada a esta reserva (sale_order_id vacío).")

            self.env["motel.payment.log"].sudo().create({
                "reservation_id": rec.id,
                "channel": "reception",
                "action": "reception_collect",
                "state": "paid",
                "correlation_id": correlation_id,
                "provider_reference": reference,
                "performed_by_user_id": self.env.user.id,
                "note": "Cobro registrado en recepción.",
            })

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("reference", "New") == "New":
                vals["reference"] = self.env["ir.sequence"].next_by_code("motel.reservation") or "RES"
        return super().create(vals_list)
