# -*- coding: utf-8 -*-
from odoo import fields, models, api

class AccountMove(models.Model):
    _inherit = 'account.move'

    mall_contract_id = fields.Many2one('mall.leasing.contract', string='租赁合同')
    mall_facade_id = fields.Many2one('mall.facade', string='门面')
    
    @api.onchange('mall_contract_id')
    def _onchange_mall_contract_id(self):
        """当选择合同时，自动填充相关信息"""
        if self.mall_contract_id:
            self.partner_id = self.mall_contract_id.partner_id.id
            # 如果合同只关联一个门面，自动填充
            if len(self.mall_contract_id.facade_ids) == 1:
                self.mall_facade_id = self.mall_contract_id.facade_ids[0].id