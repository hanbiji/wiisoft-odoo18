# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    esim_recharge_id = fields.Many2one(
        'esim.balance.recharge', string="eSIM 充值单",
        ondelete='set null', readonly=True,
    )
    esim_order_id = fields.Many2one(
        'esim.order', string="eSIM 订单",
        ondelete='set null', readonly=True,
    )

    # ------------------------------------------------------------------
    # Reference
    # ------------------------------------------------------------------

    @api.model
    def _compute_reference_prefix(self, separator, **values):
        """使用关联单据的编号作为交易 reference 前缀。"""
        recharge_id = values.get('esim_recharge_id')
        if recharge_id:
            recharge = self.env['esim.balance.recharge'].browse(recharge_id).exists()
            if recharge:
                return recharge.name

        order_id = values.get('esim_order_id')
        if order_id:
            order = self.env['esim.order'].browse(order_id).exists()
            if order:
                return order.name

        return super()._compute_reference_prefix(separator, **values)

    # ------------------------------------------------------------------
    # Post-processing
    # ------------------------------------------------------------------

    def _post_process(self):
        super()._post_process()
        self._post_process_recharge()
        self._post_process_esim_order()

    def _post_process_recharge(self):
        """充值单到账处理。"""
        for tx in self.filtered(lambda t: t.state == 'done' and t.esim_recharge_id):
            recharge = tx.esim_recharge_id
            if recharge.state == 'done':
                continue
            recharge.action_credit_balance()

        for tx in self.filtered(lambda t: t.state == 'cancel' and t.esim_recharge_id):
            recharge = tx.esim_recharge_id
            if recharge.state in ('draft', 'pending'):
                recharge.action_cancel()

    def _post_process_esim_order(self):
        """eSIM 订单支付成功后自动确认下单。"""
        for tx in self.filtered(lambda t: t.state == 'done' and t.esim_order_id):
            order = tx.esim_order_id
            if order.state != 'draft':
                continue
            try:
                order.action_confirm()
            except UserError as e:
                _logger.warning(
                    "eSIM order %s auto-confirm failed after payment: %s",
                    order.name, e,
                )

        for tx in self.filtered(lambda t: t.state == 'cancel' and t.esim_order_id):
            order = tx.esim_order_id
            if order.state == 'draft':
                order.write({'state': 'cancelled'})
                order.message_post(body=_("支付已取消，订单自动关闭。"))
