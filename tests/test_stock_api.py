import json
from datetime import timedelta

from odoo import fields
from odoo.tests.common import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestStockApi(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.product = cls.env['product.product'].create({
            'name': 'API Test Product',
            'type': 'product',
            'barcode': 'API-TEST-0001',
        })
        warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.env.company.id)], limit=1)
        cls.env['stock.quant']._update_available_quantity(
            cls.product, warehouse.lot_stock_id, 10)
        _record, cls.token = cls.env['space.woo.api.token']._generate('test')

    def _get(self, token, params=''):
        return self.url_open(
            '/api/v1/stock%s' % params,
            headers={'Authorization': 'Bearer %s' % token})

    def test_valid_token_returns_free_qty(self):
        response = self._get(self.token, '?barcode=API-TEST-0001')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['count'], 1)
        row = data['results'][0]
        self.assertEqual(set(row), {'barcode', 'product_id', 'stock'})
        self.assertEqual(row['product_id'], self.product.id)
        self.assertEqual(row['stock'], self.product.free_qty)

    def test_stock_is_free_qty_not_on_hand(self):
        # Reserve 4 units via a delivery: on hand stays 10, free drops to 6.
        warehouse = self.env['stock.warehouse'].search(
            [('company_id', '=', self.env.company.id)], limit=1)
        picking = self.env['stock.picking'].create({
            'picking_type_id': warehouse.out_type_id.id,
            'location_id': warehouse.lot_stock_id.id,
            'location_dest_id': self.env.ref('stock.stock_location_customers').id,
            'move_ids': [(0, 0, {
                'name': 'out',
                'product_id': self.product.id,
                'product_uom_qty': 4,
                'product_uom': self.product.uom_id.id,
                'location_id': warehouse.lot_stock_id.id,
                'location_dest_id': self.env.ref('stock.stock_location_customers').id,
            })],
        })
        picking.action_confirm()
        picking.action_assign()
        self.assertEqual(self.product.qty_available, 10)
        self.assertEqual(self.product.free_qty, 6)
        data = json.loads(self._get(self.token, '?barcode=API-TEST-0001').content)
        self.assertEqual(data['results'][0]['stock'], 6)

    def test_bad_token_401(self):
        for bad in ('WRONG', ''):
            response = self._get(bad)
            self.assertEqual(response.status_code, 401)

    def test_expired_and_inactive_token_401(self):
        record, token = self.env['space.woo.api.token']._generate(
            'expired', fields.Datetime.now() - timedelta(hours=1))
        self.assertEqual(self._get(token).status_code, 401)
        record.expiration_date = False
        record.active = False
        self.assertEqual(self._get(token).status_code, 401)

    def test_pagination_and_unknown_barcode(self):
        response = self._get(self.token, '?limit=1&offset=0')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content)['count'], 1)
        self.assertEqual(
            self._get(self.token, '?barcode=NO-SUCH-BARCODE').status_code, 404)
