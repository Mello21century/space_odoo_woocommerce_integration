from unittest.mock import patch

from odoo.tests.common import tagged

from .common import WooCase


@tagged('post_install', '-at_install')
class TestStockQueue(WooCase):

    def _pending(self):
        return self.env['space.woo.stock.queue'].search([
            ('state', '=', 'pending'),
            ('product_id', '=', self.product.id),
        ])

    def _make_sale_order(self):
        return self.env['sale.order'].create({
            'partner_id': self.env.ref('base.res_partner_1').id,
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'product_uom_qty': 2,
            })],
        })

    def test_sale_confirm_enqueues_and_dedups(self):
        self._make_sale_order().action_confirm()
        self.assertEqual(len(self._pending()), 1)
        # A second confirmation while the first row is pending must not
        # create a duplicate pending row.
        self._make_sale_order().action_confirm()
        self.assertEqual(len(self._pending()), 1)

    def test_push_sends_free_qty_and_marks_done(self):
        self._make_sale_order().action_confirm()
        row = self._pending()
        self.env['space.woo.product.map'].create({
            'connection_id': self.connection.id,
            'product_id': self.product.id,
            'woo_product_id': 811,
        })
        sent = {}

        def fake_request(_connection, method, endpoint, params=None, json=None):
            sent.update(method=method, endpoint=endpoint, json=json)
            return {}

        with patch.object(type(self.connection), '_woo_request', fake_request):
            self.env['space.woo.stock.queue']._run_push()
        self.assertEqual(row.state, 'done')
        self.assertEqual(sent['endpoint'], 'products/batch')
        # free_qty read at push time: 10 on hand - 2 reserved by the SO.
        self.assertEqual(sent['json']['update'],
                         [{'id': 811, 'stock_quantity': 8}])

    def test_push_failure_retries_then_errors(self):
        self.env['space.woo.stock.queue']._enqueue(self.product)
        row = self._pending()
        self.env['space.woo.product.map'].create({
            'connection_id': self.connection.id,
            'product_id': self.product.id,
            'woo_product_id': 811,
        })

        def failing_request(_connection, *args, **kwargs):
            raise OSError('store unreachable')

        with patch.object(type(self.connection), '_woo_request', failing_request):
            for _attempt in range(5):
                self.env['space.woo.stock.queue']._run_push()
        self.assertEqual(row.state, 'error')
        self.assertEqual(row.retry_count, 5)
        self.assertIn('store unreachable', row.error_message)
        row.action_requeue()
        self.assertEqual(row.state, 'pending')

    def test_unmapped_sku_errors_readably(self):
        self.env['space.woo.stock.queue']._enqueue(self.product)
        row = self._pending()

        def no_result(_connection, method, endpoint, params=None, json=None):
            return []

        with patch.object(type(self.connection), '_woo_request', no_result):
            for _attempt in range(5):
                self.env['space.woo.stock.queue']._run_push()
        self.assertEqual(row.state, 'error')
        self.assertIn('SKU not found', row.error_message)

    def test_barcodeless_products_not_enqueued(self):
        no_barcode = self.env['product.product'].create(
            {'name': 'No Barcode', 'is_storable': True})
        self.env['space.woo.stock.queue']._enqueue(no_barcode)
        self.assertFalse(self.env['space.woo.stock.queue'].search(
            [('product_id', '=', no_barcode.id)]))
