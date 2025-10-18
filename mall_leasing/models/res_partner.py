# -*- coding: utf-8 -*-
from odoo import fields, models

class ResPartner(models.Model):
    _inherit = 'res.partner'

    is_tenant = fields.Boolean('是否为租户')
    industry_type = fields.Selection([
        ('retail', '零售'),
        ('catering', '餐饮'),
        ('service', '服务'),
        ('other', '其他'),
    ], string='行业类型')

    leasing_contract_ids = fields.One2many('mall.leasing.contract', 'partner_id', string='关联租赁合同')
    communication_ids = fields.One2many('mall.communication', 'partner_id', string='沟通日志')