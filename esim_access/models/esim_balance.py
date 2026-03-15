# -*- coding: utf-8 -*-
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

BALANCE_LOG_TYPE_SELECTION = [
    ('topup', '充值'),
    ('consume', '消费'),
    ('refund', '退款'),
]


class ResPartner(models.Model):
    _inherit = 'res.partner'

    esim_balance = fields.Float(
        string="eSIM 余额", digits=(12, 2), default=0,
        help="客户用于购买 eSIM 套餐的账户余额",
    )
    esim_balance_log_ids = fields.One2many(
        'esim.balance.log', 'partner_id', string="余额变动记录",
    )

    def action_view_esim_balance_logs(self):
        """查看余额变动记录"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('余额变动记录'),
            'res_model': 'esim.balance.log',
            'view_mode': 'list,form',
            'domain': [('partner_id', '=', self.id)],
            'context': {'default_partner_id': self.id},
        }

    def _esim_change_balance(
        self,
        log_type: str,
        amount: float,
        description: str = '',
        order_id: int | None = None,
    ) -> 'EsimBalanceLog':
        """
        统一余额变更入口，保证余额与日志的原子一致性。
        - log_type: 'topup' / 'consume' / 'refund'
        - amount: 变动金额（正数），方向由 log_type 决定
        - description: 变动说明
        - order_id: 关联订单 ID（消费/退款时）
        返回创建的日志记录
        """
        self.ensure_one()
        if amount <= 0:
            raise UserError(_("变动金额必须大于 0"))

        balance_before = self.esim_balance
        if log_type == 'consume':
            if balance_before < amount:
                raise UserError(
                    _("余额不足：当前余额 $%.2f，需要 $%.2f") % (balance_before, amount)
                )
            balance_after = balance_before - amount
        elif log_type in ('topup', 'refund'):
            balance_after = balance_before + amount
        else:
            raise UserError(_("未知的余额变动类型: %s") % log_type)

        self.esim_balance = balance_after

        log = self.env['esim.balance.log'].create({
            'partner_id': self.id,
            'type': log_type,
            'amount': amount,
            'balance_before': balance_before,
            'balance_after': balance_after,
            'description': description,
            'order_id': order_id,
            'operator_id': self.env.uid,
        })
        return log


class EsimBalanceLog(models.Model):
    _name = 'esim.balance.log'
    _description = 'eSIM 余额变动记录'
    _order = 'create_date desc'

    name = fields.Char(
        string="编号", required=True, readonly=True,
        default=lambda self: _('New'), copy=False,
    )
    partner_id = fields.Many2one(
        'res.partner', string="客户", required=True,
        ondelete='cascade', index=True,
    )
    type = fields.Selection(
        BALANCE_LOG_TYPE_SELECTION, string="类型",
        required=True, readonly=True,
    )
    amount = fields.Float(
        string="金额", digits=(12, 2), required=True, readonly=True,
    )
    balance_before = fields.Float(
        string="变动前余额", digits=(12, 2), readonly=True,
    )
    balance_after = fields.Float(
        string="变动后余额", digits=(12, 2), readonly=True,
    )
    description = fields.Char(string="说明", readonly=True)
    order_id = fields.Many2one(
        'esim.order', string="关联订单",
        ondelete='set null', readonly=True,
    )
    operator_id = fields.Many2one(
        'res.users', string="操作人",
        default=lambda self: self.env.uid, readonly=True,
    )

    @api.model_create_multi
    def create(self, vals_list: list[dict]) -> 'EsimBalanceLog':
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('esim.balance.log') or _('New')
        return super().create(vals_list)

    @api.depends('name', 'type', 'amount')
    def _compute_display_name(self):
        type_map = dict(BALANCE_LOG_TYPE_SELECTION)
        for rec in self:
            rec.display_name = f"{rec.name} - {type_map.get(rec.type, '')} ${rec.amount:.2f}"
