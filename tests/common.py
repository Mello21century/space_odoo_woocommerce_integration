from odoo.tests.common import TransactionCase


class WooCase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.env.company.id)], limit=1)
        cls.product = cls.env['product.product'].create({
            'name': 'Woo Test Product',
            'type': 'product',
            'barcode': 'WOO-TEST-0001',
            'list_price': 10.0,
        })
        cls.env['stock.quant']._update_available_quantity(
            cls.product, cls.warehouse.lot_stock_id, 10)
        cls.discount_product = cls.env['product.product'].create({
            'name': 'Woo Discount', 'type': 'service'})
        cls.shipping_product = cls.env['product.product'].create({
            'name': 'Woo Shipping', 'type': 'service'})
        cls.connection = cls.env['space.woo.connection'].create({
            'name': 'Test Store',
            'store_url': 'https://store.test',
            'consumer_key': 'ck_test',
            'consumer_secret': 'cs_test',
            'webhook_secret': 'whsec_test',
            'warehouse_id': cls.warehouse.id,
            'discount_product_id': cls.discount_product.id,
            'shipping_product_id': cls.shipping_product.id,
        })
