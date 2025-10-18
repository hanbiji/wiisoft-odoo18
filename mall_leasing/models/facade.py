# -*- coding: utf-8 -*-
from odoo import api, fields, models
from datetime import date

class MallFacade(models.Model):
    _name = 'mall.facade'
    _description = '商场门面'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char('编号', required=True, index=True, tracking=True)
    address = fields.Char('地址', tracking=True)
    area = fields.Float('面积(㎡)', tracking=True)
    floor = fields.Char('楼层', tracking=True)
    layout_plan = fields.Binary('户型图')
    image_main = fields.Image('主图')

    contract_ids = fields.One2many('mall.leasing.contract', 'facade_id', string='合同')
    landlord_contract_id = fields.Many2one(
        'mall.leasing.contract', string='房东合同',
        domain="[('contract_type','=','landlord'),('state','=','active'),('facade_id','=',id)]",
        compute='_compute_current_contracts', store=True)
    tenant_contract_id = fields.Many2one(
        'mall.leasing.contract', string='租户合同',
        domain="[('contract_type','=','tenant'),('state','=','active'),('facade_id','=',id)]",
        compute='_compute_current_contracts', store=True)

    status = fields.Selection([
        ('vacant', '空置'),
        ('leased', '已租'),
        ('expiring', '即将到期'),
    ], string='现状', compute='_compute_status', store=True)

    _sql_constraints = [
        ('name_unique', 'unique(name)', '门面编号必须唯一。')
    ]

    @api.depends('contract_ids.state', 'contract_ids.contract_type', 'contract_ids.lease_end_date')
    def _compute_current_contracts(self):
        for rec in self:
            landlord = rec.contract_ids.filtered(lambda c: c.contract_type == 'landlord' and c.state == 'active')
            tenant = rec.contract_ids.filtered(lambda c: c.contract_type == 'tenant' and c.state == 'active')
            rec.landlord_contract_id = landlord[:1].id
            rec.tenant_contract_id = tenant[:1].id

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
            'view_mode': 'form,tree',
            'domain': [('facade_id', '=', self.id), ('contract_type', '=', 'landlord')],
        }

    def action_view_tenant_contract(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '租户合同',
            'res_model': 'mall.leasing.contract',
            'view_mode': 'form,tree',
            'domain': [('facade_id', '=', self.id), ('contract_type', '=', 'tenant')],
        }