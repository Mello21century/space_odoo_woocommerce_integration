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

    @api.model
    def space_woo_pos_available(self, product_id, config_id):
        """Called by the POS frontend before adding a product to the cart.

        Returns {'enabled': False} when the guard is off or the product is
        not storable, else {'enabled': True, 'available': qty} where qty is
        the free-to-use quantity in the POS terminal's warehouse minus units
        already sold on any open POS session.
        """
        enabled = self.env['ir.config_parameter'].sudo().get_param(
            'space_woo.block_out_of_stock')
        product = self.browse(product_id).exists()
        if not enabled or not product or product.type != 'product':
            return {'enabled': False}
        config = self.env['pos.config'].browse(config_id).exists()
        warehouse = config.picking_type_id.warehouse_id
        if warehouse:
            product = product.with_context(warehouse=warehouse.id)
        return {
            'enabled': True,
            'available': product.free_qty - product._space_woo_open_pos_qty(),
        }

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
