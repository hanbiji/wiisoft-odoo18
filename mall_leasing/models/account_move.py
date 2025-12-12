# -*- coding: utf-8 -*-
from odoo import fields, models, api

class AccountMove(models.Model):
    _inherit = ['account.move']

    mall_contract_id = fields.Many2one('mall.leasing.contract', string='租赁合同')
    mall_facade_id = fields.Many2one('mall.facade', string='门面')
    
    # 开票信息
    is_invoiced = fields.Boolean('是否开票', default=False, tracking=True, help='标记该账单是否已开具发票')
    invoice_time = fields.Datetime('开票时间', tracking=True, help='实际开具发票的时间')
    
    @api.onchange('mall_contract_id')
    def _onchange_mall_contract_id(self):
        """当选择合同时，自动填充相关信息"""
        if self.mall_contract_id:
            self.partner_id = self.mall_contract_id.partner_id.id
            # 如果合同只关联一个门面，自动填充
            if len(self.mall_contract_id.facade_ids) == 1:
                self.mall_facade_id = self.mall_contract_id.facade_ids[0].id