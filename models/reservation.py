# models/reservation.py
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class MotelReservation(models.Model):
    _name = "motel.reservation"
    _description = "Room Reservation"
    _order = "checkin_date desc, id desc"

    # ---------------------------------------------------------
    # Identificación / trazabilidad base
    # ---------------------------------------------------------
    reference = fields.Char(
        string="Reference",
        readonly=True,
        copy=False,
        index=True,
        default=lambda self: "New",
    )
    attempt_uuid = fields.Char(string="Attempt ID", copy=False, index=True)

    # ---------------------------------------------------------
    # Relación con inventario / fechas / estado
    # ---------------------------------------------------------
    room_id = fields.Many2one("motel.room", required=True, ondelete="restrict")
    motel_id = fields.Many2one(related="room_id.motel_id", store=True, readonly=True)
    checkin_date = fields.Date(required=True)
    checkout_date = fields.Date(required=True)

    state = fields.Selection(
        [("draft", "Draft"), ("confirmed", "Confirmed"), ("cancelled", "Cancelled")],
        default="draft",
        required=True,
    )

    # ---------------------------------------------------------
    # Cliente / huésped (HU-02)
    # ---------------------------------------------------------
    partner_id = fields.Many2one("res.partner", string="Customer", ondelete="set null")
    guest_first_name = fields.Char(string="Guest First Name")
    guest_last_name = fields.Char(string="Guest Last Name")
    guest_email = fields.Char(string="Guest Email")
    guest_phone = fields.Char(string="Guest Phone")
    terms_accepted = fields.Boolean(string="Terms Accepted", default=False)

    # ---------------------------------------------------------
    # Integración con ventas (HU-02)
    # ---------------------------------------------------------
    sale_order_id = fields.Many2one("sale.order", string="Sale Order", ondelete="set null")

    # ---------------------------------------------------------
    # HU-04: Reglas de precios y trazabilidad del cálculo (CA-04)
    # ---------------------------------------------------------
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        required=True,
        default=lambda self: self.env.company.currency_id,
    )

    room_type_code = fields.Selection(
        [("normal", "Normal"), ("premium", "Premium")],
        string="Room Type",
        required=True,
        default="normal",
    )

    nights = fields.Integer(string="Nights", required=True, default=1)
    base_price_per_day = fields.Float(string="Base Price / Day", required=True, default=0.0)
    base_total = fields.Monetary(string="Base Total", currency_field="currency_id", required=True, default=0.0)
    surcharge_applied = fields.Boolean(string="Long-stay Surcharge Applied", default=False)
    final_total = fields.Monetary(string="Final Total", currency_field="currency_id", required=True, default=0.0)

    # ---------------------------------------------------------
    # Constraints
    # ---------------------------------------------------------
    @api.constrains("checkin_date", "checkout_date")
    def _check_dates(self):
        for rec in self:
            if rec.checkin_date and rec.checkout_date and rec.checkout_date <= rec.checkin_date:
                raise ValidationError("La fecha de salida debe ser posterior a la de entrada.")

    @api.constrains("room_type_code")
    def _check_room_type_code(self):
        for rec in self:
            if rec.room_type_code not in ("normal", "premium"):
                raise ValidationError("Tipo de habitación inválido.")

    @api.constrains("nights", "checkin_date", "checkout_date")
    def _check_nights(self):
        for rec in self:
            if rec.checkin_date and rec.checkout_date:
                expected = (rec.checkout_date - rec.checkin_date).days
                if expected <= 0:
                    raise ValidationError("Rango de fechas inválido.")
                # nights debe coincidir (auditoría / consistencia)
                if rec.nights and rec.nights != expected:
                    raise ValidationError("El número de noches no coincide con las fechas.")

    # ---------------------------------------------------------
    # Create override: generar reference por secuencia
    # ---------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("reference", "New") == "New":
                vals["reference"] = self.env["ir.sequence"].next_by_code("motel.reservation") or "RES"
        return super().create(vals_list)
