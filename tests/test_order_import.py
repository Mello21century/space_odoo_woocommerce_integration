import base64
import hashlib
import hmac
import json

from odoo.tests.common import HttpCase, tagged

from .common import WooCase


def order_payload(**overrides):
    payload = {
        'id': 5001,
        'number': '5001',
        'status': 'processing',
        'currency': 'USD',
        'discount_total': '5.00',
        'shipping_total': '7.50',
        'billing': {
            'first_name': 'Jane', 'last_name': 'Shopper',
            'email': 'jane@example.com', 'phone': '123456',
            'address_1': '1 Main St', 'city': 'Springfield', 'country': 'US',
        },
        'line_items': [{
            'sku': 'WOO-TEST-0001', 'name': 'Woo Test Product',
            'quantity': 2, 'price': 9.0, 'subtotal': '20.00', 'total': '18.00',
        }],
    }
    payload.update(overrides)
    return payload


@tagged('post_install', '-at_install')
class TestOrderImport(WooCase):

    def _receive(self, payload):
        log = self.env['space.woo.order.log'].create({
            'connection_id': self.connection.id,
            'woo_order_id': str(payload['id']),
            'payload': json.dumps(payload),
        })
        log._process(payload)
        return log

    def test_full_order_import(self):
        log = self._receive(order_payload())
        self.assertEqual(log.state, 'done', log.error_message)
        order = log.sale_order_id
        self.assertEqual(order.state, 'sale')
        self.assertEqual(order.partner_id.email, 'jane@example.com')
        self.assertEqual(order.client_order_ref, '5001')
        # 2 x 10 (pre-discount) - 5 discount + 7.5 shipping
        self.assertAlmostEqual(order.amount_untaxed, 22.5)
        discount_line = order.order_line.filtered(
            lambda line: line.product_id == self.discount_product)
        self.assertAlmostEqual(discount_line.price_unit, -5.0)
        # Stock is reserved by the confirmed order.
        self.assertEqual(self.product.free_qty, 8)

    def test_existing_customer_matched_not_duplicated(self):
        partner = self.env['res.partner'].create(
            {'name': 'Jane Shopper', 'email': 'JANE@example.com'})
        log = self._receive(order_payload())
        self.assertEqual(log.sale_order_id.partner_id, partner)

    def test_unknown_sku_held_in_error_then_retry(self):
        payload = order_payload()
        payload['line_items'][0]['sku'] = 'MISSING-SKU'
        log = self._receive(payload)
        self.assertEqual(log.state, 'error')
        self.assertIn('MISSING-SKU', log.error_message)
        self.assertFalse(log.sale_order_id)
        # Fix the barcode, retry from the stored payload.
        self.product.barcode = 'MISSING-SKU'
        log.action_retry()
        self.assertEqual(log.state, 'done')
        self.assertTrue(log.sale_order_id)

    def test_skipped_statuses(self):
        log = self._receive(order_payload(status='pending'))
        self.assertEqual(log.state, 'skipped')
        self.assertFalse(log.sale_order_id)

    def test_cancellation_of_imported_order(self):
        log = self._receive(order_payload())
        order = log.sale_order_id
        log._process(order_payload(status='cancelled'))
        self.assertEqual(log.state, 'done')
        self.assertEqual(order.state, 'cancel')


@tagged('post_install', '-at_install')
class TestWebhookEndpoint(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.product = cls.env['product.product'].create({
            'name': 'Webhook Product', 'is_storable': True,
            'barcode': 'WOO-TEST-0001',
        })
        warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.env.company.id)], limit=1)
        cls.env['stock.quant']._update_available_quantity(
            cls.product, warehouse.lot_stock_id, 10)
        cls.connection = cls.env['space.woo.connection'].create({
            'name': 'Webhook Store',
            'store_url': 'https://store.test',
            'consumer_key': 'ck', 'consumer_secret': 'cs',
            'webhook_secret': 'whsec_test',
            'discount_product_id': cls.env['product.product'].create(
                {'name': 'Disc', 'type': 'service'}).id,
            'shipping_product_id': cls.env['product.product'].create(
                {'name': 'Ship', 'type': 'service'}).id,
        })

    def _post(self, body, secret='whsec_test'):
        signature = base64.b64encode(hmac.new(
            secret.encode(), body, hashlib.sha256).digest()).decode()
        return self.url_open(
            '/woo/webhook/order/%s' % self.connection.id, data=body,
            headers={'X-WC-Webhook-Signature': signature,
                     'Content-Type': 'application/json'})

    def test_valid_signature_creates_order_and_is_idempotent(self):
        body = json.dumps(order_payload()).encode()
        response = self._post(body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content)['status'], 'ok')
        orders = self.env['sale.order'].search(
            [('client_order_ref', '=', '5001')])
        self.assertEqual(len(orders), 1)
        # Redelivery: no duplicate.
        response = self._post(body)
        self.assertEqual(json.loads(response.content)['status'], 'duplicate')
        self.assertEqual(self.env['sale.order'].search_count(
            [('client_order_ref', '=', '5001')]), 1)

    def test_bad_signature_401(self):
        response = self._post(json.dumps(order_payload()).encode(), secret='WRONG')
        self.assertEqual(response.status_code, 401)

    def test_unknown_connection_404(self):
        body = json.dumps(order_payload()).encode()
        signature = base64.b64encode(hmac.new(
            b'whsec_test', body, hashlib.sha256).digest()).decode()
        response = self.url_open(
            '/woo/webhook/order/999999', data=body,
            headers={'X-WC-Webhook-Signature': signature})
        self.assertEqual(response.status_code, 404)
