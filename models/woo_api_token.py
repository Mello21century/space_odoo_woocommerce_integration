import hashlib
import secrets

from odoo import api, fields, models, _


class WooApiToken(models.Model):
    _name = 'space.woo.api.token'
    _description = 'WooCommerce Integration API Token'
    _order = 'create_date desc'

    name = fields.Char(required=True, help="What this token is used for, e.g. 'Warehouse app'.")
    token_hash = fields.Char(readonly=True, index=True, copy=False)
    expiration_date = fields.Datetime(
        help="Leave empty for a token that never expires.")
    active = fields.Boolean(default=True)
    last_used = fields.Datetime(readonly=True, copy=False)

    @staticmethod
    def _hash(raw_token):
        return hashlib.sha256(raw_token.encode()).hexdigest()

    @api.model
    def _generate(self, name, expiration_date=False):
        """Create a token record and return (record, raw_token).

        The raw value is only available here; we store its sha256 hash.
        """
        raw_token = secrets.token_urlsafe(32)
        record = self.create({
            'name': name,
            'token_hash': self._hash(raw_token),
            'expiration_date': expiration_date,
        })
        return record, raw_token

    @api.model
    def _check_token(self, raw_token):
        """Return the matching valid token record, or an empty recordset."""
        if not raw_token:
            return self.browse()
        token = self.search([('token_hash', '=', self._hash(raw_token))], limit=1)
        if not token:
            return self.browse()
        if token.expiration_date and token.expiration_date <= fields.Datetime.now():
            return self.browse()
        token.last_used = fields.Datetime.now()
        return token


class WooApiTokenWizard(models.TransientModel):
    _name = 'space.woo.api.token.wizard'
    _description = 'Generate API Token'

    name = fields.Char(required=True)
    expiration_date = fields.Datetime()
    raw_token = fields.Char(readonly=True,
                            help="Copy this value now: it is never shown again.")

    def action_generate(self):
        self.ensure_one()
        _record, raw = self.env['space.woo.api.token']._generate(
            self.name, self.expiration_date)
        self.raw_token = raw
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'name': _('Your API Token'),
        }
