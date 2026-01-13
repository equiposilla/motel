# models/rate_limit.py
from datetime import datetime, timedelta
from odoo import fields, models


class MotelRateLimit(models.Model):
    _name = "motel.rate.limit"
    _description = "Basic Rate Limit for Public Reservation"

    key = fields.Char(required=True, index=True)  # "ip:xxx" o "email:xxx"
    create_date = fields.Datetime(readonly=True)

    @classmethod
    def is_limited(cls, env, key: str, window_minutes: int = 10, max_hits: int = 5) -> bool:
        since = datetime.utcnow() - timedelta(minutes=window_minutes)
        count = env["motel.rate.limit"].sudo().search_count([("key", "=", key), ("create_date", ">=", since)])
        return count >= max_hits

    @classmethod
    def hit(cls, env, key: str):
        env["motel.rate.limit"].sudo().create({"key": key})
