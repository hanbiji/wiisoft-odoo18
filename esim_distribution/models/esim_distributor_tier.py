# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class EsimDistributorTier(models.Model):
    _name = 'esim.distributor.tier'
    _description = 'eSIM 分销等级'
    _order = 'sequence, id'

    name = fields.Char(string="等级名称", required=True, translate=True)
    code = fields.Char(string="等级编码", required=True)
    sequence = fields.Integer(string="等级顺序", default=10)
    commission_rate = fields.Float(
        string="佣金比例 (%)", digits=(5, 2), required=True,
        help="按订单销售额计算的返佣比例。",
    )
    min_sales_amount = fields.Float(
        string="最低累计销售额", digits=(12, 2), default=0,
        help="分销商已结算订单销售额达到该金额后可升级到此等级。",
    )
    min_referral_count = fields.Integer(
        string="最低有效订单数", default=0,
        help="分销商已结算订单数达到该数量后可升级到此等级。",
    )
    is_default = fields.Boolean(
        string="默认等级",
        help="分销商审核通过且未指定等级时使用的初始等级。",
    )
    active = fields.Boolean(string="启用", default=True)
    description = fields.Text(string="说明")

    _sql_constraints = [
        ('code_uniq', 'UNIQUE(code)', '分销等级编码不能重复。'),
        ('commission_rate_range',
         'CHECK(commission_rate >= 0 AND commission_rate <= 100)',
         '佣金比例必须在 0 到 100 之间。'),
        ('min_sales_amount_positive',
         'CHECK(min_sales_amount >= 0)',
         '最低累计销售额不能为负数。'),
        ('min_referral_count_positive',
         'CHECK(min_referral_count >= 0)',
         '最低有效订单数不能为负数。'),
    ]

    @api.constrains('is_default')
    def _check_single_default(self) -> None:
        for tier in self.filtered('is_default'):
            duplicate = self.search_count([
                ('is_default', '=', True),
                ('id', '!=', tier.id),
            ])
            if duplicate:
                raise ValidationError(_("只能设置一个默认分销等级。"))

    @api.depends('name', 'commission_rate')
    def _compute_display_name(self) -> None:
        for tier in self:
            tier.display_name = _("%(name)s (%(rate).2f%%)") % {
                'name': tier.name,
                'rate': tier.commission_rate,
            }

    @api.model
    def _get_default_tier(self) -> 'EsimDistributorTier':
        """返回审核通过分销商使用的默认等级。"""
        return self.search([('is_default', '=', True), ('active', '=', True)], limit=1)
