# -*- coding: utf-8 -*-
# Copyright 2025 WiiSoft
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl.html).

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from datetime import datetime, timedelta


class ClothingDevelopmentRequest(models.Model):
    """服装开发申请模型
    
    用于管理服装开发申请的完整生命周期，包括申请创建、审批流程、状态跟踪等功能。
    """
    _name = 'clothing.development.request'
    _description = '服装开发申请'
    _order = 'create_date desc'
    _rec_name = 'name'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    
    # ========== 基本信息字段 ==========
    name = fields.Char(
        string='申请编号',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
        help='系统自动生成的唯一申请编号'
    )
    
    year = fields.Selection([
        ('2025', '2025'),
        ('2026', '2026'),
        ('2027', '2027'),
        ('2028', '2028'),
        ('2029', '2029'),
        ('2030', '2030')
    ], string='年份', help='服装开发的年份', required=True)
    
    batch = fields.Char(
        string='批次',
        help='服装开发的批次编号'
    )
    
    style_number = fields.Char(
        string='款号',
        help='服装的款式编号'
    )
    
    description = fields.Text(
        string='详细描述',
        required=True,
        help='详细描述服装开发需求、设计理念、功能要求等'
    )
    
    # ========== 申请人信息 ==========
    applicant_id = fields.Many2one(
        'res.users',
        string='申请人',
        required=True,
        default=lambda self: self.env.user,
        tracking=True,
        help='提交申请的用户'
    )
    
    department_id = fields.Many2one(
        'hr.department',
        string='部门',
        related='applicant_id.department_id',
        store=True,
        help='申请人所属部门'
    )
    
    # ========== 服装信息 ==========
    # 服装品牌
    brand = fields.Selection([
        ('GS', 'GSOUSNOW'),
        ('OT', '其他')
    ], string='服装品牌', required=True, help='选择要开发的服装品牌')

    clothing_type = fields.Selection([
        ('shirt', '衬衫'),
        ('pants', '裤子'),
        ('dress', '连衣裙'),
        ('jacket', '外套'),
        ('skirt', '裙子'),
        ('suit', '套装'),
        ('accessories', '配饰'),
        ('other', '其他')
    ], string='服装类型', required=True, tracking=True, help='选择要开发的服装类型')
    
    target_season = fields.Selection([
        ('spring', '春季'),
        ('summer', '夏季'),
        ('autumn', '秋季'),
        ('winter', '冬季'),
        ('all_season', '四季通用')
    ], string='目标季节', required=True, help='该服装适用的季节')
    
    color_id = fields.Many2one(
        'clothing.color',
        string='主要颜色',
        help='服装的主要颜色'
    )
    
    secondary_color_ids = fields.Many2many(
        'clothing.color',
        string='次要颜色',
        help='服装的次要颜色或配色方案'
    )
    
    design_requirements = fields.Text(
        string='设计要求',
        help='详细的设计要求和规格说明'
    )
    
    target_gender = fields.Selection([
        ('male', '男性'),
        ('female', '女性'),
        ('unisex', '中性')
    ], string='目标性别', required=True, help='该服装的目标客户群体性别')
    
    size_range = fields.Char(
        string='尺码范围',
        help='例如：S-XXL 或 XS-L'
    )
    
    estimated_cost = fields.Float(
        string='预估成本',
        digits='Product Price',
        help='单件服装的预估生产成本（元）'
    )
    
    target_price = fields.Float(
        string='目标售价',
        digits='Product Price',
        help='单件服装的目标销售价格（元）'
    )
    
    actual_cost = fields.Float(
        string='实际成本',
        digits='Product Price',
        help='单件服装的实际生产成本（元）'
    )
    
    cost_variance = fields.Float(
        string='成本差异',
        compute='_compute_cost_variance',
        store=True,
        digits='Product Price',
        help='实际成本与预估成本的差异（元）'
    )
    
    # ========== 时间管理 ==========
    expected_start_date = fields.Date(
        string='期望开始日期',
        required=True,
        default=fields.Date.today,
        help='期望开始开发的日期'
    )
    
    expected_completion_date = fields.Date(
        string='期望完成日期',
        required=True,
        help='期望完成开发的日期'
    )
    
    actual_start_date = fields.Date(
        string='实际开始日期',
        help='实际开始开发的日期'
    )
    
    actual_completion_date = fields.Date(
        string='实际完成日期',
        help='实际完成开发的日期'
    )
    
    # ========== 审批流程 ==========
    state = fields.Selection([
        ('draft', '草稿'),
        ('submitted', '已提交'),
        ('under_review', '审核中'),
        ('approved', '已批准'),
        ('rejected', '已拒绝'),
        ('in_development', '开发中'),
        ('completed', '已完成'),
        ('cancelled', '已取消')
    ], string='状态', default='draft', required=True, tracking=True, help='申请当前状态')
    
    priority = fields.Selection([
        ('low', '低'),
        ('normal', '普通'),
        ('high', '高'),
        ('urgent', '紧急')
    ], string='优先级', default='normal', required=True, tracking=True, help='申请优先级')
    
    # ========== 审批人员 ==========
    reviewer_id = fields.Many2one(
        'res.users',
        string='审核人',
        tracking=True,
        help='负责审核此申请的用户'
    )
    
    approver_id = fields.Many2one(
        'res.users',
        string='批准人',
        tracking=True,
        help='最终批准此申请的用户'
    )
    
    review_date = fields.Datetime(
        string='审核日期',
        help='审核完成的日期和时间'
    )
    
    approval_date = fields.Datetime(
        string='批准日期',
        help='批准完成的日期和时间'
    )
    
    # ========== 审批意见 ==========
    review_notes = fields.Text(
        string='审核意见',
        help='审核人员的意见和建议'
    )
    
    approval_notes = fields.Text(
        string='批准意见',
        help='批准人员的意见和建议'
    )
    
    rejection_reason = fields.Text(
        string='拒绝原因',
        help='申请被拒绝的具体原因'
    )
    
    # ========== 附件和文档 ==========
    attachment_ids = fields.Many2many(
        'ir.attachment',
        string='附件',
        help='相关的设计图、参考资料等附件'
    )
    
    notes = fields.Text(
        string='备注',
        help='其他备注信息'
    )
    
    # ========== 计算字段 ==========
    duration_days = fields.Integer(
        string='预计工期（天）',
        compute='_compute_duration_days',
        store=True,
        help='从开始日期到完成日期的天数'
    )
    
    is_overdue = fields.Boolean(
        string='是否逾期',
        compute='_compute_is_overdue',
        help='是否超过了期望完成日期'
    )
    
    progress_percentage = fields.Float(
        string='进度百分比',
        compute='_compute_progress_percentage',
        help='基于状态计算的进度百分比'
    )
    
    # ========== 约束条件 ==========
    @api.constrains('expected_start_date', 'expected_completion_date')
    def _check_dates(self):
        """检查日期的合理性"""
        for record in self:
            if record.expected_start_date and record.expected_completion_date:
                if record.expected_start_date > record.expected_completion_date:
                    raise ValidationError(_('期望开始日期不能晚于期望完成日期！'))
    
    @api.constrains('estimated_cost', 'target_price')
    def _check_prices(self):
        """检查价格的合理性"""
        for record in self:
            if record.estimated_cost < 0:
                raise ValidationError(_('预估成本不能为负数！'))
            if record.target_price < 0:
                raise ValidationError(_('目标售价不能为负数！'))
            if record.estimated_cost > 0 and record.target_price > 0:
                if record.estimated_cost >= record.target_price:
                    raise ValidationError(_('目标售价应该高于预估成本！'))
    
    # ========== 计算方法 ==========
    @api.depends('expected_start_date', 'expected_completion_date')
    def _compute_duration_days(self):
        """计算预计工期"""
        for record in self:
            if record.expected_start_date and record.expected_completion_date:
                delta = record.expected_completion_date - record.expected_start_date
                record.duration_days = delta.days + 1
            else:
                record.duration_days = 0
    
    @api.depends('expected_completion_date', 'state')
    def _compute_is_overdue(self):
        """计算是否逾期"""
        today = fields.Date.today()
        for record in self:
            if record.expected_completion_date and record.state not in ['completed', 'cancelled', 'rejected']:
                record.is_overdue = today > record.expected_completion_date
            else:
                record.is_overdue = False
    
    @api.depends('estimated_cost', 'actual_cost')
    def _compute_cost_variance(self):
        """计算成本差异"""
        for record in self:
            if record.estimated_cost and record.actual_cost:
                record.cost_variance = record.actual_cost - record.estimated_cost
            else:
                record.cost_variance = 0.0
    
    @api.depends('state')
    def _compute_progress_percentage(self):
        """根据状态计算进度百分比"""
        state_progress = {
            'draft': 0,
            'submitted': 10,
            'under_review': 20,
            'approved': 30,
            'in_development': 70,
            'completed': 100,
            'rejected': 0,
            'cancelled': 0
        }
        for record in self:
            record.progress_percentage = state_progress.get(record.state, 0)
    
    # ========== 生命周期方法 ==========
    @api.model_create_multi
    def create(self, vals_list):
        """创建记录时自动生成编号，支持批量创建"""
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('clothing.development.request') or _('New')
        return super(ClothingDevelopmentRequest, self).create(vals_list)
    
    # ========== 业务方法 ==========
    def action_submit(self):
        """提交申请"""
        for record in self:
            if record.state != 'draft':
                raise UserError(_('只有草稿状态的申请才能提交！'))
            record.write({
                'state': 'submitted'
            })
            record.message_post(body=_('申请已提交，等待审核。'))
    
    def action_start_review(self):
        """开始审核"""
        for record in self:
            if record.state != 'submitted':
                raise UserError(_('只有已提交的申请才能开始审核！'))
            record.write({
                'state': 'under_review',
                'reviewer_id': self.env.user.id,
                'review_date': fields.Datetime.now()
            })
            record.message_post(body=_('申请审核已开始。'))
    
    def action_approve(self):
        """批准申请"""
        for record in self:
            if record.state != 'under_review':
                raise UserError(_('只有审核中的申请才能批准！'))
            record.write({
                'state': 'approved',
                'approver_id': self.env.user.id,
                'approval_date': fields.Datetime.now()
            })
            record.message_post(body=_('申请已批准，可以开始开发。'))
    
    def action_reject(self):
        """拒绝申请"""
        for record in self:
            if record.state not in ['submitted', 'under_review']:
                raise UserError(_('只有已提交或审核中的申请才能拒绝！'))
            record.write({
                'state': 'rejected'
            })
            record.message_post(body=_('申请已被拒绝。'))
    
    def action_start_development(self):
        """开始开发"""
        for record in self:
            if record.state != 'approved':
                raise UserError(_('只有已批准的申请才能开始开发！'))
            record.write({
                'state': 'in_development',
                'actual_start_date': fields.Date.today()
            })
            record.message_post(body=_('开发工作已开始。'))
    
    def action_complete(self):
        """完成开发"""
        for record in self:
            if record.state != 'in_development':
                raise UserError(_('只有开发中的申请才能标记为完成！'))
            record.write({
                'state': 'completed',
                'actual_completion_date': fields.Date.today()
            })
            record.message_post(body=_('开发工作已完成。'))
    
    def action_cancel(self):
        """取消申请"""
        for record in self:
            if record.state in ['completed']:
                raise UserError(_('已完成的申请不能取消！'))
            record.write({
                'state': 'cancelled'
            })
            record.message_post(body=_('申请已取消。'))
    
    def action_reset_to_draft(self):
        """重置为草稿"""
        for record in self:
            if record.state not in ['rejected', 'cancelled']:
                raise UserError(_('只有被拒绝或已取消的申请才能重置为草稿！'))
            record.write({
                'state': 'draft',
                'reviewer_id': False,
                'approver_id': False,
                'review_date': False,
                'approval_date': False,
                'review_notes': False,
                'approval_notes': False,
                'rejection_reason': False
            })
            record.message_post(body=_('申请已重置为草稿状态。'))