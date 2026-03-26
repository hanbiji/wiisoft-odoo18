# -*- coding: utf-8 -*-
import logging

from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)

RECHARGE_STATE_SELECTION = [
    ('draft', '草稿'),
    ('pending', '待支付'),
    ('done', '已完成'),
    ('cancelled', '已取消'),
]


class EsimBalanceRecharge(models.Model):
    """在线充值订单，关联 payment.transaction 完成支付到账闭环。"""

    _name = 'esim.balance.recharge'
    _description = 'eSIM 在线充值'
    _inherit = ['mail.thread']
    _order = 'create_date desc'

    name = fields.Char(
        string="编号", required=True, readonly=True,
        default=lambda self: _('New'), copy=False,
    )
    partner_id = fields.Many2one(
        'res.partner', string="客户", required=True,
        ondelete='restrict', index=True,
    )
    amount = fields.Float(
        string="充值金额", digits=(12, 2), required=True,
    )
    currency_id = fields.Many2one(
        'res.currency', string="币种", required=True,
    )
    state = fields.Selection(
        RECHARGE_STATE_SELECTION, string="状态",
        default='draft', required=True, tracking=True,
    )
    option_id = fields.Many2one(
        'esim.recharge.option', string="充值档位",
        ondelete='set null', readonly=True,
    )
    transaction_ids = fields.Many2many(
        'payment.transaction', string="支付交易",
        relation='esim_recharge_transaction_rel',
        column1='recharge_id', column2='transaction_id',
        readonly=True, copy=False,
    )
    balance_log_id = fields.Many2one(
        'esim.balance.log', string="余额变动记录",
        ondelete='set null', readonly=True,
    )

    @api.model_create_multi
    def create(self, vals_list: list[dict]) -> 'EsimBalanceRecharge':
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = (
                    self.env['ir.sequence'].next_by_code('esim.balance.recharge')
                    or _('New')
                )
        return super().create(vals_list)

    def action_credit_balance(self) -> None:
        """将充值金额入账到客户余额，仅在首次到账时执行。"""
        self.ensure_one()
        if self.state == 'done':
            return
        partner = self.partner_id.sudo()
        log = partner._esim_change_balance(
            'topup',
            self.amount,
            _("在线充值 %s", self.name),
        )
        self.write({
            'state': 'done',
            'balance_log_id': log.id,
        })
        _logger.info(
            "Recharge %s credited %.2f to partner %s",
            self.name, self.amount, partner.id,
        )

    def action_cancel(self) -> None:
        """取消充值单（仅草稿/待支付状态可取消）。"""
        for rec in self:
            if rec.state in ('draft', 'pending'):
                rec.state = 'cancelled'
