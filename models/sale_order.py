from odoo import models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def action_confirm(self):
        result = super().action_confirm()
        products = self.order_line.product_id.filtered(
            lambda product: product.is_storable)
        if products:
            self.env['space.woo.stock.queue']._enqueue(products)
        return result
