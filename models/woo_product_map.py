import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class WooProductMap(models.Model):
    _name = 'space.woo.product.map'
    _description = 'Odoo Product ↔ WooCommerce Product Mapping'
    _rec_name = 'product_id'

    connection_id = fields.Many2one(
        'space.woo.connection', required=True, ondelete='cascade', index=True)
    product_id = fields.Many2one(
        'product.product', required=True, ondelete='cascade', index=True)
    woo_product_id = fields.Integer(required=True)
    woo_variation_id = fields.Integer()

    _sql_constraints = [
        ('connection_product_uniq', 'unique(connection_id, product_id)',
         'This product is already mapped for this store.'),
    ]

    def _resolve(self, connection, product):
        """Return the map entry for (connection, product), creating it via a
        Woo SKU lookup on cache miss. Returns empty recordset if the barcode
        has no matching SKU on the store."""
        entry = self.search([
            ('connection_id', '=', connection.id),
            ('product_id', '=', product.id),
        ], limit=1)
        if entry:
            return entry
        if not product.barcode:
            return self.browse()
        results = connection._woo_request(
            'GET', 'products', params={'sku': product.barcode})
        if not results:
            return self.browse()
        woo_product = results[0]
        values = {
            'connection_id': connection.id,
            'product_id': product.id,
            'woo_product_id': woo_product['id'],
        }
        if woo_product.get('type') == 'variation' and woo_product.get('parent_id'):
            values.update(woo_product_id=woo_product['parent_id'],
                          woo_variation_id=woo_product['id'])
        return self.create(values)
