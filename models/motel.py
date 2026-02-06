# models/motel.py
from odoo import api, fields, models , tools

class MotelMotel(models.Model):
    _name = "motel.motel"
    _description = "Motel"

    name = fields.Char(required=True)
    street = fields.Char()
    city = fields.Char()
    country_id = fields.Many2one("res.country")
    room_ids = fields.One2many("motel.room", "motel_id", string="Rooms")
    room_total = fields.Integer(compute="_compute_room_total", store=False)
    latitude = fields.Float(string="Latitud", digits=(10, 7))
    longitude = fields.Float(string="Longitud", digits=(10, 7))

    @api.depends("room_ids")
    def _compute_room_total(self):
        for rec in self:
            rec.room_total = len(rec.room_ids)

    def display_address(self):
        self.ensure_one()
        parts = [p for p in [self.street, self.city, self.country_id.name if self.country_id else None] if p]
        return ", ".join(parts) if parts else "Ubicación no definida"

    def _has_valid_coords(self):
        self.ensure_one()
        return (
            self.latitude is not False and self.longitude is not False
            and -90.0 <= self.latitude <= 90.0
            and -180.0 <= self.longitude <= 180.0
        )
        
    @tools.ormcache()  # cache básico (CA-05 / CA-08)
    def _public_map_payload_cached(self):
        motels = self.sudo().search([])
        items = []
        for m in motels:
            if not m._has_valid_coords():
                continue
            items.append({
                "id": m.id,
                "name": m.name,
                "address": m.display_address(),
                # placeholder de detalle (CA-03)
                "detail_url": f"/motels/{m.id}",
                "lat": m.latitude,
                "lng": m.longitude,
            })
        return items

    def public_map_payload(self):
        # wrapper para poder invalidar si lo necesitas más adelante
        return self._public_map_payload_cached()


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
