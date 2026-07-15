import json

from odoo import http
from odoo.http import request

MAX_LIMIT = 1000


class SpaceWooStockApi(http.Controller):

    @http.route('/api/v1/stock', type='http', auth='public', methods=['GET'],
                csrf=False, save_session=False)
    def stock(self, barcode=None, limit='500', offset='0', **kwargs):
        # sudo: route is public; access is granted by the bearer token check
        # below, not by an Odoo user session.
        env = request.env(su=True)
        auth_header = request.httprequest.headers.get('Authorization', '')
        raw_token = auth_header[7:] if auth_header.startswith('Bearer ') else ''
        if not env['space.woo.api.token']._check_token(raw_token):
            return self._json({'error': 'invalid_token'}, status=401)

        try:
            limit = min(max(int(limit), 1), MAX_LIMIT)
            offset = max(int(offset), 0)
        except ValueError:
            limit, offset = 500, 0

        domain = [('barcode', '!=', False), ('type', '=', 'product')]
        if barcode:
            domain.append(('barcode', '=', barcode))
        products = env['product.product'].search(
            domain, limit=limit, offset=offset, order='id')
        if barcode and not products:
            return self._json({'error': 'not_found'}, status=404)
        results = [{
            'barcode': product.barcode,
            'product_id': product.id,
            'stock': product.free_qty,
        } for product in products]
        return self._json({'count': len(results), 'results': results})

    @staticmethod
    def _json(payload, status=200):
        return request.make_response(
            json.dumps(payload), status=status,
            headers=[('Content-Type', 'application/json')])
