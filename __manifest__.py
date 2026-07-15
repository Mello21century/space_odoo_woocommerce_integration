{
    'name': 'WooCommerce Inventory & Sales Integration',
    'summary': 'Free-to-use stock API, WooCommerce stock push and order import',
    'description': """
Token-secured REST API exposing "Free To Use" stock, automatic stock push to
WooCommerce on POS/Sales activity, and WooCommerce order import into Odoo.
""",
    'author': 'Mello21century',
    'website': 'https://github.com/Mello21century/space_odoo_woocommerce_integration',
    'category': 'Sales',
    'version': '19.0.1.0.0',
    'license': 'LGPL-3',
    'depends': ['stock', 'sale_management', 'point_of_sale'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/woo_api_token_views.xml',
        'views/woo_connection_views.xml',
        'views/woo_stock_queue_views.xml',
        'views/woo_order_log_views.xml',
        'views/menus.xml',
        'data/ir_cron.xml',
    ],
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': True,
}
