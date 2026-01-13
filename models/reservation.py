# models/reservation.py
import uuid
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class MotelReservation(models.Model):
    _name = "motel.reservation"
    _description = "Room Reservation"
    _order = "checkin_date desc, id desc"

    reference = fields.Char(default=lambda self: f"RSV-{uuid.uuid4().hex[:10].upper()}", readonly=True)
    attempt_uuid = fields.Char(readonly=True)  # trazabilidad (intentos)

    room_id = fields.Many2one("motel.room", required=True, ondelete="restrict")
    motel_id = fields.Many2one(related="room_id.motel_id", store=True, readonly=True)

    checkin_date = fields.Date(required=True)
    checkout_date = fields.Date(required=True)

    state = fields.Selection(
        [("draft", "Draft"), ("confirmed", "Confirmed"), ("cancelled", "Cancelled")],
        default="draft",
        required=True,
    )

    # Datos mínimos guest (HU-02)
    guest_first_name = fields.Char(required=True)
    guest_last_name = fields.Char(required=True)
    guest_email = fields.Char(required=True)
    guest_phone = fields.Char(required=True)
    terms_accepted = fields.Boolean(default=False)

    partner_id = fields.Many2one("res.partner", readonly=True)  # partner creado/reutilizado

    sale_order_id = fields.Many2one("sale.order", readonly=True)

    @api.constrains("checkin_date", "checkout_date")
    def _check_dates(self):
        for rec in self:
            if rec.checkout_date and rec.checkin_date and rec.checkout_date <= rec.checkin_date:
                raise ValidationError("La fecha de salida debe ser posterior a la de entrada.")

    @api.constrains("room_id", "checkin_date", "checkout_date", "state")
    def _check_overlap_confirmed(self):
        """
        Evita que una misma habitación tenga 2 reservas CONFIRMED traslapadas.
        """
        for rec in self:
            if rec.state != "confirmed":
                continue
            domain = [
                ("id", "!=", rec.id),
                ("room_id", "=", rec.room_id.id),
                ("state", "=", "confirmed"),
                ("checkin_date", "<", rec.checkout_date),
                ("checkout_date", ">", rec.checkin_date),
            ]
            if self.search_count(domain):
                raise ValidationError("La habitación ya está reservada en ese rango de fechas.")
