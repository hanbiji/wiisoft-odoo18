# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class EsimRechargeOption(models.Model):
    """预设充值档位，管理员在后台配置可供门户客户选择的固定充值金额。"""

    _name = 'esim.recharge.option'
    _description = '充值档位'
    _order = 'sequence, id'

    name = fields.Char(string="名称", required=True)
    amount = fields.Float(
        string="金额", digits=(12, 2), required=True,
    )
    currency_id = fields.Many2one(
        'res.currency', string="币种", required=True,
        default=lambda self: self.env.company.currency_id,
    )
    sequence = fields.Integer(string="排序", default=10)
    active = fields.Boolean(string="有效", default=True)

    @api.depends('name', 'amount', 'currency_id')
    def _compute_display_name(self):
        for rec in self:
            symbol = rec.currency_id.symbol or ''
            rec.display_name = f"{rec.name} ({symbol}{rec.amount:.2f})"
