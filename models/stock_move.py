from odoo import models


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _action_assign(self, force_qty=False):
        result = super()._action_assign(force_qty=force_qty)
        self._space_woo_enqueue()
        return result

    def _do_unreserve(self):
        result = super()._do_unreserve()
        self._space_woo_enqueue()
        return result

    def _action_done(self, cancel_backorder=False):
        moves = super()._action_done(cancel_backorder=cancel_backorder)
        moves._space_woo_enqueue()
        return moves

    def _space_woo_enqueue(self):
        products = self.product_id.filtered(lambda product: product.type == 'product')
        if products:
            self.env['space.woo.stock.queue']._enqueue(products)
