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
    
    thumbnail = fields.Binary(
        string='缩略图',
        help='服装设计的缩略图或效果图',
        attachment=True
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
        ('product_review', '产品经理审核'),
        ('design', '设计阶段'),
        ('design_review', '设计审核'),
        ('pattern_making', '版型制作'),
        ('pattern_review', '版型审核'),
        ('sample_making', '样衣制作'),
        ('sample_review', '样衣审核'),
        ('final_approval', '最终审批'),
        ('approved', '已批准'),
        ('rejected', '已拒绝'),
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
    
    # ========== 角色分配 ==========
    current_handler_id = fields.Many2one(
        'res.users',
        string='当前处理人',
        tracking=True,
        help='当前阶段的负责处理人员'
    )
    
    product_manager_id = fields.Many2one(
        'res.users',
        string='产品经理',
        tracking=True,
        help='负责产品规划和最终审批的产品经理'
    )
    
    designer_id = fields.Many2one(
        'res.users',
        string='设计师',
        tracking=True,
        help='负责设计方案制定的设计师'
    )
    
    pattern_maker_id = fields.Many2one(
        'res.users',
        string='版师',
        tracking=True,
        help='负责版型制作的版师'
    )
    
    sample_worker_id = fields.Many2one(
        'res.users',
        string='样衣工',
        tracking=True,
        help='负责样衣制作的样衣工'
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
            'product_review': 15,
            'design': 25,
            'design_review': 35,
            'pattern_making': 50,
            'pattern_review': 60,
            'sample_making': 75,
            'sample_review': 85,
            'final_approval': 90,
            'approved': 95,
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
            # 自动分配产品经理作为当前处理人
            current_handler = record.product_manager_id or self._get_default_product_manager()
            record.write({
                'state': 'submitted',
                'current_handler_id': current_handler.id if current_handler else False
            })
            record.message_post(body=_('申请已提交，等待产品经理审核。'))
    
    def action_product_review(self):
        """产品经理开始审核"""
        for record in self:
            if record.state != 'submitted':
                raise UserError(_('只有已提交的申请才能开始产品审核！'))
            if not self.env.user.has_group('clothing_development_approval.group_product_manager'):
                raise UserError(_('只有产品经理才能执行此操作！'))
            record.write({
                'state': 'product_review',
                'reviewer_id': self.env.user.id,
                'review_date': fields.Datetime.now(),
                'current_handler_id': self.env.user.id
            })
            record.message_post(body=_('产品经理审核已开始。'))
    
    def action_approve_to_design(self):
        """批准进入设计阶段"""
        for record in self:
            if record.state != 'product_review':
                raise UserError(_('只有产品审核中的申请才能批准进入设计阶段！'))
            if not self.env.user.has_group('clothing_development_approval.group_product_manager'):
                raise UserError(_('只有产品经理才能执行此操作！'))
            # 分配设计师作为当前处理人
            current_handler = record.designer_id or self._get_default_designer()
            record.write({
                'state': 'design',
                'current_handler_id': current_handler.id if current_handler else False
            })
            record.message_post(body=_('申请已批准进入设计阶段。'))
    
    def action_design_complete(self):
        """设计完成，提交审核"""
        for record in self:
            if record.state != 'design':
                raise UserError(_('只有设计阶段的申请才能提交设计审核！'))
            if not self.env.user.has_group('clothing_development_approval.group_designer'):
                raise UserError(_('只有设计师才能执行此操作！'))
            # 分配产品经理进行设计审核
            current_handler = record.product_manager_id or self._get_default_product_manager()
            record.write({
                'state': 'design_review',
                'current_handler_id': current_handler.id if current_handler else False
            })
            record.message_post(body=_('设计已完成，等待产品经理审核。'))
    
    def action_approve_to_pattern(self):
        """批准进入版型制作阶段"""
        for record in self:
            if record.state != 'design_review':
                raise UserError(_('只有设计审核中的申请才能批准进入版型制作阶段！'))
            if not self.env.user.has_group('clothing_development_approval.group_product_manager'):
                raise UserError(_('只有产品经理才能执行此操作！'))
            # 分配版师作为当前处理人
            current_handler = record.pattern_maker_id or self._get_default_pattern_maker()
            record.write({
                'state': 'pattern_making',
                'current_handler_id': current_handler.id if current_handler else False
            })
            record.message_post(body=_('设计已批准，进入版型制作阶段。'))
    
    def action_pattern_complete(self):
        """版型制作完成，提交审核"""
        for record in self:
            if record.state != 'pattern_making':
                raise UserError(_('只有版型制作阶段的申请才能提交版型审核！'))
            if not self.env.user.has_group('clothing_development_approval.group_pattern_maker'):
                raise UserError(_('只有版师才能执行此操作！'))
            # 分配产品经理进行版型审核
            current_handler = record.product_manager_id or self._get_default_product_manager()
            record.write({
                'state': 'pattern_review',
                'current_handler_id': current_handler.id if current_handler else False
            })
            record.message_post(body=_('版型制作已完成，等待产品经理审核。'))
    
    def action_approve_to_sample(self):
        """批准进入样衣制作阶段"""
        for record in self:
            if record.state != 'pattern_review':
                raise UserError(_('只有版型审核中的申请才能批准进入样衣制作阶段！'))
            if not self.env.user.has_group('clothing_development_approval.group_product_manager'):
                raise UserError(_('只有产品经理才能执行此操作！'))
            # 分配样衣工作为当前处理人
            current_handler = record.sample_worker_id or self._get_default_sample_worker()
            record.write({
                'state': 'sample_making',
                'current_handler_id': current_handler.id if current_handler else False,
                'actual_start_date': fields.Date.today()
            })
            record.message_post(body=_('版型已批准，进入样衣制作阶段。'))
    
    def action_sample_complete(self):
        """样衣制作完成，提交审核"""
        for record in self:
            if record.state != 'sample_making':
                raise UserError(_('只有样衣制作阶段的申请才能提交样衣审核！'))
            if not self.env.user.has_group('clothing_development_approval.group_sample_worker'):
                raise UserError(_('只有样衣工才能执行此操作！'))
            # 分配产品经理进行样衣审核
            current_handler = record.product_manager_id or self._get_default_product_manager()
            record.write({
                'state': 'sample_review',
                'current_handler_id': current_handler.id if current_handler else False
            })
            record.message_post(body=_('样衣制作已完成，等待产品经理审核。'))
    
    def action_final_approval(self):
        """进入最终审批"""
        for record in self:
            if record.state != 'sample_review':
                raise UserError(_('只有样衣审核中的申请才能进入最终审批！'))
            if not self.env.user.has_group('clothing_development_approval.group_product_manager'):
                raise UserError(_('只有产品经理才能执行此操作！'))
            record.write({
                'state': 'final_approval',
                'current_handler_id': self.env.user.id
            })
            record.message_post(body=_('样衣已通过审核，进入最终审批阶段。'))
    
    def action_approve(self):
        """最终批准"""
        for record in self:
            if record.state != 'final_approval':
                raise UserError(_('只有最终审批阶段的申请才能批准！'))
            if not self.env.user.has_group('clothing_development_approval.group_product_manager'):
                raise UserError(_('只有产品经理才能执行此操作！'))
            record.write({
                'state': 'approved',
                'approver_id': self.env.user.id,
                'approval_date': fields.Datetime.now(),
                'current_handler_id': False
            })
            record.message_post(body=_('申请已最终批准，可以投入生产。'))
    
    def action_complete(self):
        """完成开发"""
        for record in self:
            if record.state != 'approved':
                raise UserError(_('只有已批准的申请才能标记为完成！'))
            record.write({
                'state': 'completed',
                'actual_completion_date': fields.Date.today(),
                'current_handler_id': False
            })
            record.message_post(body=_('开发工作已完成。'))
    
    def action_reject(self):
        """拒绝申请"""
        for record in self:
            if record.state in ['completed', 'cancelled']:
                raise UserError(_('已完成或已取消的申请不能拒绝！'))
            # 检查权限
            if record.state in ['submitted', 'product_review', 'design_review', 'pattern_review', 'sample_review', 'final_approval']:
                if not self.env.user.has_group('clothing_development_approval.group_product_manager'):
                    raise UserError(_('只有产品经理才能拒绝此申请！'))
            record.write({
                'state': 'rejected',
                'current_handler_id': False
            })
            record.message_post(body=_('申请已被拒绝。'))
    
    def action_cancel(self):
        """取消申请"""
        for record in self:
            if record.state in ['completed']:
                raise UserError(_('已完成的申请不能取消！'))
            record.write({
                'state': 'cancelled',
                'current_handler_id': False
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
                'rejection_reason': False,
                'current_handler_id': False,
                'product_manager_id': False,
                'designer_id': False,
                'pattern_maker_id': False,
                'sample_worker_id': False
            })
            record.message_post(body=_('申请已重置为草稿状态。'))
    
    def _get_default_product_manager(self):
        """获取默认产品经理"""
        product_manager = self.env['res.users'].search([
            ('groups_id', 'in', self.env.ref('clothing_development_approval.group_product_manager').id)
        ], limit=1)
        return product_manager
    
    def _get_default_designer(self):
        """获取默认设计师"""
        designer = self.env['res.users'].search([
            ('groups_id', 'in', self.env.ref('clothing_development_approval.group_designer').id)
        ], limit=1)
        return designer
    
    def _get_default_pattern_maker(self):
        """获取默认版师"""
        pattern_maker = self.env['res.users'].search([
            ('groups_id', 'in', self.env.ref('clothing_development_approval.group_pattern_maker').id)
        ], limit=1)
        return pattern_maker
    
    def _get_default_sample_worker(self):
        """获取默认样衣工"""
        sample_worker = self.env['res.users'].search([
            ('groups_id', 'in', self.env.ref('clothing_development_approval.group_sample_worker').id)
        ], limit=1)
        return sample_worker