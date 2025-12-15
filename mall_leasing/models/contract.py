# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
import logging

_logger = logging.getLogger(__name__)

class MallLeasingContract(models.Model):
    _name = 'mall.leasing.contract'
    _description = '租赁合同（房东/租户）'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char('合同编号', required=True, tracking=True, copy=False, default=lambda self: _('New'))
    contract_type = fields.Selection([
        ('tenant', '租赁合同'),
        ('property', '物业合同'),
        ('landlord', '房东合同'),
    ], string='合同类型', default='tenant', required=True, tracking=True)

    # 商场项目
    mall_id = fields.Many2one('mall.mall', string='商场', required=True, tracking=True)
    # 房产（支持多选）
    facade_ids = fields.Many2many(
        'mall.facade', 'mall_contract_facade_rel', 'contract_id', 'facade_id', 
        string='房号', required=True
    )
    # 运营单位
    operator_id = fields.Many2one('res.company', 
        string='运营公司', 
        required=True, 
        default=lambda self: self.env.company)
    # 物业单位
    property_company_id = fields.Many2one('res.company', 
        string='物业公司', 
        required=True, 
        default=lambda self: self.env.company)
    # 租赁单位（人）
    partner_id = fields.Many2one('res.partner', 
        string='租赁单位（人）', 
        required=True, 
        domain=[('mall_contact_type', '=', 'tenant')])
    # 房东
    landlord_id = fields.Many2one('res.partner', 
        string='房东', 
        domain=[('mall_contact_type', '=', 'landlord')])
    
    # 店铺名称
    shop_name = fields.Char('店铺名称', required=True)

    state = fields.Selection([
        ('draft', '草稿'),
        ('approved', '审批通过'),
        ('signed', '已签约'),
        ('active', '执行中'),
        ('renewed', '已续约'),
        ('terminated', '已终止'),
    ], string='状态', default='draft', tracking=True)

    currency_id = fields.Many2one('res.currency', string='币种', default=lambda self: self.env.company.currency_id.id)

    # 首期租金
    first_rent_amount = fields.Monetary('首期租金', currency_field='currency_id')
    # 首期租金已生成
    first_rent_generated = fields.Boolean('首期租金已生成', default=False, help='标记首期租金是否已经生成过账单')
    # 首期账单比例（用于按自然月调整首期费用）
    first_period_ratio = fields.Float(
        '首期账单比例', 
        compute='_compute_first_period_ratio', 
        store=True, 
        digits=(5, 4),
        help='首期账单按实际天数占周期总天数的比例计算'
    )
    # 每期租金
    rent_amount = fields.Monetary('每期租金', currency_field='currency_id')
    # 押金
    deposit = fields.Monetary('押金', currency_field='currency_id')
    # 押金已生成
    deposit_generated = fields.Boolean('押金已生成', default=False, help='标记押金是否已经生成过账单')
    # 合同押金支付与退款
    deposit_payment_status = fields.Selection([
        ('unpaid', '未支付'),
        ('paid', '已支付'),
        ('refunded', '已退款'),
    ], string='押金支付与退款状态', default='unpaid')

    # 租赁面积
    lease_area = fields.Float('租赁面积(㎡)', digits=(10, 2), help='合同约定的租赁面积')
    # 物业费单价
    property_fee_unit = fields.Monetary('物业费单价(元/㎡)', currency_field='currency_id', help='每平方米物业费单价')
    # 每期物业费
    property_fee = fields.Monetary('每期物业费', currency_field='currency_id', compute='_compute_property_fee', store=True, readonly=False)
    # 每期服务费
    service_fee = fields.Monetary('每期服务费', currency_field='currency_id')
    # 水费
    water_fee = fields.Monetary('水费', currency_field='currency_id')
    # 电费
    electric_fee = fields.Monetary('电费', currency_field='currency_id')
    # 装修垃圾清理费
    garbage_fee = fields.Monetary('装修垃圾清理费', currency_field='currency_id')
    # 装修保证金
    decoration_deposit = fields.Monetary('装修保证金', currency_field='currency_id')
    # 装修保证金已生成
    decoration_deposit_generated = fields.Boolean('装修保证金已生成', default=False, help='标记装修保证金是否已经生成过账单')
    # 装修保证金支付与退款
    decoration_deposit_payment_status = fields.Selection([
        ('unpaid', '未支付'),
        ('paid', '已支付'),
        ('refunded', '已退款'),
        ('refunded_partially', '部分退款'),
    ], string='装修保证金支付与退款状态', default='unpaid')
    # 装修保证金扣款金额
    decoration_deposit_deduction_amount = fields.Monetary('装修保证金扣款金额', currency_field='currency_id')
    # 装修保证金扣款原因
    decoration_deposit_deduction_reason = fields.Char('装修保证金扣款原因')


    payment_frequency = fields.Selection([
        ('monthly', '月付'),
        ('quarterly', '季付'),
        ('half_yearly', '半年付'),
        ('yearly', '年付'),
    ], string='支付方式')
    payment_day = fields.Integer('支付日(1-31)', default=1)

    bank_account = fields.Char('收款账户')
    # 银行账户详细信息（用于付款通知单）
    bank_account_name = fields.Char('户名', help='收款账户户名')
    bank_name = fields.Char('开户行', help='开户银行名称')
    bank_account_number = fields.Char('账号', help='银行账号')
    
    # 租赁期限（年）
    lease_term = fields.Integer('租赁期限（年）', default=1)
    lease_start_date = fields.Date('租赁开始日')
    lease_end_date = fields.Date('租赁结束日', compute='_compute_lease_end_date', store=True, readonly=False)

    free_rent_from = fields.Date('免租开始')
    free_rent_to = fields.Date('免租结束')

    escalation_rate = fields.Float('递增率(%)', help='例如每年递增5%，填写5')
    # 递增起始年（从第几年开始递增）
    escalation_start_year = fields.Integer(
        '递增起始年', 
        default=1, 
        help='从第几年开始执行递增，例如：1表示第1年就开始递增，3表示前2年不变、从第3年开始递增'
    )
    # 递增周期（每隔几年递增一次）
    escalation_term = fields.Integer('递增周期（年）', default=1, help='每隔几年执行一次递增')
    # 递增周期已递增
    escalation_term_generated = fields.Boolean('本周期已递增', default=False, help='标记当前递增周期是否已经执行过递增')
    # 下次递增日期
    escalation_term_end_date = fields.Date('下次递增日期', compute='_compute_escalation_term_end_date', store=True)

    @api.depends('escalation_term', 'escalation_start_year', 'lease_start_date')
    def _compute_escalation_term_end_date(self):
        """
        计算下次递增日期
        逻辑：
        - 如果递增起始年=1，则第一次递增日期 = 租赁开始日 + 递增周期
        - 如果递增起始年>1，则第一次递增日期 = 租赁开始日 + (递增起始年-1) + 递增周期
        - 例如：起始年=3，周期=1年，则从第3年开始，每年递增一次
        """
        for rec in self:
            if rec.lease_start_date and rec.escalation_term:
                start_year = rec.escalation_start_year or 1
                # 首次递增日期 = 开始日期 + (起始年-1)年 + 递增周期
                # 即：如果起始年=1，周期=1，则1年后递增；如果起始年=3，周期=1，则3年后递增
                years_until_escalation = (start_year - 1) + rec.escalation_term
                rec.escalation_term_end_date = rec.lease_start_date + relativedelta(years=years_until_escalation)
            else:
                rec.escalation_term_end_date = False

    introducer_id = fields.Many2one('res.partner', string='介绍人/中介')
    commission_type = fields.Selection([
        ('fixed', '固定金额'),
        ('percent', '租金比例'),
    ], string='中介费类型')
    commission_amount = fields.Float('中介费金额/比例')
    commission_paid = fields.Boolean('中介费已支付')

    # 账单提前生成天数
    bill_advance_days = fields.Integer(
        '账单提前天数', 
        default=0, 
        help='账单在到期日前提前多少天生成，0表示到期当天生成'
    )

    next_bill_date = fields.Date('下次出账日', compute='_compute_next_bill_date', store=True)

    version_ids = fields.One2many('mall.leasing.contract.version', 'contract_id', string='历史版本')

    contract_payment_ids = fields.One2many('mall.leasing.contract.payment', 'contract_id', string='付款记录')
    
    # 发票关联
    invoice_ids = fields.One2many(
        'account.move', 
        'mall_contract_id', string='相关发票', 
        domain=[('move_type', 'in', ['out_invoice', 'in_invoice'])]
    )
    invoice_count = fields.Integer('发票数量', compute='_compute_invoice_count')
    pending_amount = fields.Monetary(
        '待付款金额', 
        currency_field='currency_id', 
        compute='_compute_pending_amount', 
        store=True, 
        readonly=True
    )

    _sql_constraints = [
        ('name_unique', 'unique(name)', '合同编号必须唯一。')
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) in [False, _('New')]:
                vals['name'] = self.env['ir.sequence'].next_by_code('mall.leasing.contract') or _('New')
        return super().create(vals_list)

    @api.depends('lease_area', 'property_fee_unit')
    def _compute_property_fee(self):
        """
        根据租赁面积和物业费单价自动计算每期物业费
        物业费 = 租赁面积 × 物业费单价
        """
        for rec in self:
            if rec.lease_area and rec.property_fee_unit:
                rec.property_fee = rec.lease_area * rec.property_fee_unit
            # 如果没有设置单价或面积，保持原有值不变（允许手动输入）

    @api.depends('lease_start_date', 'payment_frequency', 'free_rent_from', 'free_rent_to')
    def _compute_first_period_ratio(self):
        """
        计算首期账单比例
        按正常周期生成账单，如果有免租期则计算扣除免租天数后的比例
        """
        for rec in self:
            if not rec.lease_start_date or not rec.payment_frequency:
                rec.first_period_ratio = 1.0
                rec.first_rent_amount = rec.rent_amount
                continue
            
            # 计算一个完整周期的天数
            period_months = {'monthly': 1, 'quarterly': 3, 'half_yearly': 6, 'yearly': 12}.get(rec.payment_frequency, 1)
            period_end = rec.lease_start_date + relativedelta(months=period_months)
            full_period_days = (period_end - rec.lease_start_date).days
            
            # 检查首期内是否有免租期
            free_days = rec._calculate_free_rent_days_in_period(rec.lease_start_date, period_end)
            
            if free_days > 0:
                # 有免租期，计算比例
                billable_days = full_period_days - free_days
                if billable_days < 0:
                    billable_days = 0
                rec.first_period_ratio = round(billable_days / full_period_days, 2) if full_period_days > 0 else 1.0
                _logger.info(f"合同 {rec.name}: 首期有免租期 - 总天数: {full_period_days}, 免租天数: {free_days}, 应收天数: {billable_days}, 比例: {rec.first_period_ratio}")
            else:
                # 无免租期，完整周期
                rec.first_period_ratio = 1.0
                _logger.info(f"合同 {rec.name}: 首期无免租期，完整周期，比例: 1.0")
            
            rec.first_rent_amount = rec.rent_amount * rec.first_period_ratio
    
    def _calculate_free_rent_days_in_period(self, period_start, period_end):
        """
        计算指定期间内的免租天数
        :param period_start: 期间开始日期
        :param period_end: 期间结束日期（不包含）
        :return: 免租天数
        """
        self.ensure_one()
        
        if not self.free_rent_from or not self.free_rent_to:
            return 0
        
        # 计算免租期与账单期间的重叠部分
        # 重叠开始日 = max(免租开始日, 期间开始日)
        overlap_start = max(self.free_rent_from, period_start)
        # 重叠结束日 = min(免租结束日, 期间结束日-1天)
        overlap_end = min(self.free_rent_to, period_end - relativedelta(days=1))
        
        # 如果有重叠
        if overlap_start <= overlap_end:
            free_days = (overlap_end - overlap_start).days + 1
            _logger.info(f"合同 {self.name}: 免租期 ({self.free_rent_from} ~ {self.free_rent_to}) 与期间 ({period_start} ~ {period_end}) 重叠 {free_days} 天")
            return free_days
        
        return 0

    @api.depends('lease_term', 'lease_start_date')
    def _compute_lease_end_date(self):
        """
        根据租赁期限和开始日期自动计算租赁结束日期
        :return: None
        """
        for rec in self:
            if rec.lease_start_date and rec.lease_term:
                # 租赁结束日期 = 开始日期 + 租赁年限 - 1天
                rec.lease_end_date = rec.lease_start_date + relativedelta(years=rec.lease_term, days=-1)
            else:
                rec.lease_end_date = False

    @api.depends('lease_start_date', 'payment_frequency')
    def _compute_next_bill_date(self):
        """
        计算合同的下次出账日（按正常周期）
        从租赁开始日开始，按照支付周期生成账单
        """
        for rec in self:
            if not rec.lease_start_date or not rec.payment_frequency:
                rec.next_bill_date = False
                continue
            rec.next_bill_date = rec.lease_start_date

    @api.depends('invoice_ids')
    def _compute_invoice_count(self):
        """计算关联发票数量"""
        for record in self:
            record.invoice_count = len(record.invoice_ids)

    @api.depends('invoice_ids.amount_residual', 'invoice_ids.payment_state', 'invoice_ids.state')
    def _compute_pending_amount(self):
        for record in self:
            moves = record.invoice_ids.filtered(lambda m: m.state == 'posted' and m.payment_state in ('not_paid', 'partial'))
            record.pending_amount = sum(m.amount_residual for m in moves)

    def _get_journal_and_account(self):
        """
        获取合同对应的会计凭证和资产账户
        :return: 包含journal、account和company的元组
        """
        # 根据合同类型确定使用哪个公司
        if self.contract_type == 'tenant':
            # 租赁合同：运营公司向租户收款
            company = self.operator_id
            # 获取销售账簿，如果是分公司，则获取分公司的销售账簿
            if company.parent_id:
                journal = self.env['account.journal'].sudo().search([
                    ('type', '=', 'sale'), 
                    ('company_id', '=', company.parent_id.id)
                ], limit=1)
            else:
                journal = self.env['account.journal'].sudo().search([
                    ('type', '=', 'sale'), 
                    ('company_id', '=', company.id)
                ], limit=1)
            # 获取收入科目，如果是分公司，则获取分公司的收入科目
            if company.parent_id:
                account = self.env['account.account'].sudo().search([
                    ('account_type', '=', 'income'),
                    ('company_ids', 'in', [company.parent_id.id])
                ], limit=1)
            else:
                account = self.env['account.account'].sudo().search([
                    ('account_type', '=', 'income'),
                    ('company_ids', 'in', [company.id])
                ], limit=1)

        elif self.contract_type == 'property':
            # 物业合同：物业公司向租户收取物业费
            company = self.property_company_id
            # 获取销售账簿，如果是分公司，则获取分公司的销售账簿
            if company.parent_id:
                journal = self.env['account.journal'].sudo().search([
                    ('type', '=', 'sale'), 
                    ('company_id', '=', company.parent_id.id)
                ], limit=1)
            else:
                journal = self.env['account.journal'].sudo().search([
                    ('type', '=', 'sale'), 
                    ('company_id', '=', company.id)
                ], limit=1)
            # 获取收入科目，如果是分公司，则获取分公司的收入科目
            if company.parent_id:
                account = self.env['account.account'].sudo().search([
                    ('account_type', '=', 'income'),
                    ('company_ids', 'in', [company.parent_id.id])
                ], limit=1)
            else:
                account = self.env['account.account'].sudo().search([
                    ('account_type', '=', 'income'),
                    ('company_ids', 'in', [company.id])
                ], limit=1)
        else:  # landlord
            # 房东合同：公司向房东支付租金
            company = self.operator_id
            # 获取采购账簿，如果是分公司，则获取分公司的采购账簿
            if company.parent_id:
                journal = self.env['account.journal'].sudo().search([
                    ('type', '=', 'purchase'), 
                    ('company_id', '=', company.parent_id.id)
                ], limit=1)
            else:
                journal = self.env['account.journal'].sudo().search([
                    ('type', '=', 'purchase'), 
                    ('company_id', '=', company.id)
                ], limit=1)
            # 获取费用科目，如果是分公司，则获取分公司的费用科目
            if company.parent_id:
                account = self.env['account.account'].sudo().search([
                    ('account_type', '=', 'expense'),
                    ('company_ids', 'in', [company.parent_id.id])
                ], limit=1)
            else:
                account = self.env['account.account'].sudo().search([
                    ('account_type', '=', 'expense'),
                    ('company_ids', 'in', [company.id])
                ], limit=1)

        _logger.info(f"Contract: {self.name}, Journal: {journal.name if journal else 'None'}, Account: {account.display_name if account else 'None'}, Company: {company.name}")
        
        # 检查是否找到了必需的 Journal 和 Account
        if not journal:
            raise UserError(_(
                '未找到公司 "%s" 的会计账簿。\n'
                '请在"会计 → 配置 → 账簿"中为该公司创建%s账簿。'
            ) % (company.name, _('销售') if self.contract_type in ['tenant', 'property'] else _('采购')))
        
        if not account:
            raise UserError(_(
                '未找到公司 "%s" 的会计科目。\n'
                '请在"会计 → 配置 → 会计科目表"中为该公司配置%s科目。'
            ) % (company.name, _('收入') if self.contract_type in ['tenant', 'property'] else _('费用')))
        
        return journal, account, company

    def _charge_lines(self, account):
        """
        生成合同的费用行项目
        :param account: 费用对应的资产账户
        :return: 费用行项目列表
        """
        def line(name, amount):
            return (0, 0, {
                'name': name,
                'quantity': 1.0,
                'price_unit': amount or 0.0,
                'account_id': account.id,
            })
        lines = []
        if self.rent_amount:
            lines.append(line(_('租金'), self.rent_amount))
        # if self.water_fee:
        #     lines.append(line(_('水费'), self.water_fee))
        # if self.electric_fee:
        #     lines.append(line(_('电费'), self.electric_fee))
        if self.property_fee:
            lines.append(line(_('物业费'), self.property_fee))
        if self.service_fee:
            lines.append(line(_('服务费'), self.service_fee))
        if self.garbage_fee:
            lines.append(line(_('装修垃圾清理费'), self.garbage_fee))
        return lines or [line(_('租赁费用'), 0.0)]

    def _create_single_move(self, fee_name, fee_amount, journal, account, company):
        """
        为单个费用类型创建会计凭证
        :param fee_name: 费用名称
        :param fee_amount: 费用金额
        :param journal: 会计账簿
        :param account: 费用对应的资产账户
        :param company: 公司对象
        :return: 创建的会计凭证
        """
        if not fee_amount or fee_amount <= 0:
            return None
        # 账单周期起始日期为next_bill_date
        bill_period_start_date = self.next_bill_date
        # 账单周期结束日期为next_bill_date+付款周期-1天（因为下一期从结束日当天开始）
        period_months = {'monthly': 1, 'quarterly': 3, 'half_yearly': 6, 'yearly': 12}.get(self.payment_frequency, 1)
        bill_period_end_date = self.next_bill_date + relativedelta(months=period_months, days=-1)
        
        move_vals = {
            'move_type': 'out_invoice' if self.contract_type in ['tenant', 'property'] else 'in_invoice',
            'partner_id': self.partner_id.id,  # 租户或房东
            'ref': f'合同# {self.name} - {fee_name}',
            'invoice_date': self.next_bill_date,
            'invoice_date_due': self.next_bill_date + relativedelta(days=30),
            'journal_id': journal.id,
            'company_id': company.id,
            'invoice_line_ids': [(0, 0, {
                'name': fee_name,
                'quantity': 1.0,
                'price_unit': fee_amount,
                'account_id': account.id,
            })],
            'mall_contract_id': self.id,  # 建立与合同的关联
            'bill_period_start_date': bill_period_start_date,
            'bill_period_end_date': bill_period_end_date,
        }
        # _logger.info(f"move_vals: {move_vals}")
        
        account_move = self.env['account.move'].sudo().create(move_vals)
        # _logger.info(f"account_move: {account_move}")
        # 自动确认凭证
        account_move.action_post()
        return account_move

    def action_approve(self):
        """审核通过"""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('只有草稿状态的合同才能审核'))
        
        self.state = 'approved'
        self.message_post(body=_('合同已审核通过'))
        
        # 创建活动提醒
        self.activity_schedule(
            'mail.mail_activity_data_todo',
            summary=_('合同审核通过'),
            note=_('合同 %s 已审核通过，可以进行签约') % self.name,
            user_id=self.env.user.id
        )
        
        return True
    
    def action_reject(self):
        """审核拒绝"""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('只有草稿状态的合同才能拒绝'))
        
        # 保持草稿状态，但添加拒绝记录
        self.message_post(body=_('合同审核被拒绝，请修改后重新提交'))
        
        # 创建活动提醒
        self.activity_schedule(
            'mail.mail_activity_data_todo',
            summary=_('合同审核被拒绝'),
            note=_('合同 %s 审核被拒绝，请修改后重新提交审核') % self.name,
            user_id=self.env.user.id
        )
        
        return True

    def action_sign(self):
        """签约"""
        self.ensure_one()
        if self.state != 'approved':
            raise UserError(_('只有已审核通过的合同才能签约'))
        
        self.state = 'signed'
        self.message_post(body=_('合同已签约'))
        
        # 创建活动提醒
        self.activity_schedule(
            'mail.mail_activity_data_todo',
            summary=_('合同已签约'),
            note=_('合同 %s 已签约，可以开始执行') % self.name,
            user_id=self.env.user.id
        )
        
        return True
    
    def action_active(self):
        """
        激活合同 - 合同状态变更为活动
        """
        self.ensure_one()
        if self.state != 'signed':
            raise UserError(_('只有已签约的合同才能激活'))
        
        self.state = 'active'
        self.message_post(body=_('合同已激活'))
        
        # 创建活动提醒
        self.activity_schedule(
            'mail.mail_activity_data_todo',
            summary=_('合同已激活'),
            note=_('合同 %s 已激活，可以开始执行') % self.name,
            user_id=self.env.user.id
        )
        
        return True

    def action_create_property_contract(self):
        """创建物业合同"""
        self.ensure_one()
        vals = {
            'contract_type': 'property',
            'mall_id': self.mall_id.id,
            'facade_ids': [(6, 0, self.facade_ids.ids)],
            'operator_id': self.operator_id.id,
            'partner_id': self.partner_id.id,
            'property_company_id': self.property_company_id.id,
            'shop_name': self.shop_name,
            'currency_id': self.currency_id.id,
            'bank_account': self.bank_account,
            'lease_term': self.lease_term,
            'lease_start_date': self.lease_start_date,
            'lease_end_date': self.lease_end_date,
            'payment_frequency': self.payment_frequency,
            'payment_day': self.payment_day,
            'free_rent_from': self.free_rent_from,
            'free_rent_to': self.free_rent_to,
            'escalation_rate': self.escalation_rate,
        }
        new = self.env['mall.leasing.contract'].create(vals)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'mall.leasing.contract',
            'res_id': new.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_property_contracts(self):
        """查看相关的物业合同"""
        self.ensure_one()
        # 读取已有的动作定义（若存在）
        try:
            action = self.env.ref('mall_leasing.action_property_contracts').read()[0]
        except Exception:
            action = {
                'type': 'ir.actions.act_window',
                'name': _('物业合同'),
                'res_model': 'mall.leasing.contract',
                'view_mode': 'list,form',
            }
        # 基础筛选：物业合同
        domain = [('contract_type', '=', 'property')]
        # 同商场
        if self.mall_id:
            domain.append(('mall_id', '=', self.mall_id.id))
        # 关联相同房号（多选）
        if self.facade_ids:
            domain.append(('facade_ids', 'in', self.facade_ids.ids))
        if self.partner_id:
            domain.append(('partner_id', '=', self.partner_id.id))
        action['domain'] = domain

        # 传递默认上下文，便于快速创建物业合同
        ctx = dict(self.env.context or {})
        ctx.update({
            'default_contract_type': 'property',
            'default_mall_id': self.mall_id.id,
            'default_facade_ids': [(6, 0, self.facade_ids.ids)],
            'default_operator_id': self.operator_id.id,
            'default_partner_id': self.partner_id.id,
            'default_property_company_id': self.property_company_id.id,
        })
        action['context'] = ctx

        # 若仅有一个匹配，直接打开表单视图
        records = self.env['mall.leasing.contract'].search(domain, limit=2)
        if len(records) == 1:
            try:
                form_view = self.env.ref('mall_leasing.view_mall_contract_form').id
                action['views'] = [(form_view, 'form')]
            except Exception:
                # 无特定视图引用时，保持默认
                pass
            action['res_id'] = records.id
        return action

    def action_view_tenant_contracts(self):
        """查看相关的租户合同"""
        self.ensure_one()
        try:
            action = self.env.ref('mall_leasing.action_tenant_contracts').read()[0]
        except Exception:
            action = {
                'type': 'ir.actions.act_window',
                'name': _('租户合同'),
                'res_model': 'mall.leasing.contract',
                'view_mode': 'list,form',
            }
        domain = [('contract_type', '=', 'tenant')]
        if self.mall_id:
            domain.append(('mall_id', '=', self.mall_id.id))
        if self.facade_ids:
            domain.append(('facade_ids', 'in', self.facade_ids.ids))
        if self.partner_id:
            domain.append(('partner_id', '=', self.partner_id.id))
        action['domain'] = domain

        ctx = dict(self.env.context or {})
        ctx.update({
            'default_contract_type': 'tenant',
            'default_mall_id': self.mall_id.id,
            'default_facade_ids': [(6, 0, self.facade_ids.ids)],
            'default_operator_id': self.operator_id.id,
            'default_partner_id': self.partner_id.id,
            'default_property_company_id': self.property_company_id.id,
        })
        action['context'] = ctx

        records = self.env['mall.leasing.contract'].search(domain, limit=2)
        if len(records) == 1:
            try:
                form_view = self.env.ref('mall_leasing.view_mall_contract_form').id
                action['views'] = [(form_view, 'form')]
            except Exception:
                pass
            action['res_id'] = records.id
        return action

    def action_generate_move(self):
        """
        生成合同对应的会计凭证 - 为每种费用类型生成单独的凭证
        支持首期账单按比例计算（对齐自然月周期）
        :return: 包含所有凭证ID的字典
        """
        self.ensure_one()
        
        if not self.lease_start_date:
            raise UserError(_('请先设置租赁开始日期'))
        
        # 判断当前日期+bill_advance_days是否小于出账日
        if self.next_bill_date > date.today() + timedelta(days=self.bill_advance_days):
            raise UserError(_('未到出账日，不能生成账单！'))
        
        journal, account, company = self._get_journal_and_account()
        
        # 判断是否是首期账单（首期租金未生成）
        is_first_period = not self.first_rent_generated
        # 首期比例（只在有免租期时才会小于1.0）
        ratio = self.first_period_ratio if is_first_period and self.first_period_ratio else 1.0
        
        # 定义费用类型和对应的金额
        fee_types = []
        
        # 租金处理
        if is_first_period and self.first_rent_amount and ratio < 1.0:
            # 首期有免租期，使用按比例计算的租金
            fee_types.append((_('租金（扣除免租期）'), self.first_rent_amount))
        else:
            # 正常周期租金
            fee_types.append((_('租金'), self.rent_amount))
        
        # 押金只在第一次生成账单时包含
        if not self.deposit_generated and self.deposit:
            fee_types.append((_('押金'), self.deposit))
        # 装修保证金只在第一次生成账单时包含
        if not self.decoration_deposit_generated and self.decoration_deposit:
            fee_types.append((_('装修保证金'), self.decoration_deposit))
        
        # 其他费用（首期有免租期时按比例）
        if is_first_period and ratio < 1.0:
            if self.property_fee:
                fee_types.append((_('物业费（扣除免租期）'), round(self.property_fee * ratio, 2)))
            if self.service_fee:
                fee_types.append((_('服务费（扣除免租期）'), round(self.service_fee * ratio, 2)))
        else:
            if self.property_fee:
                fee_types.append((_('物业费'), self.property_fee))
            if self.service_fee:
                fee_types.append((_('服务费'), self.service_fee))
        
        # 装修垃圾清理费（一次性，不按比例）
        if self.garbage_fee:
            fee_types.append((_('装修垃圾清理费'), self.garbage_fee))
        
        _logger.info(f"fee_types: {fee_types}")
        
        # 为每种费用类型生成单独的会计凭证
        created_moves = []
        deposit_move_created = False
        first_rent_move_created = False
        for fee_name, fee_amount in fee_types:
            if not fee_amount:
                continue
            move = self._create_single_move(fee_name, fee_amount, journal, account, company)
            if move:
                created_moves.append(move)
                # 如果生成了押金账单，标记为已生成
                if fee_name == _('押金'):
                    deposit_move_created = True
                # 如果生成了租金账单（包含"租金"关键字），标记为已生成
                if '租金' in fee_name:
                    first_rent_move_created = True
                if '装修保证金' in fee_name:
                    self.decoration_deposit_generated = True

        
        # 更新押金生成状态
        if deposit_move_created:
            self.deposit_generated = True
        
        # 首期账单生成后，标记首期租金已生成
        if first_rent_move_created and is_first_period:
            self.first_rent_generated = True
        
        if not created_moves:
            raise UserError(_('没有需要生成凭证的费用项目'))

        self.next_bill_date = self._get_next_bill_date_after_current()
        
        
        # 如果只有一个凭证，直接返回该凭证的表单视图
        if len(created_moves) == 1:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'account.move',
                'res_id': created_moves[0].id,
                'view_mode': 'form',
                'target': 'current',
            }
        
        # 如果有多个凭证，返回列表视图显示所有生成的凭证
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'domain': [('id', 'in', [move.id for move in created_moves])],
            'view_mode': 'list,form',
            'target': 'current',
            'name': _('生成的会计凭证'),
        }

    def action_view_invoices(self):
        """查看关联的发票"""
        self.ensure_one()
        
        if not self.invoice_ids:
            return {'type': 'ir.actions.act_window_close'}
        
        # 获取自定义视图ID
        tree_view_id = self.env.ref('mall_leasing.view_lease_invoice_tree').id
        form_view_id = self.env.ref('mall_leasing.view_move_form_inherit_mall_leasing').id
        
        action = {
            'type': 'ir.actions.act_window',
            'name': '租赁合同发票',
            'res_model': 'account.move',
            'domain': [('id', 'in', self.invoice_ids.ids)],
            'context': {
                'default_move_type': 'out_invoice',
                'create': False,  # 禁止从此视图创建发票
            },
            'target': 'current',
        }
        
        if len(self.invoice_ids) == 1:
            # 单条记录：直接打开表单视图
            action['view_mode'] = 'form'
            action['res_id'] = self.invoice_ids.id
            action['views'] = [(form_view_id, 'form')]
        else:
            # 多条记录：显示列表视图
            action['view_mode'] = 'list,form'
            action['views'] = [
                (tree_view_id, 'list'),
                (form_view_id, 'form'),
            ]
        
        return action

    def get_invoice_summary(self):
        """获取发票汇总信息"""
        self.ensure_one()
        invoices = self.invoice_ids
        total_amount = sum(invoices.mapped('amount_total'))
        paid_amount = sum(invoices.filtered(lambda x: x.payment_state == 'paid').mapped('amount_total'))
        unpaid_amount = total_amount - paid_amount
        overdue_invoices = invoices.filtered(lambda x: x.invoice_date_due and x.invoice_date_due < fields.Date.today() and x.payment_state != 'paid')
        
        return {
            'total_invoices': len(invoices),
            'total_amount': total_amount,
            'paid_amount': paid_amount,
            'unpaid_amount': unpaid_amount,
            'overdue_count': len(overdue_invoices),
            'overdue_amount': sum(overdue_invoices.mapped('amount_total')),
        }

    def get_payment_notice_data(self):
        """
        获取付款通知单所需的数据
        用于报表模板中显示费用产生时间和合计金额
        """
        self.ensure_one()
        
        # 获取周期月数
        period_months = {'monthly': 1, 'quarterly': 3, 'half_yearly': 6, 'yearly': 12}.get(self.payment_frequency, 1)
        
        # 计算费用产生时间段
        start_date = self.next_bill_date or self.lease_start_date or date.today()
        end_date = start_date + relativedelta(months=period_months, days=-1)
        
        # 格式化日期
        period_start_str = start_date.strftime('%Y年%m月%d日') if start_date else ''
        period_end_str = end_date.strftime('%Y年%m月%d日') if end_date else ''
        period_str = f"{period_start_str} 至 {period_end_str}" if period_start_str else ''
        
        # 构建费用项目列表
        fee_items = []
        total_amount = 0.0
        
        # 商铺租金
        if self.rent_amount and self.contract_type != 'property':
            fee_items.append({
                'name': '商铺租金',
                'period': period_str,
                'months': period_months,
                'amount': self.rent_amount,
                'remark': '',
            })
            total_amount += self.rent_amount
        
        # 物业费
        if self.property_fee:
            fee_items.append({
                'name': '物业费',
                'period': period_str,
                'months': period_months,
                'amount': self.property_fee,
                'remark': '',
            })
            total_amount += self.property_fee
        
        # 服务费
        if self.service_fee:
            fee_items.append({
                'name': '服务费',
                'period': period_str,
                'months': period_months,
                'amount': self.service_fee,
                'remark': '',
            })
            total_amount += self.service_fee
        
        # 押金（仅首次）
        if self.deposit and not self.deposit_generated and self.contract_type != 'property':
            fee_items.append({
                'name': '押金',
                'period': '一次性',
                'months': '-',
                'amount': self.deposit,
                'remark': '',
            })
            total_amount += self.deposit
        
        # 装修垃圾清理费
        if self.garbage_fee:
            fee_items.append({
                'name': '装修垃圾清理费',
                'period': '一次性',
                'months': '-',
                'amount': self.garbage_fee,
                'remark': '',
            })
            total_amount += self.garbage_fee
        
        return {
            'fee_items': fee_items,
            'total_amount': total_amount,
            'period_months': period_months,
            'period_str': period_str,
        }

    @api.model
    def cron_generate_periodic_bills(self):
        """
        自动生成合同的周期性账单（按正常周期）
        优化逻辑：
        1. 使用 next_bill_date 判断出账时间（已考虑 bill_advance_days）
        2. 跳过免租期内的账单
        3. 记录详细的生成日志
        """
        
        # 查找所有执行中的合同，且到达出账日期
        active_contracts = self.search([
            ('state', '=', 'active'),
            ('next_bill_date', '!=', False)
        ])
        
        generated_count = 0
        skipped_count = 0
        error_count = 0
        
        for c in active_contracts:
            today = date.today() + relativedelta(days=c.bill_advance_days or 0)
            _logger.info(f"开始执行自动出账任务，当前日期: {today}")
            try:
                # 1. 检查是否在免租期内
                if c.free_rent_from and c.free_rent_to:
                    if c.free_rent_from <= date.today() <= c.free_rent_to:
                        _logger.info(f"合同 {c.name}: 当前在免租期内 ({c.free_rent_from} 至 {c.free_rent_to})，跳过")
                        # 更新到下一个周期
                        c.next_bill_date = c._get_next_bill_date_after_current()
                        skipped_count += 1
                        continue
                
                # 2. 生成账单
                if c.next_bill_date <= today:
                    _logger.info(f"合同 {c.name}: 开始生成账单，出账日: {c.next_bill_date}")
                    c.action_generate_move()
                    generated_count += 1
                    
                    # 3. 更新下一个账单日期（按正常周期）
                    next_date = c._get_next_bill_date_after_current()
                    _logger.info(f"合同 {c.name}: 账单生成成功，下次出账日: {next_date}")
                
            except Exception as e:
                error_count += 1
                _logger.error(f"合同 {c.name} 生成账单失败: {str(e)}", exc_info=True)
                # 发送错误通知
                try:
                    c.message_post(
                        body=f"自动生成账单失败: {str(e)}",
                        subject="账单生成错误",
                        message_type='notification'
                    )
                except:
                    pass
                continue
        
        # 记录汇总日志
        _logger.info(
            f"自动出账任务完成 - "
            f"检查合同数: {len(active_contracts)}, "
            f"成功生成: {generated_count}, "
            f"跳过: {skipped_count}, "
            f"失败: {error_count}"
        )
        
        return True

    def _get_next_bill_date_after_current(self):
        """
        获取当前账单后的下一个出账日期（按正常周期）
        从当前出账日开始，按照支付周期月数递增
        """
        self.ensure_one()
        
        if not self.payment_frequency:
            return False
        
        # 获取当前出账日
        current_date = self.next_bill_date or self.lease_start_date or date.today()
        
        # 按照支付周期递增
        period_months = {'monthly': 1, 'quarterly': 3, 'half_yearly': 6, 'yearly': 12}.get(self.payment_frequency, 1)
        next_bill_date = current_date + relativedelta(months=period_months)
        
        # 确保不超过租赁结束日
        if self.lease_end_date and next_bill_date > self.lease_end_date:
            return False
        
        return next_bill_date

    @api.model
    def _create_activity(self, res_model, res_id, summary, note):
        self.env['mail.activity'].create({
            'res_model_id': self.env['ir.model']._get(res_model).id,
            'res_id': res_id,
            'activity_type_id': self.env.ref('mail.mail_activity_data_todo').id,
            'summary': summary,
            'note': note,
        })

    @api.model
    def cron_expiry_reminder(self):
        today = date.today()
        for days in (30, 15, 7):
            target = today + relativedelta(days=days)
            contracts = self.search([
                ('state', '=', 'active'),
                ('lease_end_date', '=', target),
            ])
            for c in contracts:
                summary = _('合同到期预警')
                note = _('合同 %s 将在 %s 天后到期（租户/房东：%s）。') % (c.name, days, c.partner_id.name)
                self._create_activity('mall.leasing.contract', c.id, summary, note)
                # 同时提醒相对方
                self._create_activity('res.partner', c.partner_id.id, summary, note)

    @api.model
    def cron_payment_reminders(self):
        # 提醒应收/应付到期与欠费
        Move = self.env['account.move']
        today = date.today()
        soon = today + relativedelta(days=3)
        # 即将到期
        moves_soon = Move.search([
            ('mall_contract_id', '!=', False),
            ('state', '=', 'posted'),
            ('payment_state', 'in', ('not_paid', 'partial')),
            ('invoice_date_due', '>=', today),
            ('invoice_date_due', '<=', soon),
        ])
        for m in moves_soon:
            c = m.mall_contract_id
            summary = _('账款到期提醒')
            who = _('租户') if c.contract_type == 'tenant' else _('房东')
            note = _('合同 %s 的账单将于 %s 到期（%s：%s）。') % (c.name, m.invoice_date_due, who, c.partner_id.name)
            self._create_activity('account.move', m.id, summary, note)
            self._create_activity('res.partner', c.partner_id.id, summary, note)
        # 已逾期
        moves_overdue = Move.search([
            ('mall_contract_id', '!=', False),
            ('state', '=', 'posted'),
            ('payment_state', 'in', ('not_paid', 'partial')),
            ('invoice_date_due', '<', today),
        ])
        for m in moves_overdue:
            c = m.mall_contract_id
            summary = _('欠费预警')
            who = _('租户') if c.contract_type == 'tenant' else _('房东')
            note = _('合同 %s 的账单已于 %s 逾期（%s：%s）。请尽快处理。') % (c.name, m.invoice_date_due, who, c.partner_id.name)
            self._create_activity('account.move', m.id, summary, note)
            self._create_activity('res.partner', c.partner_id.id, summary, note)

    def write(self, vals):
        # 审批后禁止修改合同类型
        if 'contract_type' in vals:
            prohibited_states = ['approved', 'signed', 'active', 'renewed', 'terminated']
            for rec in self:
                if rec.state in prohibited_states:
                    raise UserError(_('审批通过后合同类型不可修改。'))
        res = super().write(vals)
        tracked_fields = ['state', 'rent_amount', 'deposit', 'water_fee', 'electric_fee', 'property_fee', 'garbage_fee', 'payment_frequency', 'payment_day', 'lease_start_date', 'lease_end_date']
        changed = {k: v for k, v in vals.items() if k in tracked_fields}
        for rec in self:
            if changed:
                self.env['mall.leasing.contract.version'].create({
                    'contract_id': rec.id,
                    'change_date': date.today(),
                    'change_note': _('自动记录变更'),
                    'data_json': str({k: rec[k] for k in tracked_fields}),
                })
        return res

class MallLeasingContractVersion(models.Model):
    _name = 'mall.leasing.contract.version'
    _description = '合同历史版本'

    contract_id = fields.Many2one('mall.leasing.contract', string='合同', required=True, ondelete='cascade')
    change_date = fields.Date('变更日期', required=True)
    change_note = fields.Char('备注')
    data_json = fields.Text('快照数据')