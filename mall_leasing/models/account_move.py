# -*- coding: utf-8 -*-
from odoo import fields, models

class AccountMove(models.Model):
    _inherit = 'account.move'

    mall_contract_id = fields.Many2one('mall.leasing.contract', string='租赁合同')
    mall_facade_id = fields.Many2one('mall.facade', string='门面')