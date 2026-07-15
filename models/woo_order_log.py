import json
import logging

from odoo import fields, models, _

_logger = logging.getLogger(__name__)

IMPORT_STATUSES = ('processing', 'completed')
CANCEL_STATUSES = ('cancelled', 'refunded')


class WooOrderLog(models.Model):
    _name = 'space.woo.order.log'
    _description = 'WooCommerce Inbound Order Log'
    _order = 'create_date desc'
    _rec_name = 'woo_order_id'

    connection_id = fields.Many2one(
        'space.woo.connection', required=True, ondelete='cascade', index=True)
    woo_order_id = fields.Char(required=True, index=True)
    sale_order_id = fields.Many2one('sale.order', readonly=True)
    state = fields.Selection([
        ('done', 'Done'),
        ('skipped', 'Skipped'),
        ('error', 'Error'),
    ], required=True, default='error')
    payload = fields.Text()
    error_message = fields.Text()

    _sql_constraints = [
        ('connection_order_uniq', 'unique(connection_id, woo_order_id)',
         'This WooCommerce order was already received.'),
    ]

    def action_retry(self):
        for log in self.filtered(lambda log: log.state == 'error'):
            log._process(json.loads(log.payload))
        return True

    def _process(self, payload):
        """Create/update the Odoo sale order from a Woo order payload.
        Never raises: failures land in state=error with a readable reason."""
        self.ensure_one()
        status = payload.get('status')
        try:
            # Savepoint: a failed import must not leave partial orders behind,
            # while keeping the log row update below committable.
            with self.env.cr.savepoint():
                if status in CANCEL_STATUSES:
                    self._process_cancellation()
                elif status in IMPORT_STATUSES:
                    self._process_import(payload)
                else:
                    self.write({'state': 'skipped',
                                'error_message': _('Woo status %r is not imported.') % status})
        except Exception as error:
            self.write({'state': 'error', 'error_message': str(error)})
            _logger.warning('Woo order %s import failed: %s',
                            self.woo_order_id, error)

    def _process_cancellation(self):
        if not self.sale_order_id:
            self.write({'state': 'skipped',
                        'error_message': _('Cancellation for an order never imported.')})
            return
        if self.sale_order_id.picking_ids.filtered(lambda p: p.state == 'done'):
            self.write({
                'state': 'error',
                'error_message': _('Order was cancelled on the store but is '
                                   'already delivered in Odoo. Handle manually.')})
            return
        self.sale_order_id._action_cancel()
        self.write({'state': 'done', 'error_message': False})

    def _process_import(self, payload):
        if self.sale_order_id:
            self.write({'state': 'done', 'error_message': False})
            return
        connection = self.connection_id
        partner = self._find_or_create_partner(payload.get('billing') or {})
        lines = []
        for item in payload.get('line_items') or []:
            sku = item.get('sku')
            product = self.env['product.product'].search(
                [('barcode', '=', sku)], limit=1) if sku else None
            if not product:
                raise ValueError(_(
                    "Woo line '%s': SKU %r has no matching product barcode in Odoo.")
                    % (item.get('name'), sku))
            quantity = item.get('quantity') or 0
            # Unit price before coupon discounts: Woo's discount_total is added
            # as its own line below, so lines must carry pre-discount prices.
            subtotal = float(item.get('subtotal') or 0)
            price_unit = subtotal / quantity if quantity else 0.0
            lines.append((0, 0, {
                'product_id': product.id,
                'product_uom_qty': quantity,
                'price_unit': price_unit,
            }))
        discount_total = float(payload.get('discount_total') or 0)
        if discount_total:
            if not connection.discount_product_id:
                raise ValueError(_('Order has a discount but the connection has '
                                   'no Discount Product configured.'))
            lines.append((0, 0, {
                'product_id': connection.discount_product_id.id,
                'product_uom_qty': 1,
                'price_unit': -discount_total,
            }))
        shipping_total = float(payload.get('shipping_total') or 0)
        if shipping_total:
            if not connection.shipping_product_id:
                raise ValueError(_('Order has shipping fees but the connection '
                                   'has no Shipping Product configured.'))
            lines.append((0, 0, {
                'product_id': connection.shipping_product_id.id,
                'product_uom_qty': 1,
                'price_unit': shipping_total,
            }))
        order_values = {
            'partner_id': partner.id,
            'company_id': connection.company_id.id,
            'client_order_ref': str(payload.get('number') or self.woo_order_id),
            'origin': '%s #%s' % (connection.name, payload.get('number') or self.woo_order_id),
            'order_line': lines,
        }
        if connection.warehouse_id:
            order_values['warehouse_id'] = connection.warehouse_id.id
        order = self.env['sale.order'].create(order_values)
        order.action_confirm()
        if connection.auto_invoice:
            self._create_invoice_and_payment(order)
        self.write({'state': 'done', 'sale_order_id': order.id,
                    'error_message': False})

    def _create_invoice_and_payment(self, order):
        """The shopper already paid on the store: post the invoice and
        register the payment in the connection's journal."""
        try:
            invoices = order._create_invoices(final=True)
        except Exception as error:
            raise ValueError(_(
                'Could not invoice %(order)s: %(error)s (products imported '
                'from the store should use the "Ordered quantities" '
                'invoicing policy).', order=order.name, error=error))
        invoices.action_post()
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=invoices.ids,
        ).create({
            'journal_id': self.connection_id.payment_journal_id.id,
        }).action_create_payments()

    def _find_or_create_partner(self, billing):
        email = (billing.get('email') or '').strip().lower()
        partner_model = self.env['res.partner']
        if email:
            partner = partner_model.search([('email', '=ilike', email)], limit=1)
            if partner:
                return partner
        name = ('%s %s' % (billing.get('first_name') or '',
                           billing.get('last_name') or '')).strip()
        if not name and not email:
            raise ValueError(_('Order has no usable billing name or email.'))
        country = self.env['res.country'].search(
            [('code', '=', billing.get('country'))], limit=1)
        return partner_model.create({
            'name': name or email,
            'email': email or False,
            'phone': billing.get('phone') or False,
            'street': billing.get('address_1') or False,
            'city': billing.get('city') or False,
            'country_id': country.id or False,
            'company_id': False,
        })
