# -*- coding: utf-8 -*-
from odoo import api, fields, models

class Mall(models.Model):
    _name = 'mall.mall'
    _description = '商场项目'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    name = fields.Char('商场名称', required=True, index=True, tracking=True)
    code = fields.Char('商场编码', required=True, index=True, tracking=True)
    address = fields.Text('详细地址', tracking=True)
    city = fields.Char('城市', tracking=True)
    province = fields.Char('省份', tracking=True)
    postal_code = fields.Char('邮政编码')
    
    # 商场基本信息
    total_area = fields.Float('总建筑面积(㎡)', tracking=True)
    leasable_area = fields.Float('可租赁面积(㎡)', tracking=True)
    floors = fields.Integer('楼层数', tracking=True)
    opening_date = fields.Date('开业日期', tracking=True)
    
    # 商场状态
    status = fields.Selection([
        ('planning', '规划中'),
        ('construction', '建设中'),
        ('operating', '运营中'),
        ('renovation', '装修中'),
        ('closed', '已关闭'),
    ], string='状态', default='planning', tracking=True)
    
    # 联系信息
    manager_id = fields.Many2one('res.partner', string='商场经理', tracking=True)
    phone = fields.Char('联系电话')
    email = fields.Char('邮箱')
    website = fields.Char('官网')
    
    # 商场图片
    image_main = fields.Image('主图')
    image_gallery = fields.One2many('mall.mall.image', 'mall_id', string='图片库')
    
    # 关联数据
    facade_ids = fields.One2many('mall.facade', 'mall_id', string='门面列表')
    
    # 统计字段
    facade_count = fields.Integer('门面数量', compute='_compute_facade_stats', store=True)
    vacant_count = fields.Integer('空置门面数', compute='_compute_facade_stats', store=True)
    leased_count = fields.Integer('已租门面数', compute='_compute_facade_stats', store=True)
    expiring_count = fields.Integer('即将到期门面数', compute='_compute_facade_stats', store=True)
    occupancy_rate = fields.Float('出租率(%)', compute='_compute_facade_stats', store=True)
    
    # 财务统计
    total_rent_income = fields.Monetary('总租金收入', compute='_compute_financial_stats', store=True, currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', string='币种', default=lambda self: self.env.company.currency_id.id)
    
    _sql_constraints = [
        ('code_unique', 'unique(code)', '商场编码必须唯一。'),
        ('name_unique', 'unique(name)', '商场名称必须唯一。')
    ]

    @api.depends('facade_ids', 'facade_ids.status')
    def _compute_facade_stats(self):
        for mall in self:
            facades = mall.facade_ids
            mall.facade_count = len(facades)
            mall.vacant_count = len(facades.filtered(lambda f: f.status == 'vacant'))
            mall.leased_count = len(facades.filtered(lambda f: f.status == 'leased'))
            mall.expiring_count = len(facades.filtered(lambda f: f.status == 'expiring'))
            
            # 计算出租率
            if mall.facade_count > 0:
                mall.occupancy_rate = (mall.leased_count + mall.expiring_count) / mall.facade_count * 100
            else:
                mall.occupancy_rate = 0.0

    @api.depends('facade_ids', 'facade_ids.tenant_contract_id', 'facade_ids.tenant_contract_id.rent_amount')
    def _compute_financial_stats(self):
        for mall in self:
            total_rent = 0.0
            for facade in mall.facade_ids:
                if facade.tenant_contract_id and facade.tenant_contract_id.state == 'active':
                    total_rent += facade.tenant_contract_id.rent_amount or 0.0
            mall.total_rent_income = total_rent

    def action_view_facades(self):
        """查看商场下的所有门面"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'{self.name} - 门面列表',
            'res_model': 'mall.facade',
            'view_mode': 'kanban,list,form',
            'domain': [('mall_id', '=', self.id)],
            'context': {'default_mall_id': self.id},
        }

    def action_view_contracts(self):
        """查看商场下的所有合同"""
        self.ensure_one()
        facade_ids = self.facade_ids.ids
        return {
            'type': 'ir.actions.act_window',
            'name': f'{self.name} - 合同列表',
            'res_model': 'mall.leasing.contract',
            'view_mode': 'list,form',
            'domain': [('facade_id', 'in', facade_ids)],
        }

    def action_create_facade(self):
        """快速创建门面"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '新建门面',
            'res_model': 'mall.facade',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_mall_id': self.id},
        }


class MallImage(models.Model):
    _name = 'mall.mall.image'
    _description = '商场图片'
    _order = 'sequence, id'

    mall_id = fields.Many2one('mall.mall', string='商场', required=True, ondelete='cascade')
    name = fields.Char('图片名称', required=True)
    image = fields.Image('图片', required=True)
    sequence = fields.Integer('排序', default=10)
    description = fields.Text('描述')