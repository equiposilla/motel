# models/motel.py
from odoo import api, fields, models

class MotelMotel(models.Model):
    _name = "motel.motel"
    _description = "Motel"

    name = fields.Char(required=True)
    street = fields.Char()
    city = fields.Char()
    country_id = fields.Many2one("res.country")
    room_ids = fields.One2many("motel.room", "motel_id", string="Rooms")

    room_total = fields.Integer(compute="_compute_room_total", store=False)

    @api.depends("room_ids")
    def _compute_room_total(self):
        for rec in self:
            rec.room_total = len(rec.room_ids)

    def display_address(self):
        self.ensure_one()
        parts = [p for p in [self.street, self.city, self.country_id.name if self.country_id else None] if p]
        return ", ".join(parts) if parts else "Ubicación no definida"


class MotelRoomType(models.Model):
    _name = "motel.room.type"
    _description = "Room Type"

    name = fields.Char(required=True)
    code = fields.Selection([("normal", "Normal"), ("premium", "Premium")], required=True)
    price_per_night = fields.Monetary(required=True, default=0.0)
    currency_id = fields.Many2one("res.currency", required=True, default=lambda self: self.env.company.currency_id.id)


class MotelRoom(models.Model):
    _name = "motel.room"
    _description = "Room"

    name = fields.Char(required=True)  # ej: "N-01", "P-02"
    motel_id = fields.Many2one("motel.motel", required=True, ondelete="cascade")
    room_type_id = fields.Many2one("motel.room.type", required=True)
    active = fields.Boolean(default=True)
