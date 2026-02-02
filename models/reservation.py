# models/reservation.py
import uuid
from datetime import datetime, time

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError


class MotelReservation(models.Model):
    _name = "motel.reservation"
    _description = "Room Reservation"
    _order = "checkin_date desc, id desc"

    # ----------------------------
    # Pricing rules (HU-04)
    # ----------------------------
    PRICE_PER_DAY = {"normal": 100.0, "premium": 200.0}
    LONG_STAY_MIN_DAYS = 6
    LONG_STAY_MULTIPLIER = 1.5
    PET_FEE = 25.0
    WIFI_FEE_PER_DAY = 2.0

    # ----------------------------
    # Core
    # ----------------------------
    reference = fields.Char(string="Reference", readonly=True, copy=False, index=True, default="New")
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
        index=True,
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

    # ----------------------------
    # Pricing computed fields (stored)
    # ----------------------------
    nights = fields.Integer(string="Nights", compute="_compute_pricing", store=True, readonly=True)
    base_price_per_day = fields.Float(string="Base Price / Day", compute="_compute_pricing", store=True, readonly=True)
    pet_fee = fields.Monetary(string="Pet Fee", currency_field="currency_id", compute="_compute_pricing", store=True, readonly=True)
    wifi_fee_total = fields.Monetary(string="Wi-Fi Total", currency_field="currency_id", compute="_compute_pricing", store=True, readonly=True)
    base_total = fields.Monetary(string="Base Total", currency_field="currency_id", compute="_compute_pricing", store=True, readonly=True)
    surcharge_applied = fields.Boolean(string="Long-stay Surcharge Applied", compute="_compute_pricing", store=True, readonly=True)
    final_total = fields.Monetary(string="Final Total", currency_field="currency_id", compute="_compute_pricing", store=True, readonly=True)

    # ----------------------------
    # Channel & payments
    # ----------------------------
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
            ("pending", "Pending payment"),
            ("paid", "Paid"),
            ("failed", "Payment failed"),
        ],
        string="Payment Status",
        required=True,
        default="pending",
        index=True,
    )

    payment_reference = fields.Char(string="Payment Reference", copy=False, index=True)
    payment_correlation_id = fields.Char(string="Correlation ID", copy=False, index=True)
    paid_at = fields.Datetime(string="Paid At", readonly=True, copy=False)
    paid_by_user_id = fields.Many2one("res.users", string="Paid By", readonly=True, copy=False)

    amount_paid = fields.Monetary(
        string="Amount Paid",
        currency_field="currency_id",
        readonly=True,
        copy=False,
        help="Monto realmente pagado por el cliente (base para reembolso).",
    )

    # ----------------------------
    # HU-05: Cancellation & refunds (persisted audit)
    # ----------------------------
    financial_state = fields.Selection(
        [
            ("none", "No aplica"),
            ("refunded", "Reembolsado"),
            ("partial", "Parcialmente reembolsado"),
            ("non_refundable", "No reembolsable"),
            ("manual", "Reembolso manual"),
        ],
        string="Financial Status",
        default="none",
        required=True,
        index=True,
        copy=False,
    )

    cancelled_at = fields.Datetime(string="Cancelled At", readonly=True, copy=False)
    cancelled_by_user_id = fields.Many2one("res.users", string="Cancelled By", readonly=True, copy=False)
    cancelled_channel = fields.Selection(
        [("web", "Web"), ("reception", "Reception")],
        string="Cancelled Channel",
        readonly=True,
        copy=False,
    )

    refund_percentage = fields.Float(string="Refund % Applied", readonly=True, copy=False)
    refund_amount = fields.Monetary(string="Refund Amount", currency_field="currency_id", readonly=True, copy=False)
    non_refundable_amount = fields.Monetary(string="Retained Amount", currency_field="currency_id", readonly=True, copy=False)
    refund_reference = fields.Char(string="Refund Reference", readonly=True, copy=False)

    # ----------------------------
    # HU-05: Preview (before cancelling) - store=False
    # ----------------------------
    refund_quote_percentage = fields.Float(string="Refund % (Preview)", compute="_compute_refund_quote", store=False)
    refund_quote_amount = fields.Monetary(
        string="Refund Amount (Preview)",
        currency_field="currency_id",
        compute="_compute_refund_quote",
        store=False,
    )
    retained_quote_amount = fields.Monetary(
        string="Retained Amount (Preview)",
        currency_field="currency_id",
        compute="_compute_refund_quote",
        store=False,
    )
    refund_quote_message = fields.Char(string="Preview Message", compute="_compute_refund_quote", store=False)

    # ----------------------------
    # HU-05: Check-in datetime (policy)
    # ----------------------------
    checkin_datetime = fields.Datetime(
        string="Check-in DateTime",
        compute="_compute_checkin_datetime",
        store=False,
        help="Fecha/hora usada para política de cancelación (check-in).",
    )

    # ============================================================
    # Pricing compute
    # ============================================================
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
            # Defaults seguros (evita valores viejos)
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

    # ============================================================
    # Constraints & onchange
    # ============================================================
    @api.constrains("checkin_date", "checkout_date")
    def _check_dates(self):
        for rec in self:
            if rec.checkin_date and rec.checkout_date and rec.checkout_date <= rec.checkin_date:
                raise ValidationError(_("La fecha de salida debe ser posterior a la de entrada."))

    @api.constrains("checkin_date")
    def _check_not_past(self):
        for rec in self:
            if rec.checkin_date and rec.checkin_date < fields.Date.context_today(rec):
                raise ValidationError(_("No se permiten fechas en el pasado."))

    @api.constrains("room_type_code")
    def _check_room_type_code(self):
        for rec in self:
            if rec.room_type_code and rec.room_type_code not in ("normal", "premium"):
                raise ValidationError(_("Tipo de habitación inválido."))

    @api.constrains("nights", "checkin_date", "checkout_date")
    def _check_nights_match_dates(self):
        for rec in self:
            if rec.checkin_date and rec.checkout_date:
                expected = (rec.checkout_date - rec.checkin_date).days
                if expected <= 0:
                    raise ValidationError(_("Rango de fechas inválido."))
                if rec.nights != expected:
                    raise ValidationError(_("El número de noches no coincide con las fechas."))

    @api.constrains("channel", "payment_method")
    def _check_channel_payment_rules(self):
        for rec in self:
            if rec.channel == "web" and rec.payment_method != "advance":
                raise ValidationError(_("En la web solo se permite pago anticipado."))

    @api.onchange("channel", "payment_method")
    def _onchange_channel_payment(self):
        for rec in self:
            if rec.channel == "web":
                rec.payment_method = "advance"
            elif rec.channel == "reception":
                if rec.payment_method == "on_site" and rec.payment_state in (False, "failed"):
                    rec.payment_state = "pending"

    # ============================================================
    # Payments actions
    # ============================================================
    def action_mark_paid(self, reference=None, correlation_id=None, by_user=None):
        """Marca pagado, fija amount_paid (base reembolso) y confirma SO."""
        self.ensure_one()
        self.write({
            "payment_state": "paid",
            "payment_reference": reference or self.payment_reference,
            "payment_correlation_id": correlation_id or self.payment_correlation_id,
            "paid_at": fields.Datetime.now(),
            "paid_by_user_id": (by_user or self.env.user).id,
            "amount_paid": self.final_total,
        })
        if self.state != "confirmed":
            self.write({"state": "confirmed"})

        if self.sale_order_id and self.sale_order_id.state in ("draft", "sent"):
            self.sale_order_id.sudo().action_confirm()

    def action_mark_payment_failed(self, correlation_id=None):
        self.ensure_one()
        self.write({
            "payment_state": "failed",
            "payment_correlation_id": correlation_id or self.payment_correlation_id,
        })

    def action_register_on_site_payment(self):
        """Recepción cobra y marca pagado (log incluido)."""
        for rec in self:
            if rec.channel != "reception" or rec.payment_method != "on_site":
                raise ValidationError(_("Solo aplica a reservas de recepción con pago en sitio."))

            if rec.payment_state == "paid":
                continue

            so = rec.sale_order_id
            if not so:
                raise ValidationError(_("No hay Orden de Venta vinculada a esta reserva (sale_order_id vacío)."))
            if so.state == "cancel":
                raise ValidationError(_("La orden de venta está cancelada. No se puede confirmar automáticamente."))

            correlation_id = rec.payment_correlation_id or f"REC-{uuid.uuid4().hex[:12].upper()}"
            reference = rec.payment_reference or f"REC-CASH-{rec.reference}"

            if so.state in ("draft", "sent"):
                so.sudo().action_confirm()

            vals = {
                "payment_state": "paid",
                "payment_reference": reference,
                "payment_correlation_id": correlation_id,
                "paid_at": fields.Datetime.now(),
                "paid_by_user_id": self.env.user.id,
                "amount_paid": rec.final_total,
            }
            if rec.state != "confirmed":
                vals["state"] = "confirmed"
            rec.write(vals)

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

    # ============================================================
    # HU-05: Check-in datetime helpers
    # ============================================================
    def _get_checkin_hour(self):
        """Hora de check-in configurable (0-23). Default 14."""
        param = self.env["ir.config_parameter"].sudo().get_param("motel.checkin_hour", default="14")
        try:
            hour = int(param)
        except Exception:
            hour = 14
        return max(0, min(23, hour))

    @api.depends("checkin_date")
    def _compute_checkin_datetime(self):
        for rec in self:
            if not rec.checkin_date:
                rec.checkin_datetime = False
                continue
            hour = rec._get_checkin_hour()
            dt = datetime.combine(rec.checkin_date, time(hour=hour, minute=0, second=0))
            rec.checkin_datetime = fields.Datetime.to_string(dt)

    # ============================================================
    # HU-05: Policy engine + quote + preview
    # ============================================================
    def _compute_refund_percentage(self, cancel_dt):
        """Devuelve porcentaje en [0, 50, 100] según horas antes del check-in."""
        self.ensure_one()
        if not self.checkin_datetime:
            return 0.0

        checkin_dt = fields.Datetime.from_string(self.checkin_datetime)
        cancel_dt = fields.Datetime.from_string(cancel_dt) if isinstance(cancel_dt, str) else cancel_dt
        delta_hours = (checkin_dt - cancel_dt).total_seconds() / 3600.0

        if delta_hours >= 72.0:
            return 100.0
        if 24.0 <= delta_hours < 72.0:
            return 50.0
        return 0.0

    def get_cancellation_quote(self, cancel_dt=None):
        """CA-02/CA-03: desglose para mostrar ANTES de confirmar cancelación."""
        self.ensure_one()
        cancel_dt = cancel_dt or fields.Datetime.now()

        pct = self._compute_refund_percentage(cancel_dt)
        total_paid = self.amount_paid or 0.0  # CA-02: sobre lo realmente pagado

        refund = total_paid * (pct / 100.0)
        retained = total_paid - refund

        return {
            "refund_percentage": pct,
            "total_paid": total_paid,
            "refund_amount": refund,
            "retained_amount": retained,
            "message": _("¿Deseas cancelar esta reserva con un reembolso de $%s?") % (refund,),
        }

    @api.depends("state", "amount_paid", "checkin_date")
    def _compute_refund_quote(self):
        """
        Preview para mostrar en la pestaña Cancelación antes de ejecutar el wizard.
        No persiste; solo calcula con 'ahora'.
        """
        for rec in self:
            rec.refund_quote_percentage = 0.0
            rec.refund_quote_amount = 0.0
            rec.retained_quote_amount = 0.0
            rec.refund_quote_message = False

            if rec.state == "cancelled":
                rec.refund_quote_percentage = rec.refund_percentage or 0.0
                rec.refund_quote_amount = rec.refund_amount or 0.0
                rec.retained_quote_amount = rec.non_refundable_amount or 0.0
                rec.refund_quote_message = _("Reserva ya cancelada.")
                continue

            if not rec.checkin_date:
                rec.refund_quote_message = _("No hay fecha de check-in para calcular política.")
                continue

            quote = rec.get_cancellation_quote(cancel_dt=fields.Datetime.now())
            rec.refund_quote_percentage = quote.get("refund_percentage", 0.0)
            rec.refund_quote_amount = quote.get("refund_amount", 0.0)
            rec.retained_quote_amount = quote.get("retained_amount", 0.0)

            if (rec.amount_paid or 0.0) <= 0:
                rec.refund_quote_message = _("Esta reserva no tiene pagos registrados. Si cancelas, no aplica reembolso.")
            else:
                rec.refund_quote_message = quote.get("message", "")

    # ============================================================
    # HU-05: Cancel execution + refund integration
    # ============================================================
    def action_cancel_with_policy(self, channel="web"):
        """
        CA-04/CA-05/CA-06: Cancela, guarda auditoría, y ejecuta refund si aplica.
        """
        self.ensure_one()
        if self.state == "cancelled":
            return

        cancel_dt = fields.Datetime.now()
        quote = self.get_cancellation_quote(cancel_dt=cancel_dt)

        pct = quote["refund_percentage"]
        refund_amount = quote["refund_amount"]
        retained_amount = quote["retained_amount"]

        # Determinar estado financiero
        if (self.amount_paid or 0.0) <= 0:
            financial_state = "none"
        elif pct >= 100.0:
            financial_state = "refunded"
        elif 0.0 < pct < 100.0:
            financial_state = "partial"
        else:
            financial_state = "non_refundable"

        # Persistir auditoría y estados
        self.write({
            "state": "cancelled",
            "cancelled_at": cancel_dt,
            "cancelled_by_user_id": self.env.user.id,
            "cancelled_channel": channel,
            "refund_percentage": pct,
            "refund_amount": refund_amount,
            "non_refundable_amount": retained_amount,
            "financial_state": financial_state,
        })

        # Log auditoría
        self.env["motel.payment.log"].sudo().create({
            "reservation_id": self.id,
            "channel": channel,
            "action": "cancel",
            "state": "cancelled",
            "correlation_id": self.payment_correlation_id or self.reference,
            "provider_reference": self.payment_reference,
            "performed_by_user_id": self.env.user.id,
            "note": f"Cancelación. pct={pct} refund={refund_amount} retained={retained_amount}",
        })

        # Refund automático solo si fue anticipado + hubo pago + hay monto a reembolsar
        if self.payment_method == "advance" and (self.amount_paid or 0.0) > 0 and refund_amount > 0:
            refund_tx = self._request_gateway_refund(refund_amount)
            if refund_tx:
                self.write({
                    "refund_reference": getattr(refund_tx, "reference", False) or getattr(refund_tx, "provider_reference", False) or "",
                })
        elif self.payment_method == "on_site":
            # Pago en sitio: si hay monto a devolver, suele ser manual
            if refund_amount > 0:
                self.write({"financial_state": "manual"})

    def _request_gateway_refund(self, amount_to_refund):
        """
        Crea solicitud de refund vía payment.transaction.
        Retorna la refund transaction (si se pudo), o None.
        """
        self.ensure_one()

        tx = self.env["payment.transaction"].sudo().search([
            ("reference", "=", self.payment_reference),
        ], limit=1)

        if not tx and self.payment_correlation_id:
            tx = self.env["payment.transaction"].sudo().search([
                ("reference", "ilike", self.payment_correlation_id),
            ], limit=1)

        if not tx:
            self.env["motel.payment.log"].sudo().create({
                "reservation_id": self.id,
                "channel": self.cancelled_channel or "web",
                "action": "refund_request",
                "state": "failed",
                "correlation_id": self.payment_correlation_id or self.reference,
                "provider_reference": self.payment_reference,
                "performed_by_user_id": self.env.user.id,
                "note": "No se encontró payment.transaction para solicitar refund.",
            })
            return None

        # Odoo crea refund tx y envía solicitud al proveedor
        refund_tx = tx.sudo()._refund(amount_to_refund=amount_to_refund)

        self.env["motel.payment.log"].sudo().create({
            "reservation_id": self.id,
            "channel": self.cancelled_channel or "web",
            "action": "refund_request",
            "state": "pending",
            "correlation_id": self.payment_correlation_id or self.reference,
            "provider_reference": getattr(refund_tx, "reference", "") if refund_tx else "",
            "performed_by_user_id": self.env.user.id,
            "note": f"Refund solicitado por {amount_to_refund}.",
        })
        return refund_tx

    # ============================================================
    # Wizard opener (backoffice)
    # ============================================================
    def action_open_cancel_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Cancelar reserva"),
            "res_model": "motel.reservation.cancel.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"active_id": self.id},
        }

    # ============================================================
    # Sequence
    # ============================================================
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("reference", "New") == "New":
                vals["reference"] = self.env["ir.sequence"].next_by_code("motel.reservation") or "RES"
        return super().create(vals_list)
