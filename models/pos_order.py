from odoo import api, models


class PosOrder(models.Model):
    _inherit = 'pos.order'

    @api.model_create_multi
    def create(self, vals_list):
        orders = super().create(vals_list)
        products = orders.lines.product_id
        if products:
            self.env['space.woo.stock.queue']._enqueue(products)
        return orders


class ProductProduct(models.Model):
    _inherit = 'product.product'

    def _space_woo_open_pos_qty(self):
        """Qty sold in POS orders whose stock moves are not yet done.

        POS only decrements stock at session close, so free_qty alone would
        publish stale availability right after a POS sale.
        """
        self.ensure_one()
        # sudo: called from the stock-push cron, which must see POS lines of
        # all users/sessions regardless of the cron user's POS access.
        lines = self.env['pos.order.line'].sudo().search([
            ('product_id', '=', self.id),
            ('order_id.session_id.state', '!=', 'closed'),
            ('order_id.state', 'in', ('paid', 'done', 'invoiced')),
        ])
        return sum(lines.mapped('qty'))
