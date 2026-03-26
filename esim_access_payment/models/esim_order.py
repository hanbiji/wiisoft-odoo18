# -*- coding: utf-8 -*-
import logging

from odoo import models, fields, _

_logger = logging.getLogger(__name__)


class EsimOrder(models.Model):
    _inherit = 'esim.order'

    is_paid_online = fields.Boolean(
        string="在线支付", default=False, readonly=True,
        help="标记此订单是否通过在线支付网关完成付款",
    )
    payment_transaction_ids = fields.Many2many(
        'payment.transaction', string="支付交易",
        relation='esim_order_payment_transaction_rel',
        column1='order_id', column2='transaction_id',
        readonly=True, copy=False,
    )

    def _confirm_deduct_balance(self) -> None:
        """在线支付订单无需扣除余额。"""
        if self.is_paid_online:
            return
        return super()._confirm_deduct_balance()

    def _confirm_refund_on_failure(self) -> None:
        """在线支付订单 API 下单失败时，将金额转入客户余额作为补偿。"""
        if self.is_paid_online:
            self.ensure_one()
            self.partner_id._esim_change_balance(
                log_type='topup',
                amount=self.total_amount,
                description=_("在线支付下单失败，金额转入余额: %s") % self.name,
                order_id=self.id,
            )
            self.message_post(
                body=_("eSIM API 下单失败，已将 $%.2f 转入客户余额。") % self.total_amount,
            )
            return
        return super()._confirm_refund_on_failure()
