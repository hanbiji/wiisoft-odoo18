# -*- coding: utf-8 -*-
from odoo import fields, models

class ResPartner(models.Model):
    _inherit = 'res.partner'

    # 联系人类别
    mall_contact_type = fields.Selection([
        ('tenant', '租户'),
        ('operator', '运营公司(人)'),
        ('property_company', '物业公司'),
        ('landlord', '房东'),
    ], string='联系人类别')
    # 身份证号
    id_card = fields.Char('身份证号', tracking=True)

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