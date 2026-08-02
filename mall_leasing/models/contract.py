# -*- coding: utf-8 -*-
import calendar
import logging
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# 支付周期对应的月数
PAYMENT_PERIOD_MONTHS = {
    'monthly': 1,
    'quarterly': 3,
    'half_yearly': 6,
    'yearly': 12,
}

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
        ('cancelled', '已作废'),
    ], string='状态', default='draft', tracking=True)

    currency_id = fields.Many2one('res.currency', string='币种', default=lambda self: self.env.company.currency_id.id)

    # 首期租金（随首期比例与每期租金同步计算，审批前可覆盖）
    first_rent_amount = fields.Monetary(
        '首期租金',
        currency_field='currency_id',
        compute='_compute_first_period_ratio',
        store=True,
        readonly=False,
    )
    # 首期租金已生成
    first_rent_generated = fields.Boolean('首期租金已生成', default=False, help='标记首期租金是否已经生成过账单')
    # 首期账单比例（起租日所在周期：扣除免租后的应收比例）
    first_period_ratio = fields.Float(
        '首期账单比例',
        compute='_compute_first_period_ratio',
        store=True,
        digits=(5, 4),
        help='首期账单按实际天数占周期总天数的比例计算',
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
    # 水电费单价：仅备查，不参与自动出账
    water_fee = fields.Monetary(
        '水费单价',
        currency_field='currency_id',
        help='物业合同水电单价备查，生成账单时不会自动出账。',
    )
    electric_fee = fields.Monetary(
        '电费单价',
        currency_field='currency_id',
        help='物业合同水电单价备查，生成账单时不会自动出账。',
    )
    # 装修垃圾清理费
    garbage_fee = fields.Monetary('装修垃圾清理费', currency_field='currency_id')
    # 装修垃圾清理费已生成（一次性费用，防止每期重复出账）
    garbage_fee_generated = fields.Boolean(
        '装修垃圾清理费已生成',
        default=False,
        help='标记装修垃圾清理费是否已经生成过账单',
    )
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
    # 免租默认只影响租金；物业/服务费需显式开启才会按免租折算
    free_rent_applies_to_property_fee = fields.Boolean(
        '免租期适用于物业费',
        default=False,
        help='关闭（默认）：免租期只折算租金，物业费/服务费仍全额（仍会按租期截断折算）。'
             '开启后，免租重叠天数同样折算物业费与服务费。',
    )

    escalation_rate = fields.Float('递增率(%)', help='例如每年递增5%，填写5')
    # 递增起始年（从第几年开始递增）
    escalation_start_year = fields.Integer(
        '递增起始年', 
        default=1, 
        help='从第几年开始执行递增，例如：1表示第1年就开始递增，3表示前2年不变、从第3年开始递增'
    )
    # 递增周期（每隔几年递增一次）
    escalation_term = fields.Integer('递增周期（年）', default=1, help='每隔几年执行一次递增')
    # 递增周期已递增（至少执行过一次递增后为 True，避免参数变更覆盖下次递增日）
    escalation_term_generated = fields.Boolean(
        '本周期已递增',
        default=False,
        help='标记是否已经执行过租金递增；执行后不再因参数变更重置下次递增日',
    )
    # 下次递增日期（可写；出账时到期自动调价并推进）
    escalation_term_end_date = fields.Date('下次递增日期')

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

    # 下次出账日：可写；初始会跳过覆盖起租日的免租段，出账成功后按周期推进
    next_bill_date = fields.Date(
        '下次出账日',
        help='默认从起租日起算；若免租覆盖起租日，则从免租结束次日开始。'
             '出账成功后按支付周期推进，并自动跳过整期免租的账期。',
    )

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

    # 作废信息
    cancel_reason = fields.Text('作废原因', tracking=True, copy=False)
    cancel_date = fields.Date('作废日期', copy=False, readonly=True)
    cancelled_by_id = fields.Many2one(
        'res.users', string='作废人', copy=False, readonly=True,
    )
    # 作废后重建：原合同 ↔ 新合同
    source_contract_id = fields.Many2one(
        'mall.leasing.contract',
        string='来源合同',
        copy=False,
        readonly=True,
        help='由作废合同复制创建时记录来源。',
    )
    replacement_contract_ids = fields.One2many(
        'mall.leasing.contract',
        'source_contract_id',
        string='替代合同',
        readonly=True,
    )
    replacement_contract_count = fields.Integer(
        '替代合同数',
        compute='_compute_replacement_contract_count',
    )

    # Odoo 19：SQL 约束改为 declarative Constraint
    _name_unique = models.Constraint(
        'UNIQUE(name)',
        '合同编号必须唯一。',
    )

    @api.depends('replacement_contract_ids')
    def _compute_replacement_contract_count(self) -> None:
        for rec in self:
            rec.replacement_contract_count = len(rec.replacement_contract_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) in [False, _('New')]:
                vals['name'] = self.env['ir.sequence'].next_by_code('mall.leasing.contract') or _('New')
        records = super().create(vals_list)
        # 初始化下次出账日 / 首次递增日（依赖 create 后字段齐全，以便跳过免租期）
        for rec, vals in zip(records, vals_list):
            if not vals.get('next_bill_date') and rec.lease_start_date:
                rec.next_bill_date = rec._get_initial_next_bill_date()
            if not rec.escalation_term_end_date:
                first_esc = rec._get_first_escalation_date()
                if first_esc:
                    rec.escalation_term_end_date = first_esc
        return records

    def _get_period_months(self) -> int:
        """当前合同支付周期对应的月数。"""
        self.ensure_one()
        return PAYMENT_PERIOD_MONTHS.get(self.payment_frequency, 1)

    def _should_defer_billing_for_free_rent(self) -> bool:
        """
        是否因免租推迟「下次出账日」。
        - 租户/房东合同：租金受免租影响，需跳过
        - 物业合同：仅当勾选「免租期适用于物业费」时跳过
        """
        self.ensure_one()
        if self.contract_type in ('tenant', 'landlord'):
            return True
        if self.contract_type == 'property':
            return bool(self.free_rent_applies_to_property_fee)
        return False

    def _get_initial_next_bill_date(self):
        """
        计算合同初始下次出账日。
        若免租覆盖起租日且本类型费用受免租影响，则从免租结束日的次日开始出账。
        """
        self.ensure_one()
        start = self.lease_start_date
        if not start:
            return False

        if (
            self._should_defer_billing_for_free_rent()
            and self.free_rent_from
            and self.free_rent_to
            and self.free_rent_from <= start <= self.free_rent_to
        ):
            candidate = self.free_rent_to + relativedelta(days=1)
            if self.lease_end_date and candidate > self.lease_end_date:
                return False
            return candidate
        return start

    def _skip_fully_free_rent_bill_dates(self, bill_date):
        """
        若账期起点落在整期免租内，按支付周期推进，直到出现应收天数或超过租期。
        """
        self.ensure_one()
        if not bill_date or not self._should_defer_billing_for_free_rent():
            return bill_date
        if not self.free_rent_from or not self.free_rent_to or not self.payment_frequency:
            return bill_date

        period_months = self._get_period_months()
        # 最多跳过 36 个周期，防止异常数据死循环
        for _unused in range(36):
            ratio = self._get_period_bill_ratio(
                bill_date, apply_free_rent=True,
            )[0]
            if ratio > 0:
                return bill_date
            advanced = bill_date + relativedelta(months=period_months)
            # 仍落在免租期内时，直接跳到免租结束次日，避免逐期空转
            after_free = self.free_rent_to + relativedelta(days=1)
            if advanced <= self.free_rent_to:
                bill_date = after_free
            else:
                bill_date = advanced
            if self.lease_end_date and bill_date > self.lease_end_date:
                return False
        return bill_date

    def _get_first_escalation_date(self):
        """
        计算首次递增日期。
        起始年=1、周期=1 → 起租日 + 1 年；起始年=3、周期=1 → 起租日 + 3 年。
        """
        self.ensure_one()
        if not self.lease_start_date or not self.escalation_term:
            return False
        start_year = self.escalation_start_year or 1
        years_until_escalation = (start_year - 1) + self.escalation_term
        return self.lease_start_date + relativedelta(years=years_until_escalation)

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

    @api.depends(
        'lease_start_date', 'payment_frequency', 'free_rent_from', 'free_rent_to',
        'free_rent_applies_to_property_fee', 'contract_type',
        'rent_amount', 'lease_end_date',
    )
    def _compute_first_period_ratio(self):
        """按实际首次出账日起算首期比例与首期租金（已跳过起租免租段）。"""
        for rec in self:
            bill_start = rec._get_initial_next_bill_date()
            if not bill_start or not rec.payment_frequency:
                rec.first_period_ratio = 1.0
                rec.first_rent_amount = rec.rent_amount
                continue
            ratio = rec._get_period_bill_ratio(bill_start)[0]
            rec.first_period_ratio = ratio
            rec.first_rent_amount = round((rec.rent_amount or 0.0) * ratio, 2)

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

        # 重叠开始日 = max(免租开始日, 期间开始日)
        overlap_start = max(self.free_rent_from, period_start)
        # 重叠结束日 = min(免租结束日, 期间结束日-1天)
        overlap_end = min(self.free_rent_to, period_end - relativedelta(days=1))

        if overlap_start <= overlap_end:
            return (overlap_end - overlap_start).days + 1
        return 0

    def _get_period_bill_ratio(self, period_start, apply_free_rent: bool = True):
        """
        计算账期应收比例 = 应收天数 / 完整周期天数。
        应收天数 = min(周期结束, 租期结束) 内的日历天数 −（可选）免租重叠天数。
        :param apply_free_rent: 是否扣除免租天数（物业费默认 False，见 free_rent_applies_to_property_fee）
        :return: (ratio, period_start, bill_end_inclusive)
        """
        self.ensure_one()
        period_months = self._get_period_months()
        full_period_end = period_start + relativedelta(months=period_months)
        full_period_days = (full_period_end - period_start).days
        if full_period_days <= 0:
            return 1.0, period_start, period_start

        # 账单周期闭区间结束日，不超过租期结束
        bill_end_inclusive = full_period_end - relativedelta(days=1)
        if self.lease_end_date and bill_end_inclusive > self.lease_end_date:
            bill_end_inclusive = self.lease_end_date
        if bill_end_inclusive < period_start:
            return 0.0, period_start, period_start

        period_end_exclusive = bill_end_inclusive + relativedelta(days=1)
        calendar_days = (period_end_exclusive - period_start).days
        free_days = 0
        if apply_free_rent:
            free_days = self._calculate_free_rent_days_in_period(period_start, period_end_exclusive)
        billable_days = max(calendar_days - free_days, 0)
        ratio = round(billable_days / full_period_days, 4)
        return ratio, period_start, bill_end_inclusive

    def _get_invoice_due_date(self, invoice_date):
        """按支付日计算到期日：本月 payment_day；若早于发票日则顺延至下月。"""
        self.ensure_one()
        if not invoice_date:
            return False
        day = self.payment_day or 1
        last_day = calendar.monthrange(invoice_date.year, invoice_date.month)[1]
        due = invoice_date.replace(day=min(max(day, 1), last_day))
        if due < invoice_date:
            next_month = invoice_date + relativedelta(months=1)
            last_day_next = calendar.monthrange(next_month.year, next_month.month)[1]
            due = next_month.replace(day=min(max(day, 1), last_day_next))
        return due

    def _apply_escalation_if_due(self) -> None:
        """
        出账前：若下次出账日已到达递增日，则按合同类型调价并推进下次递增日。
        - 租赁/房东合同：递增租金
        - 物业合同：递增物业费与服务费
        """
        self.ensure_one()
        if not self.escalation_rate or not self.escalation_term_end_date or not self.next_bill_date:
            return
        term_years = self.escalation_term or 1
        factor = 1 + self.escalation_rate / 100.0
        safety = 0
        while (
            self.escalation_term_end_date
            and self.next_bill_date >= self.escalation_term_end_date
            and safety < 50
        ):
            safety += 1
            if self.lease_end_date and self.escalation_term_end_date > self.lease_end_date:
                break

            notes: list[str] = []
            if self.contract_type == 'property':
                # 有单价+面积时只递增单价，由计算字段刷新物业费，避免双重递增
                if self.property_fee_unit and self.lease_area:
                    old_unit = self.property_fee_unit
                    old_fee = self.property_fee
                    self.property_fee_unit = round(old_unit * factor, 2)
                    notes.append(
                        _('物业费单价 %(old_u)s → %(new_u)s（物业费 %(old_f)s → %(new_f)s）') % {
                            'old_u': old_unit,
                            'new_u': self.property_fee_unit,
                            'old_f': old_fee,
                            'new_f': self.property_fee,
                        }
                    )
                elif self.property_fee:
                    old_fee = self.property_fee
                    self.property_fee = round(old_fee * factor, 2)
                    notes.append(_('物业费 %(old)s → %(new)s') % {
                        'old': old_fee, 'new': self.property_fee,
                    })
                if self.service_fee:
                    old_svc = self.service_fee
                    self.service_fee = round(old_svc * factor, 2)
                    notes.append(_('服务费 %(old)s → %(new)s') % {
                        'old': old_svc, 'new': self.service_fee,
                    })
            else:
                old_rent = self.rent_amount or 0.0
                self.rent_amount = round(old_rent * factor, 2)
                notes.append(_('租金 %(old)s → %(new)s') % {
                    'old': old_rent, 'new': self.rent_amount,
                })

            self.escalation_term_generated = True
            self.escalation_term_end_date = self.escalation_term_end_date + relativedelta(years=term_years)
            if notes:
                self.message_post(
                    body=_('费用递增生效（递增率 %(rate)s%%）：%(detail)s') % {
                        'rate': self.escalation_rate,
                        'detail': '；'.join(notes),
                    }
                )

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

    def _create_single_move(
        self,
        fee_name,
        fee_amount,
        journal,
        account,
        company,
        bill_period_start_date,
        bill_period_end_date,
    ):
        """
        为单个费用类型创建会计凭证并过账。
        """
        if not fee_amount or fee_amount <= 0:
            return None

        invoice_date = bill_period_start_date or self.next_bill_date or date.today()
        move_vals = {
            'move_type': 'out_invoice' if self.contract_type in ['tenant', 'property'] else 'in_invoice',
            'partner_id': self.partner_id.id,
            'ref': f'合同# {self.name} - {fee_name}',
            'invoice_date': invoice_date,
            'invoice_date_due': self._get_invoice_due_date(invoice_date),
            'journal_id': journal.id,
            'company_id': company.id,
            'invoice_line_ids': [Command.create({
                'name': fee_name,
                'quantity': 1.0,
                'price_unit': fee_amount,
                'account_id': account.id,
            })],
            'mall_contract_id': self.id,
            'bill_period_start_date': bill_period_start_date,
            'bill_period_end_date': bill_period_end_date,
        }
        account_move = self.env['account.move'].sudo().create(move_vals)
        account_move.action_post()
        return account_move

    def _prepare_bill_fee_types(self, rent_ratio: float, property_ratio: float) -> list:
        """
        按合同类型组装本期费用清单。
        - 租金使用 rent_ratio（含免租折算）
        - 物业费/服务费使用 property_ratio（默认不含免租，见 free_rent_applies_to_property_fee）
        - 一次性费用各自用 generated 标记防重
        租户合同不再出物业费，避免与物业合同重复收费。
        """
        self.ensure_one()
        fee_types: list[tuple[str, float]] = []

        def add_recurring(label: str, amount: float, ratio: float) -> None:
            if not amount or ratio <= 0:
                return
            if ratio < 1.0:
                fee_types.append((f'{label}（按比例）', round(amount * ratio, 2)))
            else:
                fee_types.append((label, amount))

        if self.contract_type in ('tenant', 'landlord'):
            add_recurring(_('租金'), self.rent_amount or 0.0, rent_ratio)

        if self.contract_type == 'tenant':
            if not self.deposit_generated and self.deposit:
                fee_types.append((_('押金'), self.deposit))

        if self.contract_type == 'property':
            add_recurring(_('物业费'), self.property_fee or 0.0, property_ratio)
            add_recurring(_('服务费'), self.service_fee or 0.0, property_ratio)
            # 水电费仅为单价备查，不自动出账
            if not self.decoration_deposit_generated and self.decoration_deposit:
                fee_types.append((_('装修保证金'), self.decoration_deposit))
            if not self.garbage_fee_generated and self.garbage_fee:
                fee_types.append((_('装修垃圾清理费'), self.garbage_fee))

        return fee_types

    def _is_mall_manager(self) -> bool:
        """主管或系统管理员。"""
        return bool(
            self.env.su
            or self.env.user.has_group('mall_leasing.group_mall_leasing_manager')
            or self.env.user.has_group('base.group_system')
        )

    def _is_mall_finance(self) -> bool:
        """财务、主管或系统管理员。"""
        return bool(
            self.env.su
            or self.env.user.has_group('mall_leasing.group_mall_leasing_finance')
            or self._is_mall_manager()
        )

    def _is_mall_operator(self) -> bool:
        """运营、主管或系统管理员。"""
        return bool(
            self.env.su
            or self.env.user.has_group('mall_leasing.group_mall_leasing_operator')
            or self.env.user.has_group('base.group_system')
        )

    def _ensure_mall_manager(self) -> None:
        if not self._is_mall_manager():
            raise UserError(_('仅主管可执行合同审核与管理操作。'))

    def _ensure_mall_finance(self) -> None:
        if not self._is_mall_finance():
            raise UserError(_('仅财务可管理租赁账单与发票。'))

    def _ensure_mall_operator(self) -> None:
        if not self._is_mall_operator():
            raise UserError(_('仅运营可创建或维护合同。'))

    def action_approve(self):
        """审核通过（主管）。"""
        self.ensure_one()
        self._ensure_mall_manager()
        if self.state != 'draft':
            raise UserError(_('只有草稿状态的合同才能审核'))

        self.state = 'approved'
        self.message_post(body=_('合同已审核通过'))

        self.activity_schedule(
            'mail.mail_activity_data_todo',
            summary=_('合同审核通过'),
            note=_('合同 %s 已审核通过，可以进行签约') % self.name,
            user_id=self.env.user.id,
        )
        return True

    def action_reject(self):
        """审核拒绝（主管）。"""
        self.ensure_one()
        self._ensure_mall_manager()
        if self.state != 'draft':
            raise UserError(_('只有草稿状态的合同才能拒绝'))

        self.message_post(body=_('合同审核被拒绝，请修改后重新提交'))

        self.activity_schedule(
            'mail.mail_activity_data_todo',
            summary=_('合同审核被拒绝'),
            note=_('合同 %s 审核被拒绝，请修改后重新提交审核') % self.name,
            user_id=self.env.user.id,
        )
        return True

    def action_sign(self):
        """签约（主管）。"""
        self.ensure_one()
        self._ensure_mall_manager()
        if self.state != 'approved':
            raise UserError(_('只有已审核通过的合同才能签约'))

        self.state = 'signed'
        self.message_post(body=_('合同已签约'))

        self.activity_schedule(
            'mail.mail_activity_data_todo',
            summary=_('合同已签约'),
            note=_('合同 %s 已签约，可以开始执行') % self.name,
            user_id=self.env.user.id,
        )
        return True

    def action_active(self):
        """激活合同（主管）。"""
        self.ensure_one()
        self._ensure_mall_manager()
        if self.state != 'signed':
            raise UserError(_('只有已签约的合同才能激活'))

        self.state = 'active'
        self.message_post(body=_('合同已激活'))

        self.activity_schedule(
            'mail.mail_activity_data_todo',
            summary=_('合同已激活'),
            note=_('合同 %s 已激活，可以开始执行') % self.name,
            user_id=self.env.user.id,
        )
        return True

    def action_open_cancel_wizard(self) -> dict:
        """打开作废向导（仅主管）。"""
        self.ensure_one()
        self._ensure_mall_manager()
        if self.state in ('cancelled', 'terminated'):
            raise UserError(_('该合同已结束，无法再次作废。'))
        if self.state == 'draft':
            raise UserError(_('草稿合同可直接删除或修改，无需作废。请删除草稿或提交后再作废。'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('作废合同'),
            'res_model': 'mall.leasing.contract.cancel.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_contract_id': self.id,
            },
        }

    def action_cancel(self, reason: str = '') -> bool:
        """
        主管确认作废合同。
        作废后不可继续出账或状态流转；可基于本单创建新合同。
        """
        self.ensure_one()
        self._ensure_mall_manager()
        if self.state in ('cancelled', 'terminated', 'draft'):
            raise UserError(_('当前状态的合同不能作废。'))
        if not (reason or self.cancel_reason):
            raise UserError(_('请填写作废原因。'))

        self.write({
            'state': 'cancelled',
            'cancel_reason': reason or self.cancel_reason,
            'cancel_date': fields.Date.context_today(self),
            'cancelled_by_id': self.env.user.id,
        })
        self.message_post(body=_('合同已作废。原因：%s') % (reason or self.cancel_reason))
        return True

    def _prepare_copy_vals_from_cancelled(self) -> dict:
        """从作废合同组装新建草稿合同的字段值。"""
        self.ensure_one()
        return {
            'contract_type': self.contract_type,
            'mall_id': self.mall_id.id,
            'facade_ids': [Command.set(self.facade_ids.ids)],
            'operator_id': self.operator_id.id,
            'property_company_id': self.property_company_id.id,
            'partner_id': self.partner_id.id,
            'landlord_id': self.landlord_id.id,
            'shop_name': self.shop_name,
            'currency_id': self.currency_id.id,
            'rent_amount': self.rent_amount,
            'deposit': self.deposit,
            'lease_area': self.lease_area,
            'property_fee_unit': self.property_fee_unit,
            'property_fee': self.property_fee,
            'service_fee': self.service_fee,
            'water_fee': self.water_fee,
            'electric_fee': self.electric_fee,
            'garbage_fee': self.garbage_fee,
            'decoration_deposit': self.decoration_deposit,
            'payment_frequency': self.payment_frequency,
            'payment_day': self.payment_day,
            'bank_account': self.bank_account,
            'bank_account_name': self.bank_account_name,
            'bank_name': self.bank_name,
            'bank_account_number': self.bank_account_number,
            'lease_term': self.lease_term,
            'lease_start_date': self.lease_start_date,
            'lease_end_date': self.lease_end_date,
            'free_rent_from': self.free_rent_from,
            'free_rent_to': self.free_rent_to,
            'free_rent_applies_to_property_fee': self.free_rent_applies_to_property_fee,
            'escalation_rate': self.escalation_rate,
            'escalation_start_year': self.escalation_start_year,
            'escalation_term': self.escalation_term,
            'introducer_id': self.introducer_id.id,
            'commission_type': self.commission_type,
            'commission_amount': self.commission_amount,
            'bill_advance_days': self.bill_advance_days,
            'source_contract_id': self.id,
            'state': 'draft',
            # 出账标记重置，由新合同重新起算
            'first_rent_generated': False,
            'deposit_generated': False,
            'garbage_fee_generated': False,
            'decoration_deposit_generated': False,
            'escalation_term_generated': False,
            'next_bill_date': False,
            'escalation_term_end_date': False,
        }

    def action_create_from_cancelled(self) -> dict:
        """
        基于作废合同创建新草稿合同，并带入原合同信息。
        运营/主管均可操作。
        """
        self.ensure_one()
        self._ensure_mall_operator()
        if self.state != 'cancelled':
            raise UserError(_('仅已作废的合同可创建替代合同。'))

        new_contract = self.env['mall.leasing.contract'].create(
            self._prepare_copy_vals_from_cancelled()
        )
        self.message_post(
            body=_('已基于本作出废合同创建新合同 %s') % new_contract.name
        )
        new_contract.message_post(
            body=_('本单由作废合同 %s 复制创建') % self.name
        )
        return {
            'type': 'ir.actions.act_window',
            'name': _('新合同'),
            'res_model': 'mall.leasing.contract',
            'res_id': new_contract.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_replacement_contracts(self) -> dict:
        """查看由本作出废合同生成的替代合同。"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('替代合同'),
            'res_model': 'mall.leasing.contract',
            'view_mode': 'list,form',
            'domain': [('source_contract_id', '=', self.id)],
            'context': {'default_source_contract_id': self.id},
        }

    def action_create_property_contract(self):
        """
        从租赁合同创建关联物业合同（运营/主管）。
        同步租期、支付条款与费用字段；免租日期仅作参考，默认不折算物业费。
        """
        self.ensure_one()
        self._ensure_mall_operator()
        # 租赁面积：优先合同字段，否则汇总关联门面面积
        lease_area = self.lease_area or sum(self.facade_ids.mapped('area'))
        vals = {
            'contract_type': 'property',
            'mall_id': self.mall_id.id,
            'facade_ids': [Command.set(self.facade_ids.ids)],
            'operator_id': self.operator_id.id,
            'partner_id': self.partner_id.id,
            'property_company_id': self.property_company_id.id,
            'shop_name': self.shop_name,
            'currency_id': self.currency_id.id,
            'bank_account': self.bank_account,
            'bank_account_name': self.bank_account_name,
            'bank_name': self.bank_name,
            'bank_account_number': self.bank_account_number,
            'lease_term': self.lease_term,
            'lease_start_date': self.lease_start_date,
            'lease_end_date': self.lease_end_date,
            'payment_frequency': self.payment_frequency,
            'payment_day': self.payment_day,
            'bill_advance_days': self.bill_advance_days,
            # 免租日期保留备查；物业费默认不参与免租折算
            'free_rent_from': self.free_rent_from,
            'free_rent_to': self.free_rent_to,
            'free_rent_applies_to_property_fee': False,
            'escalation_rate': self.escalation_rate,
            'escalation_start_year': self.escalation_start_year,
            'escalation_term': self.escalation_term,
            'next_bill_date': self.lease_start_date,
            # 费用字段
            'lease_area': lease_area,
            'property_fee_unit': self.property_fee_unit,
            'property_fee': self.property_fee,
            'service_fee': self.service_fee,
            'decoration_deposit': self.decoration_deposit,
            'garbage_fee': self.garbage_fee,
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
        action = self.env['ir.actions.act_window']._for_xml_id(
            'mall_leasing.action_property_contracts'
        )
        # 基础筛选：物业合同 + 同商场/同房号/同租户
        domain = [('contract_type', '=', 'property')]
        if self.mall_id:
            domain.append(('mall_id', '=', self.mall_id.id))
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
            'default_facade_ids': [Command.set(self.facade_ids.ids)],
            'default_operator_id': self.operator_id.id,
            'default_partner_id': self.partner_id.id,
            'default_property_company_id': self.property_company_id.id,
        })
        action['context'] = ctx

        # 若仅有一个匹配，直接打开表单视图
        records = self.env['mall.leasing.contract'].search(domain, limit=2)
        if len(records) == 1:
            form_view = self.env.ref('mall_leasing.view_mall_contract_form').id
            action['views'] = [(form_view, 'form')]
            action['res_id'] = records.id
        return action

    def action_view_tenant_contracts(self):
        """查看相关的租户合同"""
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'mall_leasing.action_tenant_contracts'
        )
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
            'default_facade_ids': [Command.set(self.facade_ids.ids)],
            'default_operator_id': self.operator_id.id,
            'default_partner_id': self.partner_id.id,
            'default_property_company_id': self.property_company_id.id,
        })
        action['context'] = ctx

        records = self.env['mall.leasing.contract'].search(domain, limit=2)
        if len(records) == 1:
            form_view = self.env.ref('mall_leasing.view_mall_contract_form').id
            action['views'] = [(form_view, 'form')]
            action['res_id'] = records.id
        return action

    def action_generate_move(self):
        """
        生成合同对应的会计凭证：按费用拆票（财务）。
        - 每期按免租重叠与租期截断计算应收比例
        - 一次性费用（押金/保证金/垃圾费）用 generated 标记防重
        - 出账前按递增条款调价
        """
        self.ensure_one()
        self._ensure_mall_finance()

        if self.state != 'active':
            raise UserError(_('只有执行中的合同才能生成账单'))
        if not self.lease_start_date:
            raise UserError(_('请先设置租赁开始日期'))
        if not self.payment_frequency:
            raise UserError(_('请先设置支付方式'))
        if not self.next_bill_date:
            raise UserError(_('请先设置下次出账日'))
        if self.lease_end_date and self.next_bill_date > self.lease_end_date:
            raise UserError(_('下次出账日已超过租赁结束日，无法继续出账'))

        # 允许按 bill_advance_days 提前出账
        if self.next_bill_date > date.today() + timedelta(days=self.bill_advance_days or 0):
            raise UserError(_('未到出账日，不能生成账单！'))

        # 同账期幂等：已有未作废账单则拒绝
        existing = self.invoice_ids.filtered(
            lambda m: m.state != 'cancel' and m.bill_period_start_date == self.next_bill_date
        )
        if existing:
            raise UserError(_('该账期已生成账单，请勿重复出账。'))

        # 递增到期则先调价，再算出账金额
        self._apply_escalation_if_due()

        # 租金比例含免租；物业费比例默认仅租期截断，除非开启 free_rent_applies_to_property_fee
        rent_ratio, period_start, period_end = self._get_period_bill_ratio(
            self.next_bill_date, apply_free_rent=True,
        )
        # 不可用 _ 丢弃返回值：会遮蔽 gettext 的 _，导致后续 _('...') 报错
        property_ratio = self._get_period_bill_ratio(
            self.next_bill_date,
            apply_free_rent=bool(self.free_rent_applies_to_property_fee),
        )[0]
        fee_types = self._prepare_bill_fee_types(rent_ratio, property_ratio)
        _logger.info(
            '合同 %s 出账：周期 %s ~ %s，租金比例 %s，物业比例 %s，费用 %s',
            self.name, period_start, period_end, rent_ratio, property_ratio, fee_types,
        )

        # 整期免租且无一次性费用：推进出账日，不报错（避免 Cron 卡住）
        if not fee_types:
            self.first_rent_generated = True
            self.next_bill_date = self._get_next_bill_date_after_current()
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('出账跳过'),
                    'message': _('本期无可出账费用（可能整期免租），已推进下次出账日。'),
                    'type': 'warning',
                    'sticky': False,
                },
            }

        journal, account, company = self._get_journal_and_account()
        created_moves = []
        for fee_name, fee_amount in fee_types:
            move = self._create_single_move(
                fee_name, fee_amount, journal, account, company, period_start, period_end,
            )
            if not move:
                continue
            created_moves.append(move)
            if fee_name == _('押金'):
                self.deposit_generated = True
            if _('装修保证金') in fee_name:
                self.decoration_deposit_generated = True
            if _('装修垃圾清理费') in fee_name:
                self.garbage_fee_generated = True

        if not created_moves:
            raise UserError(_('没有需要生成凭证的费用项目'))

        self.first_rent_generated = True
        self.next_bill_date = self._get_next_bill_date_after_current()

        if len(created_moves) == 1:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'account.move',
                'res_id': created_moves[0].id,
                'view_mode': 'form',
                'target': 'current',
            }
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
        
        period_months = self._get_period_months()

        # 计算费用产生时间段
        start_date = self.next_bill_date or self.lease_start_date or date.today()
        end_date = start_date + relativedelta(months=period_months, days=-1)
        if self.lease_end_date and end_date > self.lease_end_date:
            end_date = self.lease_end_date
        
        # 格式化日期
        period_start_str = start_date.strftime('%Y年%m月%d日') if start_date else ''
        period_end_str = end_date.strftime('%Y年%m月%d日') if end_date else ''
        period_str = f"{period_start_str} 至 {period_end_str}" if period_start_str else ''
        
        # 与出账一致：租金含免租折算；物业/服务费按配置决定是否含免租
        bill_start = self.next_bill_date or self.lease_start_date or date.today()
        # 不可用 _ 丢弃返回值：会遮蔽 gettext 的 _
        rent_ratio = self._get_period_bill_ratio(bill_start, apply_free_rent=True)[0]
        property_ratio = self._get_period_bill_ratio(
            bill_start,
            apply_free_rent=bool(self.free_rent_applies_to_property_fee),
        )[0]

        fee_items = []
        total_amount = 0.0

        # 商铺租金（仅非物业合同）
        if self.rent_amount and self.contract_type != 'property':
            rent_bill = round(self.rent_amount * rent_ratio, 2)
            fee_items.append({
                'name': '商铺租金',
                'period': period_str,
                'months': period_months,
                'amount': rent_bill,
                'remark': _('按比例 %s') % rent_ratio if rent_ratio < 1.0 else '',
            })
            total_amount += rent_bill

        # 物业费/服务费：仅物业合同展示（与出账职责一致）
        if self.contract_type == 'property' and self.property_fee:
            property_bill = round(self.property_fee * property_ratio, 2)
            fee_items.append({
                'name': '物业费',
                'period': period_str,
                'months': period_months,
                'amount': property_bill,
                'remark': _('按比例 %s') % property_ratio if property_ratio < 1.0 else '',
            })
            total_amount += property_bill

        if self.contract_type == 'property' and self.service_fee:
            service_bill = round(self.service_fee * property_ratio, 2)
            fee_items.append({
                'name': '服务费',
                'period': period_str,
                'months': period_months,
                'amount': service_bill,
                'remark': _('按比例 %s') % property_ratio if property_ratio < 1.0 else '',
            })
            total_amount += service_bill

        # 押金（仅首次，非物业合同）
        if self.deposit and not self.deposit_generated and self.contract_type != 'property':
            fee_items.append({
                'name': '押金',
                'period': '一次性',
                'months': '-',
                'amount': self.deposit,
                'remark': '',
            })
            total_amount += self.deposit

        # 装修垃圾清理费 / 装修保证金：仅物业合同、未出过账时展示
        if (
            self.contract_type == 'property'
            and self.garbage_fee
            and not self.garbage_fee_generated
        ):
            fee_items.append({
                'name': '装修垃圾清理费',
                'period': '一次性',
                'months': '-',
                'amount': self.garbage_fee,
                'remark': '',
            })
            total_amount += self.garbage_fee

        if (
            self.contract_type == 'property'
            and self.decoration_deposit
            and not self.decoration_deposit_generated
        ):
            fee_items.append({
                'name': '装修保证金',
                'period': '一次性',
                'months': '-',
                'amount': self.decoration_deposit,
                'remark': '',
            })
            total_amount += self.decoration_deposit

        return {
            'fee_items': fee_items,
            'total_amount': total_amount,
            'period_months': period_months,
            'period_str': period_str,
        }

    @api.model
    def cron_generate_periodic_bills(self):
        """
        自动生成执行中合同的周期性账单。
        免租折算由 action_generate_move 统一处理，此处不再按免租日推进出账日。
        """
        active_contracts = self.search([
            ('state', '=', 'active'),
            ('next_bill_date', '!=', False),
        ])

        generated_count = 0
        skipped_count = 0
        error_count = 0

        for contract in active_contracts:
            due_by = date.today() + relativedelta(days=contract.bill_advance_days or 0)
            if not contract.next_bill_date or contract.next_bill_date > due_by:
                skipped_count += 1
                continue
            try:
                _logger.info(
                    '合同 %s: 开始自动出账，出账日 %s',
                    contract.name, contract.next_bill_date,
                )
                contract.action_generate_move()
                generated_count += 1
                _logger.info(
                    '合同 %s: 出账完成，下次出账日 %s',
                    contract.name, contract.next_bill_date,
                )
            except Exception as exc:
                error_count += 1
                _logger.error(
                    '合同 %s 生成账单失败: %s', contract.name, exc, exc_info=True,
                )
                contract.message_post(
                    body=_('自动生成账单失败: %s') % exc,
                    subject=_('账单生成错误'),
                    message_type='notification',
                )

        _logger.info(
            '自动出账任务完成 - 检查: %s, 成功: %s, 未到期跳过: %s, 失败: %s',
            len(active_contracts), generated_count, skipped_count, error_count,
        )
        return True

    def _get_next_bill_date_after_current(self):
        """
        获取当前账单后的下一个出账日期（按支付周期递增）。
        整期免租的账期会继续跳过；超过租期结束日则返回 False。
        """
        self.ensure_one()

        if not self.payment_frequency:
            return False

        current_date = self.next_bill_date or self.lease_start_date or date.today()
        next_bill_date = current_date + relativedelta(months=self._get_period_months())

        if self.lease_end_date and next_bill_date > self.lease_end_date:
            return False

        return self._skip_fully_free_rent_bill_dates(next_bill_date)

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
        # 运营（非主管）：仅可改草稿合同
        if (
            not self.env.su
            and self.env.user.has_group('mall_leasing.group_mall_leasing_operator')
            and not self._is_mall_manager()
            and any(rec.state != 'draft' for rec in self)
        ):
            raise UserError(_('运营仅可修改草稿状态的合同，审批后请联系主管处理。'))

        # 财务（非主管/运营）：禁止直接改合同状态与关键商务字段
        if (
            not self.env.su
            and self.env.user.has_group('mall_leasing.group_mall_leasing_finance')
            and not self._is_mall_manager()
            and not self.env.user.has_group('mall_leasing.group_mall_leasing_operator')
        ):
            blocked = {
                'state', 'contract_type', 'mall_id', 'facade_ids', 'partner_id',
                'shop_name', 'operator_id', 'property_company_id', 'landlord_id',
                'lease_term', 'lease_start_date', 'lease_end_date',
                'deposit', 'commission_type', 'commission_amount', 'introducer_id',
            }
            if blocked & set(vals):
                raise UserError(_('财务可查合同并管理账单，不可修改合同商务条款或状态。'))

        # 审批后禁止修改合同类型
        if 'contract_type' in vals:
            prohibited_states = ['approved', 'signed', 'active', 'renewed', 'terminated', 'cancelled']
            for rec in self:
                if rec.state in prohibited_states:
                    raise UserError(_('审批通过后合同类型不可修改。'))

        # 已作废合同禁止再改商务字段（仅允许 chatter 等系统写入由权限控制）
        if not self.env.su and any(rec.state == 'cancelled' for rec in self):
            mutable_when_cancelled = {
                'message_follower_ids', 'message_ids', 'activity_ids',
                'replacement_contract_ids',
            }
            if set(vals) - mutable_when_cancelled:
                raise UserError(_('已作废合同不可修改，请基于作废合同创建新合同。'))
        res = super().write(vals)

        # 尚未出过账时：起租/免租/支付方式变更则重算下次出账日；递增参数变更则重置首次递增日
        billing_trigger_keys = {
            'lease_start_date', 'payment_frequency',
            'free_rent_from', 'free_rent_to', 'free_rent_applies_to_property_fee',
            'contract_type',
            'escalation_term', 'escalation_start_year',
        }
        next_bill_trigger_keys = {
            'lease_start_date', 'payment_frequency',
            'free_rent_from', 'free_rent_to', 'free_rent_applies_to_property_fee',
            'contract_type',
        }
        if billing_trigger_keys & set(vals):
            for rec in self:
                updates = {}
                if not rec.first_rent_generated and rec.lease_start_date:
                    if next_bill_trigger_keys & set(vals):
                        if 'next_bill_date' not in vals:
                            updates['next_bill_date'] = rec._get_initial_next_bill_date()
                if not rec.escalation_term_generated:
                    if {'lease_start_date', 'escalation_term', 'escalation_start_year'} & set(vals):
                        if 'escalation_term_end_date' not in vals:
                            updates['escalation_term_end_date'] = rec._get_first_escalation_date()
                if updates:
                    super(MallLeasingContract, rec).write(updates)

        tracked_fields = [
            'state', 'rent_amount', 'deposit', 'water_fee', 'electric_fee',
            'property_fee', 'garbage_fee', 'payment_frequency', 'payment_day',
            'lease_start_date', 'lease_end_date',
        ]
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