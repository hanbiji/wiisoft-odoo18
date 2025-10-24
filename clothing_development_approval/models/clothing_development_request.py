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
        ('25', '2025'),
        ('26', '2026'),
        ('27', '2027'),
        ('28', '2028'),
        ('29', '2029'),
        ('30', '2030')
    ], string='年份', help='服装开发的年份', required=True)

    target_gender = fields.Selection([
        ('M', 'Men - 男'),
        ('W', 'Women - 女'),
        ('U', 'Unisex - 中性'),
        ('K', 'Kids - 小孩')
    ], string='目标性别', required=True)
    
    batch = fields.Char(
        string='批次',
        help='服装开发的批次编号'
    )
    
    style_number = fields.Char(
        string='款号',
        help='服装的款式编号'
    )
    
    description = fields.Text(
        string='设计参考',
        required=True,
        help='详细描述服装开发需求、设计理念、功能要求等'
    )
    design_requirements = fields.Text(
        string='设计要求',
        help='详细的设计要求和规格说明'
    )
    # 打板图
    board_drawing_html = fields.Html(
        string='打板图',
        help='上传多张打板图'
    )
    board_drawing_ids = fields.One2many(
        'ir.attachment', 'res_id',
        domain=[('res_model', '=', 'clothing.development.request')],
        string='打板图',
        help='上传多张打板图'
    )
    # 样衣图
    sample_clothing = fields.Text(
        string='样衣内容',
        help='上传样衣图片或视频'
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
        ('AD', 'ApoDrome'),
        ('OT', '其他')
    ], string='服装品牌', required=True)

    clothing_type = fields.Selection([
        ('SU', 'One-piece suit - 连体'),
        ('JK', 'Jacket - 夹克'),
        ('PT', 'Pants - 裤子'),
        ('BB', 'Bibs - 背带裤'),
        ('GG', 'Goggles - 雪镜'),
        ('HM', 'Helmet - 头盔'),
        ('GL', 'Gloves - 手套'),
        ('SK', 'Socks - 袜子')
    ], string='服装分类', required=True)

    # 服装风格: 工装,时装,潮酷,复古,常规,其他
    style = fields.Selection([
        ('formal', '工装'),
        ('fashion', '时装'),
        ('trendy', '潮酷'),
        ('retro', '复古'),
        ('regular', '常规'),
        ('other', '其他'),
    ], string='服装风格', required=True)
    
    target_season = fields.Selection([
        ('spring', '春季'),
        ('summer', '夏季'),
        ('autumn', '秋季'),
        ('winter', '冬季'),
        ('all_season', '四季通用')
    ], string='目标季节', required=True, help='该服装适用的季节')
    
    color_ids = fields.Many2many(
        'clothing.color',
        'clothing_development_request_color_rel',
        'request_id',
        'color_id',
        string='主要颜色',
        help='服装的主要颜色'
    )
    
    secondary_color_ids = fields.Many2many(
        'clothing.color',
        'clothing_development_request_secondary_color_rel',
        'request_id',
        'color_id',
        string='次要颜色',
        help='服装的次要颜色或配色方案'
    )
    
    clothing_size_ids = fields.Many2many(
        'clothing.size',
        string='关联尺寸',
        help='与此开发申请关联的具体尺寸规格',
        domain="[('clothing_type', '=', clothing_type), ('target_gender', '=', target_gender)]"
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
        default=lambda self: self._get_default_product_manager(),
        help='负责产品规划和最终审批的产品经理'
    )
    
    designer_id = fields.Many2one(
        'res.users',
        string='设计师',
        tracking=True,
        default=lambda self: self._get_default_designer(),
        help='负责设计方案制定的设计师'
    )
    
    pattern_maker_id = fields.Many2one(
        'res.users',
        string='版师',
        tracking=True,
        default=lambda self: self._get_default_pattern_maker(),
        help='负责版型制作的版师'
    )
    
    sample_worker_id = fields.Many2one(
        'res.users',
        string='样衣工',
        tracking=True,
        default=lambda self: self._get_default_sample_worker(),
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
        help='上传相关的设计图、参考图等附件'
    )
    
    # 设计参考图片关联
    design_reference_ids = fields.One2many(
        'clothing.design.reference',
        'request_id',
        string='设计参考图片',
        help='该申请关联的设计参考图片'
    )
    # 服装设计草稿关联
    design_draft_ids = fields.One2many(
        'clothing.design.draft',
        'request_id',
        string='设计草稿',
        help='该申请关联的设计草稿'
    )
    # 服装设计打板图关联
    design_board_ids = fields.One2many(
        'clothing.design.board',
        'request_id',
        string='设计打板图',
        help='该申请关联的设计打板图'
    )
    # 服装设计样衣挂板图关联
    design_sample_ids = fields.One2many(
        'clothing.design.sample',
        'request_id',
        string='设计样衣挂板图',
        help='该申请关联的设计样衣挂板图'
    )
    
    # SKU变体关联字段
    sku_variant_ids = fields.One2many(
        'clothing.sku',
        'request_id',
        string='SKU变体',
        help='该申请生成的所有SKU变体'
    )
    
    notes = fields.Text(
        string='备注',
        help='其他备注信息'
    )

    # 面料成分
    fabric_composition = fields.Char(
        string='面料成分',
        help='描述服装面料的成分，例如：100% Cotton'
    )
    # 里衬成分
    lining_composition = fields.Char(
        string='里衬成分',
        help='描述服装里衬的成分，例如：100% Polyester'
    )
    # 填充物材料
    filler_material = fields.Char(
        string='填充物材料',
        help='描述服装填充物的材料，例如：100% Polyester'
    )
    # 填充物密度(gsm)
    filler_density = fields.Char(
        string='填充物密度(gsm)',
        help='描述服装填充物的密度，例如：100gsm'
    )
    # 填充物总克重
    filler_total_weight = fields.Char(
        string='填充物总克重',
        help='描述服装填充物的总克重，例如：100g'
    )
    # 其他材料成分
    other_material_composition = fields.Char(
        string='其他材料成分',
        help='描述服装其他材料的成分，例如：100% Polyester'
    )
    # 面料涂层(抗污)
    fabric_coating = fields.Char(
        string='面料涂层(抗污)',
        help='描述服装面料的涂层，例如：100% Polyester'
    )
    # 防水透气膜
    waterproofing_permeability = fields.Char(
        string='防水透气膜',
        help='描述服装面料的防水透气膜，例如：100% Polyester'
    )
    # 布料压合工艺
    fabric_press_technique = fields.Char(
        string='布料压合工艺',
    )
    # 防水指数(mm)
    waterproofing_index = fields.Float(
        string='防水指数(mm)',
        help='描述服装面料的防水指数，例如：10mm'
    )
    # 透湿指数(g/㎡/24h)
    transpiration_index = fields.Float(
        string='透湿指数(g/㎡/24h)',
        help='描述服装面料的透湿指数，例如：10g/㎡/24h'
    )
    # 耐磨指数(次)
    wear_resistance = fields.Char(
        string='耐磨指数(次)',
        help='描述服装面料的耐磨指数，例如：10次'
    )
    # 弹性
    elasticity = fields.Char(
        string='弹性',
    )
    # 接缝压胶工艺
    seam_press_technique = fields.Char(
        string='接缝压胶工艺',
        help='描述服装面料的接缝压胶工艺，例如：100% Polyester'
    )
    # 手感
    feel = fields.Char(
        string='手感',
    )
    # 厚度
    thickness = fields.Char(
        string='厚度',
    )
    # 版型(总体)
    overall_fit = fields.Char(
        string='版型(总体)',
    )
    # 版型细节
    fit_details = fields.Text(
        string='版型细节',
        help='描述服装面料的版型细节，例如：100% Polyester'
    )
    # 口袋
    pocket = fields.Text(
        string='口袋',
    )
    # 拉链
    zip = fields.Char(
        string='拉链',
    )
    # 通风
    ventilation = fields.Char(
        string='通风',
    )
    # 帽子设计
    hat_design = fields.Text(
        string='帽子设计',
    )
    # 袖口设计
    cuff_design = fields.Text(
        string='袖口设计',
    )
    # 脚口设计
    foot_design = fields.Text(
        string='脚口设计',
    )
    # 衣领设计
    collar_design = fields.Char(
        string='衣领设计',
    )
    # 防风雪倒灌设计
    wind_snow_design = fields.Text(
        string='防风雪倒灌设计',
    )
    # 抽绳/扣
    drawstring = fields.Char(
        string='抽绳/扣',
    )
    # 其他设计细节
    other_design_details = fields.Text(
        string='其他设计细节'
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
            # generate_sku_variants
            record.generate_sku_variants()
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
    
    def generate_sku_variants(self):
        """生成所有SKU变体
        
        根据SKU规则生成所有可能的变体组合：
        'brand'-'year''batch''style_number'-'clothing_type'-'target_gender'-'color_ids.color_code'-'clothing_size_ids.size'
        
        Returns:
            list: 生成的SKU变体列表
        """
        self.ensure_one()
        
        # 验证必要字段
        if not all([self.brand, self.year, self.batch, self.style_number, 
                   self.clothing_type, self.target_gender, self.color_ids, self.clothing_size_ids]):
            raise UserError(_("请确保所有必要字段都已填写：品牌、年份、批次、款号、服装类型、目标性别、主要颜色、关联尺寸"))
        
        # 清除现有的SKU变体
        existing_skus = self.env['clothing.sku'].search([('request_id', '=', self.id)])
        existing_skus.unlink()
        
        sku_variants = []
        
        # 为每个颜色和尺寸的组合生成SKU
        for color in self.color_ids:
            for size in self.clothing_size_ids:
                # 构建SKU代码：GS-性别分类年份序号-颜色-尺寸
                sku_code = f"{self.brand}-{self.target_gender}{self.clothing_type}{self.year}{self.batch}{self.style_number}-{color.color_code}-{size.size}"
                # 把sku_code转换为大写
                sku_code = sku_code.upper()
                # 构建SKU名称
                sku_name = f"{dict(self._fields['brand'].selection)[self.brand]} {self.year}年{self.batch}批次 {self.style_number}款 {dict(self._fields['clothing_type'].selection)[self.clothing_type]} {dict(self._fields['target_gender'].selection)[self.target_gender]} {color.name} {size.size.upper()}码"
                gtin = self._generate_gtin14()
                # 创建SKU记录
                sku_variant = self.env['clothing.sku'].create({
                    'name': sku_name,
                    'sku': sku_code,
                    'gtin': gtin,
                    'size_id': size.id,
                    'color_id': color.id,
                    'request_id': self.id,
                })
                
                sku_variants.append(sku_variant)
        
        return sku_variants
    
    def action_generate_sku_variants(self):
        """按钮动作：生成SKU变体
        
        用于在界面上提供生成SKU变体的按钮功能
        """
        try:
            sku_variants = self.generate_sku_variants()
            
            # 显示成功消息
            message = _("成功生成 %d 个SKU变体") % len(sku_variants)
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _("SKU生成成功"),
                    'message': message,
                    'type': 'success',
                    'sticky': False,
                }
            }
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _("SKU生成失败"),
                    'message': str(e),
                    'type': 'danger',
                    'sticky': True,
                }
            }
            
    def _generate_gtin14(self):
        """
        生成GTIN-14条码（13位全球贸易项目代码）
        结构：厂商代码(8位) + 商品代码(4位) + 校验位(1位)
        厂商代码从系统参数读取，商品代码由系统内部逻辑生成，最后计算校验位
        """
        # 从系统参数读取厂商代码（8位数字，不足左补0）
        company_prefix = self.env['ir.config_parameter'].sudo().get_param(
            'clothing_dev.gs1_company_prefix', '69426101'
        ).zfill(8)[:8]
        
        # 用记录ID+年份后两位生成4位商品代码
        # 取记录ID的后2位和年份后2位组成4位商品代码
        gs1_last_id = self.env['ir.config_parameter'].sudo().get_param(
            'clothing_dev.gs1_last_id', '0001'
        ).zfill(4)[:4]
        
        # 增加商品代码的序号
        product_code = str(int(gs1_last_id) + 1).zfill(4)
        # 更新系统参数中的GS1最后一个ID
        self.env['ir.config_parameter'].sudo().set_param(
            'clothing_dev.gs1_last_id', product_code
        )
        
        # 拼接前12位
        gtin12 = company_prefix + product_code
        
        # 计算第13位校验码（EAN-13 Mod10算法）
        odd_sum = sum(int(ch) for ch in gtin12[::2])   # 奇数位和
        even_sum = sum(int(ch) for ch in gtin12[1::2]) # 偶数位和
        check_digit = (10 - (odd_sum + even_sum * 3) % 10) % 10
        
        return gtin12 + str(check_digit)
    
    
class ClothingSku(models.Model):
    _name = 'clothing.sku'
    _description = '服装SKU'

    name = fields.Char(string='SKU名称', required=True)
    sku = fields.Char(string='SKU', required=True)
    size_id = fields.Many2one('clothing.size', string='尺寸')
    color_id = fields.Many2one('clothing.color', string='颜色')
    gtin = fields.Char(string='GTIN')
    # clothing.development.request id
    request_id = fields.Many2one('clothing.development.request', string='申请')

