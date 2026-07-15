from odoo import models, _
from odoo.exceptions import UserError
from odoo.tools import float_compare


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def action_confirm(self):
        self._space_woo_check_stock()
        result = super().action_confirm()
        products = self.order_line.product_id.filtered(
            lambda product: product.type == 'product')
        if products:
            self.env['space.woo.stock.queue']._enqueue(products)
        return result

    def _space_woo_check_stock(self):
        """Block confirmation when a storable line exceeds the free-to-use
        quantity in the order's warehouse (minus open POS session sales)."""
        if not self.env['ir.config_parameter'].sudo().get_param(
                'space_woo.block_out_of_stock'):
            return
        for order in self:
            shortages = []
            storable_lines = order.order_line.filtered(
                lambda line: line.product_id.type == 'product')
            for product in storable_lines.product_id:
                needed = sum(storable_lines.filtered(
                    lambda line: line.product_id == product
                ).mapped('product_uom_qty'))
                ctx_product = product.with_context(
                    warehouse=order.warehouse_id.id)
                available = (ctx_product.free_qty
                             - product._space_woo_open_pos_qty())
                if float_compare(needed, available,
                                 precision_rounding=product.uom_id.rounding) > 0:
                    shortages.append(_(
                        '%(product)s: %(needed)s requested, %(available)s free to use',
                        product=product.display_name, needed=needed,
                        available=available))
            if shortages:
                raise UserError(_(
                    'Not enough free stock to confirm %(order)s (units may be '
                    'held by online orders or open POS sessions):\n%(details)s',
                    order=order.name, details='\n'.join(shortages)))
