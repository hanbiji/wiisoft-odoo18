# -*- coding: utf-8 -*-
from odoo import api, fields, models

class MallLeasingContractPayment(models.Model):
    _name = 'mall.leasing.contract.payment'
    _description = '合同付款记录'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'payment_date desc, id desc'

    contract_id = fields.Many2one(
        'mall.leasing.contract', string='合同', required=True, ondelete='cascade', index=True
    )
    payment_item = fields.Selection([
        ('rent', '租金'),
        ('deposit', '押金'),
        ('property_fee', '物业费'),
        ('management_fee', '管理费'),
        ('other', '其他'),
    ],string='付款项目', required=True)

    amount = fields.Monetary('应付金额', currency_field='currency_id', required=True)
    # 实际付款金额
    actual_amount = fields.Monetary('实际付款金额', currency_field='currency_id')
    # 未付款金额 = 应付金额 - 实际付款金额
    unpaid_amount = fields.Monetary('未付款金额', currency_field='currency_id', compute='_compute_unpaid_amount', store=True)

    @api.depends('amount', 'actual_amount')
    def _compute_unpaid_amount(self):
        for record in self:
            record.unpaid_amount = record.amount - record.actual_amount
    # 付款状态
    payment_status = fields.Selection([
        ('unpaid', '未付款'),
        ('paid', '已付款'),
    ], string='付款状态', default='unpaid', required=True, tracking=True)
    currency_id = fields.Many2one(
        'res.currency', string='币种', related='contract_id.currency_id', store=True, readonly=True
    )
    period = fields.Char(string='付款周期', required=True, tracking=True)

    payment_date = fields.Date('付款时间', tracking=True)

    _sql_constraints = [
        ('amount_non_negative', 'CHECK(amount >= 0)', '金额不能为负数。'),
    ]