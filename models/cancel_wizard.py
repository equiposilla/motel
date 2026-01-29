# models/cancel_wizard.py
from odoo import api, fields, models, _
from odoo.exceptions import UserError

class MotelReservationCancelWizard(models.TransientModel):
    _name = "motel.reservation.cancel.wizard"
    _description = "Cancel reservation with policy (quote + confirm)"

    reservation_id = fields.Many2one("motel.reservation", required=True, readonly=True)
    currency_id = fields.Many2one(related="reservation_id.currency_id", readonly=True)

    refund_percentage = fields.Float(readonly=True)
    total_paid = fields.Monetary(currency_field="currency_id", readonly=True)
    refund_amount = fields.Monetary(currency_field="currency_id", readonly=True)
    retained_amount = fields.Monetary(currency_field="currency_id", readonly=True)

    message = fields.Char(readonly=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        reservation = self.env["motel.reservation"].browse(self.env.context.get("active_id"))
        if not reservation or not reservation.exists():
            raise UserError(_("No se encontró la reserva activa."))

        quote = reservation.get_cancellation_quote()
        res.update({
            "reservation_id": reservation.id,
            "refund_percentage": quote.get("refund_percentage", 0.0),
            "total_paid": quote.get("total_paid", 0.0),
            "refund_amount": quote.get("refund_amount", 0.0),
            "retained_amount": quote.get("retained_amount", 0.0),
            "message": quote.get("message", ""),
        })
        return res

    def action_confirm_cancel(self):
        self.ensure_one()
        if self.reservation_id.state == "cancelled":
            return {"type": "ir.actions.act_window_close"}

        # Ejecuta cancelación con canal recepción
        self.reservation_id.action_cancel_with_policy(channel="reception")
        return {"type": "ir.actions.act_window_close"}
