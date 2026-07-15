import logging

import requests

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

WOO_TIMEOUT = 20


class WooConnection(models.Model):
    _name = 'space.woo.connection'
    _description = 'WooCommerce Store Connection'

    name = fields.Char(required=True)
    store_url = fields.Char(required=True, help="https://yourstore.example.com")
    consumer_key = fields.Char(required=True)
    consumer_secret = fields.Char(required=True)
    webhook_secret = fields.Char(
        help="Secret configured on the WooCommerce webhook; used to verify "
             "inbound order notifications.")
    warehouse_id = fields.Many2one(
        'stock.warehouse', string='Warehouse',
        help="Restrict 'Free To Use' stock to this warehouse. "
             "Empty = whole company.")
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company)
    discount_product_id = fields.Many2one(
        'product.product', string='Discount Product',
        domain=[('type', '=', 'service')],
        help="Service product used for the order discount line.")
    shipping_product_id = fields.Many2one(
        'product.product', string='Shipping Product',
        domain=[('type', '=', 'service')],
        help="Service product used for the delivery fee line.")
    auto_invoice = fields.Boolean(
        string='Invoice & Register Payment',
        help="After importing a store order, create and post the invoice and "
             "register its payment (the shopper already paid online).")
    payment_journal_id = fields.Many2one(
        'account.journal', string='Payment Journal',
        domain="[('type', 'in', ('bank', 'cash'))]",
        check_company=True,
        help="Journal receiving the online payments (e.g. the payment "
             "provider's bank journal).")
    state = fields.Selection([
        ('draft', 'Draft'),
        ('connected', 'Connected'),
        ('error', 'Error'),
    ], default='draft', readonly=True, copy=False)
    error_message = fields.Text(readonly=True, copy=False)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('store_url_company_uniq', 'unique(store_url, company_id)',
         'This store is already configured for this company.'),
    ]

    @api.constrains('auto_invoice', 'payment_journal_id')
    def _check_auto_invoice(self):
        for connection in self:
            if connection.auto_invoice and not connection.payment_journal_id:
                raise ValidationError(_(
                    'Set a Payment Journal to invoice and register payments '
                    'automatically.'))

    @api.constrains('store_url')
    def _check_store_url(self):
        for connection in self:
            if not connection.store_url.startswith('https://'):
                raise ValidationError(_('The store URL must use HTTPS.'))

    # ------------------------------------------------------------------
    # WooCommerce REST v3 client
    # ------------------------------------------------------------------
    def _woo_request(self, method, endpoint, params=None, json=None):
        """Call the Woo REST API. Returns parsed JSON, raises on HTTP error."""
        self.ensure_one()
        url = '%s/wp-json/wc/v3/%s' % (self.store_url.rstrip('/'), endpoint)
        response = requests.request(
            method, url,
            auth=(self.consumer_key, self.consumer_secret),
            params=params, json=json, timeout=WOO_TIMEOUT,
        )
        response.raise_for_status()
        return response.json()

    def action_test_connection(self):
        for connection in self:
            try:
                connection._woo_request('GET', 'products', params={'per_page': 1})
                connection.write({'state': 'connected', 'error_message': False})
            except Exception as error:
                connection.write({'state': 'error', 'error_message': str(error)})
        return True

    def _get_free_qty(self, products):
        """Return {product: free_qty} in this connection's warehouse context."""
        self.ensure_one()
        if self.warehouse_id:
            products = products.with_context(warehouse=self.warehouse_id.id)
        products = products.with_company(self.company_id)
        return {product: product.free_qty for product in products}
