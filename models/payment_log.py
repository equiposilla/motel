# models/payment_log.py
from odoo import fields, models


class MotelPaymentLog(models.Model):
    _name = "motel.payment.log"
    _description = "Motel Payment Audit Log"
    _order = "create_date desc, id desc"

    reservation_id = fields.Many2one("motel.reservation", required=True, ondelete="cascade", index=True)
    channel = fields.Selection([("web", "Web"), ("reception", "Reception")], required=True, index=True)
    action = fields.Selection(
        [("web_tx", "Web transaction"), ("reception_collect", "Reception collect")],
        required=True,
        index=True,
    )
    state = fields.Selection([
    ("pending", "Pending"),
    ("paid", "Paid"),
    ("failed", "Failed"),
    ("cancelled", "Cancelled"),
    ], required=True, index=True)

    correlation_id = fields.Char(index=True)
    provider_reference = fields.Char(string="Gateway Reference")
    performed_by_user_id = fields.Many2one("res.users", string="Performed By", readonly=True)
    note = fields.Char()
