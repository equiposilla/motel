from datetime import timedelta
from odoo import fields, models


class MotelRateLimit(models.Model):
    _name = "motel.rate.limit"
    _description = "Basic Rate Limit for Public Reservation"
    _order = "create_date desc"

    key = fields.Char(required=True, index=True)
    # create_date NO se define → Odoo lo crea automáticamente

    def is_limited(self, key, window_minutes=10, max_hits=5):
        """
        Devuelve True si la clave (ip:xxx o email:xxx)
        superó el límite en la ventana de tiempo.
        """
        since = fields.Datetime.now() - timedelta(minutes=window_minutes)

        count = self.sudo().search_count([
            ("key", "=", key),
            ("create_date", ">=", since),
        ])

        return count >= max_hits

    def hit(self, key):
        """
        Registra un intento para una clave (ip o email)
        """
        self.sudo().create({
            "key": key
        })
