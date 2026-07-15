/** @odoo-module */
import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/store/pos_store";
import { ErrorPopup } from "@point_of_sale/app/errors/popups/error_popup";
import { _t } from "@web/core/l10n/translation";

patch(PosStore.prototype, {
    async addProductFromUi(product, options) {
        let available = null;
        try {
            const result = await this.orm.call(
                "product.product", "space_woo_pos_available",
                [product.id, this.config.id]);
            available = result.enabled ? result.available : null;
        } catch {
            // ponytail: an offline or failing server must never freeze the
            // till — the guard fails open and the server-side sale checks
            // remain the safety net.
            available = null;
        }
        if (available !== null) {
            const order = this.get_order();
            const inCart = order
                ? order.get_orderlines()
                      .filter((line) => line.get_product().id === product.id)
                      .reduce((total, line) => total + line.get_quantity(), 0)
                : 0;
            const requested = inCart + (options?.quantity ?? 1);
            if (requested > available) {
                await this.env.services.popup.add(ErrorPopup, {
                    title: _t("Out of stock"),
                    body: _t(
                        "Only %s unit(s) of %s are free to use — the rest may be held by online orders or another register.",
                        Math.max(available, 0), product.display_name),
                });
                return;
            }
        }
        return super.addProductFromUi(product, options);
    },
});
