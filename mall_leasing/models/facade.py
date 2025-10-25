# -*- coding: utf-8 -*-
from odoo import api, fields, models
from datetime import date

class MallFacade(models.Model):
    _name = 'mall.facade'
    _description = '商场门面'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char('编号', required=True, index=True, tracking=True)
    mall_id = fields.Many2one('mall.mall', string='所属商场', required=True, index=True, tracking=True)
    address = fields.Char('地址', tracking=True)
    area = fields.Float('面积(㎡)', tracking=True)
    floor = fields.Char('楼层', tracking=True)
    layout_plan = fields.Binary('户型图')
    image_main = fields.Image('主图')
    
    # 门面位置信息
    zone = fields.Char('区域', help='如：A区、B区、中庭等')
    position = fields.Char('位置描述', help='如：临街、内铺、转角等')
    
    # 门面特征
    facade_type = fields.Selection([
        ('shop', '商铺'),
        ('restaurant', '餐饮'),
        ('office', '办公'),
        ('warehouse', '仓储'),
        ('other', '其他'),
    ], string='门面类型', tracking=True)
    
    # 设施配套
    has_water = fields.Boolean('有上下水', default=True)
    has_electricity = fields.Boolean('有电力', default=True)
    has_gas = fields.Boolean('有燃气', default=False)
    has_air_conditioning = fields.Boolean('有空调', default=False)
    
    # 商场信息（关联字段）
    mall_name = fields.Char('商场名称', related='mall_id.name', store=True, readonly=True)
    mall_status = fields.Selection(related='mall_id.status', string='商场状态', store=True, readonly=True)

    # 与合同的关联改为多对多
    contract_ids = fields.Many2many('mall.leasing.contract', 'mall_contract_facade_rel', 'facade_id', 'contract_id', string='合同')
    landlord_contract_id = fields.Many2one(
        'mall.leasing.contract', string='房东合同',
        domain="[('contract_type','=','landlord'),('state','in',['approved','signed','active'])]",
        compute='_compute_current_contracts', store=True)
    tenant_contract_id = fields.Many2one(
        'mall.leasing.contract', string='租赁合同',
        domain="[('contract_type','=','tenant'),('state','in',['approved','signed','active'])]",
        compute='_compute_current_contracts', store=True)
    tenant_partner_id = fields.Many2one('res.partner', string='承租人', related='tenant_contract_id.partner_id', store=True, readonly=True)
    property_contract_id = fields.Many2one(
        'mall.leasing.contract', string='物业合同',
        domain="[('contract_type','=','property'),('state','in',['approved','signed','active'])]",
        compute='_compute_current_contracts', store=True)

    status = fields.Selection([
        ('vacant', '空置'),
        ('leased', '已租'),
        ('expiring', '即将到期'),
    ], string='现状', compute='_compute_status', store=True)

    _sql_constraints = [
        ('name_mall_unique', 'unique(name, mall_id)', '同一商场内门面编号必须唯一。')
    ]

    @api.depends('contract_ids.state', 'contract_ids.contract_type', 'contract_ids.lease_end_date')
    def _compute_current_contracts(self):
        for rec in self:
            # 有效的合同状态：已审批、已签约、执行中
            valid_states = ['approved', 'signed', 'active']
            landlord = rec.contract_ids.filtered(lambda c: c.contract_type == 'landlord' and c.state in valid_states)
            tenant = rec.contract_ids.filtered(lambda c: c.contract_type == 'tenant' and c.state in valid_states)
            property = rec.contract_ids.filtered(lambda c: c.contract_type == 'property' and c.state in valid_states)
            rec.landlord_contract_id = landlord[:1].id
            rec.tenant_contract_id = tenant[:1].id
            rec.property_contract_id = property[:1].id

    @api.depends('tenant_contract_id', 'tenant_contract_id.lease_end_date', 'contract_ids')
    def _compute_status(self):
        today = date.today()
        for rec in self:
            if rec.tenant_contract_id:
                end = rec.tenant_contract_id.lease_end_date
                if end:
                    days = (end - today).days
                    rec.status = 'expiring' if days <= 30 and days >= 0 else 'leased'
                else:
                    rec.status = 'leased'
            else:
                rec.status = 'vacant'

    def action_view_landlord_contract(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '房东合同',
            'res_model': 'mall.leasing.contract',
            'view_mode': 'list,form',
            'domain': [('facade_ids', 'in', [self.id]), ('contract_type', '=', 'landlord')],
        }

    def action_view_tenant_contract(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '租户合同',
            'res_model': 'mall.leasing.contract',
            'view_mode': 'list,form',
            'domain': [('facade_ids', 'in', [self.id]), ('contract_type', '=', 'tenant')],
        }
    
    def action_view_property_contract(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '物业合同',
            'res_model': 'mall.leasing.contract',
            'view_mode': 'list,form',
            'domain': [('facade_ids', 'in', [self.id]), ('contract_type', '=', 'property')],
        }