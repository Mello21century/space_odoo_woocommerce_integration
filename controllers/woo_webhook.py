import base64
import hashlib
import hmac
import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class SpaceWooWebhook(http.Controller):

    @http.route('/woo/webhook/order/<int:connection_id>', type='http',
                auth='public', methods=['POST'], csrf=False, save_session=False)
    def order_webhook(self, connection_id, **kwargs):
        # sudo: public route; authenticity is proven by the HMAC signature
        # computed with the connection's webhook secret.
        env = request.env(su=True)
        connection = env['space.woo.connection'].browse(connection_id).exists()
        if not connection:
            return self._json({'error': 'not_found'}, status=404)

        raw_body = request.httprequest.get_data()
        if not self._verify_signature(connection, raw_body):
            return self._json({'error': 'invalid_signature'}, status=401)

        try:
            payload = json.loads(raw_body)
        except (ValueError, UnicodeDecodeError):
            # Woo sends a ping without an order body when the webhook is
            # first saved: acknowledge it so activation succeeds.
            return self._json({'status': 'ignored'})
        woo_order_id = str(payload.get('id') or '')
        if not woo_order_id:
            return self._json({'status': 'ignored'})

        log_model = env['space.woo.order.log']
        log = log_model.search([
            ('connection_id', '=', connection.id),
            ('woo_order_id', '=', woo_order_id),
        ], limit=1)
        if log and log.state == 'done' and payload.get('status') not in ('cancelled', 'refunded'):
            return self._json({'status': 'duplicate'})
        if not log:
            log = log_model.create({
                'connection_id': connection.id,
                'woo_order_id': woo_order_id,
                'payload': raw_body.decode('utf-8', errors='replace'),
            })
        else:
            log.payload = raw_body.decode('utf-8', errors='replace')
        log._process(payload)
        response = {'status': 'ok' if log.state == 'done' else log.state}
        if log.sale_order_id:
            response['sale_order'] = log.sale_order_id.name
        # Always 200 for business errors: the order is held in the log for
        # manual retry; a non-2xx would make Woo retry (and eventually
        # disable) the webhook.
        return self._json(response)

    @staticmethod
    def _verify_signature(connection, raw_body):
        if not connection.active or not connection.webhook_secret:
            return False
        signature = request.httprequest.headers.get('X-WC-Webhook-Signature', '')
        expected = base64.b64encode(hmac.new(
            connection.webhook_secret.encode(), raw_body, hashlib.sha256,
        ).digest()).decode()
        return hmac.compare_digest(signature, expected)

    @staticmethod
    def _json(payload, status=200):
        return request.make_response(
            json.dumps(payload), status=status,
            headers=[('Content-Type', 'application/json')])
