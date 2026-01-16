# models/reservation.py
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class MotelReservation(models.Model):
    _name = "motel.reservation"
    _description = "Room Reservation"
    _order = "checkin_date desc, id desc"

    # ==========================================================
    # HU-04 (fuente única): reglas de precios en el MODELO
    # ==========================================================
    PRICE_PER_DAY = {"normal": 100.0, "premium": 200.0}
    LONG_STAY_MIN_DAYS = 6
    LONG_STAY_MULTIPLIER = 1.5

    # ---------------------------------------------------------
    # Identificación / trazabilidad
    # ---------------------------------------------------------
    reference = fields.Char(
        string="Reference",
        readonly=True,
        copy=False,
        index=True,
        default="New",
    )
    attempt_uuid = fields.Char(string="Attempt ID", copy=False, index=True)

    # ---------------------------------------------------------
    # Relación con inventario / fechas / estado
    # ---------------------------------------------------------
    room_id = fields.Many2one("motel.room", string="Room", required=True, ondelete="restrict")
    motel_id = fields.Many2one(related="room_id.motel_id", store=True, readonly=True)

    checkin_date = fields.Date(string="Check-in", required=True)
    checkout_date = fields.Date(string="Check-out", required=True)

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
    # Requiere: depends ["sale"]
    # ---------------------------------------------------------
    sale_order_id = fields.Many2one("sale.order", string="Sale Order", ondelete="set null")

    # ---------------------------------------------------------
    # HU-04: trazabilidad de cálculo (CA-04)
    # Todos estos se calculan en backend, se guardan y son readonly.
    # ---------------------------------------------------------
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

    # ==========================================================
    # HU-04: cálculo central (CA-01, CA-02, CA-03, CA-04)
    # ==========================================================
    @api.depends("room_type_code", "checkin_date", "checkout_date")
    def _compute_pricing(self):
        """
        Calcula nights + pricing HU-04 de forma automática y consistente.
        - Normal: 100/día
        - Premium: 200/día
        - >=6 noches => total * 1.5
        """
        for rec in self:
            # Defaults seguros
            rec.nights = 0
            rec.base_price_per_day = 0.0
            rec.base_total = 0.0
            rec.surcharge_applied = False
            rec.final_total = 0.0

            if not rec.checkin_date or not rec.checkout_date:
                continue

            nights = (rec.checkout_date - rec.checkin_date).days
            if nights <= 0:
                # constraint levantará error al guardar
                continue

            if rec.room_type_code not in rec.PRICE_PER_DAY:
                # constraint levantará error al guardar
                continue

            base_per_day = rec.PRICE_PER_DAY[rec.room_type_code]
            base_total = base_per_day * nights
            surcharge = nights >= rec.LONG_STAY_MIN_DAYS
            final_total = base_total * rec.LONG_STAY_MULTIPLIER if surcharge else base_total

            rec.nights = nights
            rec.base_price_per_day = base_per_day
            rec.base_total = base_total
            rec.surcharge_applied = surcharge
            rec.final_total = final_total

    # ==========================================================
    # Constraints (integridad)
    # ==========================================================
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

    # ==========================================================
    # Create/Write: folio por secuencia + recalcular (defensa extra)
    # ==========================================================
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("reference", "New") == "New":
                vals["reference"] = self.env["ir.sequence"].next_by_code("motel.reservation") or "RES"
        return super().create(vals_list)
