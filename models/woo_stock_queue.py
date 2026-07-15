import logging
import math

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

BATCH_SIZE = 100  # Woo products/batch hard limit
MAX_RETRIES = 5


class WooStockQueue(models.Model):
    _name = 'space.woo.stock.queue'
    _description = 'WooCommerce Stock Push Queue'
    _order = 'create_date'

    connection_id = fields.Many2one(
        'space.woo.connection', required=True, ondelete='cascade', index=True)
    product_id = fields.Many2one(
        'product.product', required=True, ondelete='cascade', index=True)
    state = fields.Selection([
        ('pending', 'Pending'),
        ('done', 'Done'),
        ('error', 'Error'),
    ], default='pending', index=True)
    retry_count = fields.Integer(default=0)
    error_message = fields.Text()

    @api.model
    def _enqueue(self, products):
        """Queue a stock push for `products` on every active connection.
        Deduplicates against already-pending rows."""
        products = products.filtered('barcode')
        if not products:
            return
        connections = self.env['space.woo.connection'].sudo().search([])
        if not connections:
            return
        # sudo: enqueueing is a side effect of POS/sale flows whose users
        # have no access to integration models.
        pending = self.sudo().search_read(
            [('state', '=', 'pending'),
             ('product_id', 'in', products.ids),
             ('connection_id', 'in', connections.ids)],
            ['product_id', 'connection_id'])
        existing = {(row['connection_id'][0], row['product_id'][0]) for row in pending}
        values_list = [
            {'connection_id': connection.id, 'product_id': product.id}
            for connection in connections
            for product in products
            if (connection.id, product.id) not in existing
        ]
        if values_list:
            self.sudo().create(values_list)

    def action_requeue(self):
        self.filtered(lambda row: row.state == 'error').write(
            {'state': 'pending', 'retry_count': 0, 'error_message': False})

    @api.model
    def _run_push(self):
        """Cron entry point: push pending rows, batched per connection."""
        rows = self.search([('state', '=', 'pending')])
        for connection in rows.mapped('connection_id'):
            if not connection.active:
                continue
            connection_rows = rows.filtered(
                lambda row: row.connection_id == connection)
            self._push_connection(connection, connection_rows)

    def _push_connection(self, connection, rows):
        map_model = self.env['space.woo.product.map']
        free_qty = connection._get_free_qty(rows.mapped('product_id'))
        simple, variations, unmapped = [], [], self.browse()
        row_by_woo_id = {}
        for row in rows:
            try:
                entry = map_model._resolve(connection, row.product_id)
            except Exception as error:
                row._mark_error(str(error))
                continue
            if not entry:
                unmapped |= row
                continue
            # Woo stock_quantity is an integer; never publish negative stock.
            qty = max(0, int(math.floor(free_qty[row.product_id] - row.product_id._space_woo_open_pos_qty())))
            if entry.woo_variation_id:
                variations.append((row, entry, qty))
            else:
                simple.append((row, entry, qty))
                row_by_woo_id[entry.woo_product_id] = row
        unmapped._mark_error('SKU not found on store for this barcode')

        for offset in range(0, len(simple), BATCH_SIZE):
            chunk = simple[offset:offset + BATCH_SIZE]
            payload = {'update': [
                {'id': entry.woo_product_id, 'stock_quantity': qty}
                for _row, entry, qty in chunk]}
            try:
                connection._woo_request('PUT', 'products/batch', json=payload)
            except Exception as error:
                for row, _entry, _qty in chunk:
                    row._mark_error(str(error))
                continue
            for row, _entry, _qty in chunk:
                row.write({'state': 'done', 'error_message': False})

        for row, entry, qty in variations:
            try:
                connection._woo_request(
                    'PUT', 'products/%s/variations/%s'
                    % (entry.woo_product_id, entry.woo_variation_id),
                    json={'stock_quantity': qty})
                row.write({'state': 'done', 'error_message': False})
            except Exception as error:
                row._mark_error(str(error))
        _logger.info('Woo stock push: %s rows processed for %s',
                     len(rows), connection.name)

    def _mark_error(self, message):
        for row in self:
            retry = row.retry_count + 1
            row.write({
                'retry_count': retry,
                'error_message': message,
                'state': 'error' if retry >= MAX_RETRIES else 'pending',
            })
