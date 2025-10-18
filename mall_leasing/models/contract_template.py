# -*- coding: utf-8 -*-
from odoo import api, fields, models

class MallLeasingContractTemplate(models.Model):
    _name = 'mall.leasing.contract.template'
    _description = '租赁合同模板'

    name = fields.Char('模板名称', required=True)
    contract_type = fields.Selection([
        ('landlord', '房东合同'),
        ('tenant', '租户合同'),
    ], string='合同类型', required=True)

    currency_id = fields.Many2one('res.currency', string='币种', default=lambda self: self.env.company.currency_id.id)

    rent_amount = fields.Monetary('租金', currency_field='currency_id')
    deposit = fields.Monetary('押金', currency_field='currency_id')
    water_fee = fields.Monetary('水费', currency_field='currency_id')
    electric_fee = fields.Monetary('电费', currency_field='currency_id')
    property_fee = fields.Monetary('物业费', currency_field='currency_id')
    garbage_fee = fields.Monetary('垃圾费', currency_field='currency_id')

    payment_frequency = fields.Selection([
        ('monthly', '月付'),
        ('quarterly', '季付'),
        ('yearly', '年付'),
    ], string='支付方式')
    payment_day = fields.Integer('支付日(1-31)', default=1)

    escalation_rate = fields.Float('递增率(%)')

    introducer_id = fields.Many2one('res.partner', string='默认介绍人')
    commission_type = fields.Selection([
        ('fixed', '固定金额'),
        ('percent', '租金比例'),
    ], string='中介费类型')
    commission_amount = fields.Float('中介费金额/比例')

    def action_create_contract(self):
        self.ensure_one()
        # 打开合同创建界面，使用模板字段作为默认值
        ctx = {
            'default_contract_type': self.contract_type,
            'default_currency_id': self.currency_id.id,
            'default_rent_amount': self.rent_amount,
            'default_deposit': self.deposit,
            'default_water_fee': self.water_fee,
            'default_electric_fee': self.electric_fee,
            'default_property_fee': self.property_fee,
            'default_garbage_fee': self.garbage_fee,
            'default_payment_frequency': self.payment_frequency,
            'default_payment_day': self.payment_day,
            'default_escalation_rate': self.escalation_rate,
            'default_introducer_id': self.introducer_id.id,
            'default_commission_type': self.commission_type,
            'default_commission_amount': self.commission_amount,
            'default_state': 'draft',
        }
        return {
            'type': 'ir.actions.act_window',
            'name': '新建合同（来自模板）',
            'res_model': 'mall.leasing.contract',
            'view_mode': 'form',
            'target': 'current',
            'context': ctx,
        }