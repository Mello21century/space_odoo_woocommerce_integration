from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    space_woo_block_out_of_stock = fields.Boolean(
        string='Block Out-of-Stock Sales',
        config_parameter='space_woo.block_out_of_stock',
        help="Prevent POS and Sales from selling units that are no longer "
             "free to use (reserved by online orders or already sold on an "
             "open POS session).")
