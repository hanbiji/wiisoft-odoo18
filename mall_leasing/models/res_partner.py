# -*- coding: utf-8 -*-
from odoo import fields, models

class ResPartner(models.Model):
    _inherit = 'res.partner'

    is_tenant = fields.Boolean('是否为租户')
    # 新增字段：是否为运营
    is_operator = fields.Boolean('是否为运营')

    # 重命名字段以避免与标准type字段冲突
    industry_type = fields.Selection([
        ('retail', '零售'),
        ('catering', '餐饮'),
        ('service', '服务'),
        ('hostel', '酒店'),
        ('other_industry', '其他'),  # 改为other_industry避免与标准type字段的'other'选项冲突
    ], string='行业类型')

    leasing_contract_ids = fields.One2many('mall.leasing.contract', 'partner_id', string='关联租赁合同')
    communication_ids = fields.One2many('mall.communication', 'partner_id', string='沟通日志')