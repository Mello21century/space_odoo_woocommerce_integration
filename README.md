# WooCommerce Inventory & Sales Integration for Odoo

Free (LGPL-3) Odoo module connecting Odoo and WooCommerce:

- **Free-To-Use stock API** — `GET /api/v1/stock` returns `{barcode, product_id, stock}`
  where `stock` is Odoo's *Free To Use* quantity (on hand − reserved), so external systems
  never see stock that is already promised.
- **Multiple API tokens** — each with its own expiration; stored hashed, shown once.
- **Automatic stock push to WooCommerce** — POS orders, sales order confirmations and stock
  reservations queue batched `stock_quantity` updates to Woo products matched by
  Odoo **barcode** = Woo **SKU**.
- **Order import from WooCommerce** — HMAC-verified webhook creates confirmed Odoo sales
  orders with customer, sold prices, discounts and delivery fees; stock is reduced. Idempotent
  (no duplicates); failures are held in a log with a Retry button.

## Supported versions

| Branch | Odoo | Community | Enterprise |
|--------|------|-----------|------------|
| `17.0` | 17.0 | ✅ | ✅ |
| `18.0` | 18.0 | ✅ | ✅ |
| `19.0` | 19.0 | ✅ | ✅ |

The module only depends on Community modules (`stock`, `sale_management`, `point_of_sale`),
so it runs identically on both editions.

## Installation

```bash
cd /path/to/your/addons
git clone -b 17.0 https://github.com/Mello21century/space_odoo_woocommerce_integration.git
# make sure the parent folder is in your addons_path, then:
odoo-bin -d yourdb -i space_odoo_woocommerce_integration
```

Pick the branch matching your Odoo series (`17.0`, `18.0`, `19.0`).

## Configuration

1. **Store Connections** → create a connection with your store URL and WooCommerce REST API
   consumer key/secret (WooCommerce → Settings → Advanced → REST API), then *Test Connection*.
2. In WooCommerce add an **Order created** webhook (Settings → Advanced → Webhooks) targeting
   `https://<your-odoo>/woo/webhook/order/<connection id>` with the connection's webhook
   secret. Add **Order updated** too if you want cancellations/refunds handled.
3. Set each Odoo product's **Barcode** to the Woo product **SKU** (enable *Manage stock* on
   the Woo product).
4. Optionally generate an **API token** and pull stock from any external system:

```bash
curl -H "Authorization: Bearer YOUR_TOKEN" "https://your-odoo/api/v1/stock?limit=100"
```

## Development

Tests: `odoo-bin -d testdb -i space_odoo_woocommerce_integration --test-enable \
--test-tags /space_odoo_woocommerce_integration --stop-after-init`

## License

LGPL-3 — free to use, modify and redistribute.
