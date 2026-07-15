from odoo.exceptions import UserError
from odoo.tests.common import tagged

from .common import WooCase


@tagged('post_install', '-at_install')
class TestStockGuard(WooCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['ir.config_parameter'].sudo().set_param(
            'space_woo.block_out_of_stock', 'True')

    def _order(self, qty):
        return self.env['sale.order'].create({
            'partner_id': self.env.ref('base.res_partner_1').id,
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'product_uom_qty': qty,
            })],
        })

    def test_confirm_blocked_when_exceeding_free_qty(self):
        # 10 on hand, nothing reserved: 15 must be refused, 10 must pass.
        with self.assertRaises(UserError):
            self._order(15).action_confirm()
        order = self._order(10)
        order.action_confirm()
        self.assertEqual(order.state, 'sale')
        # Everything now reserved: even 1 more unit must be refused.
        with self.assertRaises(UserError):
            self._order(1).action_confirm()

    def test_guard_disabled_allows_overselling(self):
        self.env['ir.config_parameter'].sudo().set_param(
            'space_woo.block_out_of_stock', '')
        order = self._order(15)
        order.action_confirm()
        self.assertEqual(order.state, 'sale')

    def test_pos_available_rpc(self):
        config = self.env['pos.config'].search([], limit=1)
        if not config:
            self.skipTest('No POS config in this database')
        result = self.env['product.product'].space_woo_pos_available(
            self.product.id, config.id)
        self.assertTrue(result['enabled'])
        self.assertEqual(result['available'], 10)
        # Reserving via a sale order lowers the POS availability too.
        self._order(4).action_confirm()
        result = self.env['product.product'].space_woo_pos_available(
            self.product.id, config.id)
        self.assertEqual(result['available'], 6)
        # Services and disabled guard short-circuit.
        service = self.env['product.product'].create(
            {'name': 'Svc', 'type': 'service'})
        self.assertFalse(self.env['product.product'].space_woo_pos_available(
            service.id, config.id)['enabled'])
        self.env['ir.config_parameter'].sudo().set_param(
            'space_woo.block_out_of_stock', '')
        self.assertFalse(self.env['product.product'].space_woo_pos_available(
            self.product.id, config.id)['enabled'])
