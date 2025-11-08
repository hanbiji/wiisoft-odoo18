# -*- coding: utf-8 -*-
from odoo import api, fields, models

class MallCommunication(models.Model):
    _name = 'mall.communication'
    _description = '租户沟通日志'
    _inherit = ['mail.thread']

    partner_id = fields.Many2one('res.partner', string='租户', required=True, tracking=True)
    contract_id = fields.Many2one('mall.leasing.contract', string='关联合同')
    date = fields.Datetime('沟通时间', default=fields.Datetime.now)
    method = fields.Selection([
        ('call', '电话'),
        ('visit', '拜访'),
        ('msg', '消息'),
        ('other', '其他'),
    ], string='方式')
    content = fields.Text('沟通内容')
    user_id = fields.Many2one('res.users', string='记录人', default=lambda self: self.env.user)