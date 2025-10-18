# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from datetime import date
from dateutil.relativedelta import relativedelta

class MallLeasingContract(models.Model):
    _name = 'mall.leasing.contract'
    _description = '租赁合同（房东/租户）'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char('合同编号', required=True, tracking=True)
    contract_type = fields.Selection([
        ('landlord', '房东合同'),
        ('tenant', '租户合同'),
    ], string='合同类型', required=True, tracking=True)

    facade_id = fields.Many2one('mall.facade', string='关联门面', required=True, tracking=True)
    partner_id = fields.Many2one('res.partner', string='相对方', required=True, tracking=True)

    state = fields.Selection([
        ('draft', '草稿'),
        ('approved', '审批通过'),
        ('signed', '已签约'),
        ('active', '执行中'),
        ('renewed', '已续约'),
        ('terminated', '已终止'),
    ], string='状态', default='draft', tracking=True)

    currency_id = fields.Many2one('res.currency', string='币种', default=lambda self: self.env.company.currency_id.id)

    rent_amount = fields.Monetary('租金', currency_field='currency_id')
    deposit = fields.Monetary('押金', currency_field='currency_id')
    water_fee = fields.Monetary('水费', currency_field='currency_id')
    electric_fee = fields.Monetary('电费', currency_field='currency_id')
    property_fee = fields.Monetary('物业费', currency_field='currency_id')
    garbage_fee = fields.Monetary('垃圾费', currency_field='currency_id')

    payment_frequency = fields.Selection([
        ('monthly', '月付'),
        ('quarterly', '季付'),
        ('yearly', '年付'),
    ], string='支付方式')
    payment_day = fields.Integer('支付日(1-31)', default=1)

    bank_account = fields.Char('收款账户')

    lease_start_date = fields.Date('租赁开始日')
    lease_end_date = fields.Date('租赁结束日')

    free_rent_from = fields.Date('免租开始')
    free_rent_to = fields.Date('免租结束')

    escalation_rate = fields.Float('递增率(%)', help='例如每年递增5%，填写5')

    introducer_id = fields.Many2one('res.partner', string='介绍人/中介')
    commission_type = fields.Selection([
        ('fixed', '固定金额'),
        ('percent', '租金比例'),
    ], string='中介费类型')
    commission_amount = fields.Float('中介费金额/比例')
    commission_paid = fields.Boolean('中介费已支付')

    next_bill_date = fields.Date('下次出账日', compute='_compute_next_bill_date', store=True)

    version_ids = fields.One2many('mall.leasing.contract.version', 'contract_id', string='历史版本')

    _sql_constraints = [
        ('name_unique', 'unique(name)', '合同编号必须唯一。')
    ]

    @api.depends('lease_start_date', 'payment_frequency', 'payment_day')
    def _compute_next_bill_date(self):
        for rec in self:
            if not rec.lease_start_date or not rec.payment_frequency:
                rec.next_bill_date = False
                continue
            start = rec.lease_start_date
            # 设置首次账单为开始日期对应的支付日所在月
            first = date(start.year, start.month, min(rec.payment_day or 1, 28))
            if first < start:
                # 若支付日早于开始日，顺延一个周期
                delta = {'monthly': 1, 'quarterly': 3, 'yearly': 12}.get(rec.payment_frequency, 1)
                first = first + relativedelta(months=delta)
            rec.next_bill_date = first

    def _get_journal_and_account(self):
        company = self.env.company
        if self.contract_type == 'tenant':
            journal = self.env['account.journal'].search([('type', '=', 'sale'), ('company_id', '=', company.id)], limit=1)
            account = self.env['account.account'].search([('account_type', '=', 'income'), ('company_ids', 'in', company.id)], limit=1)
        else:
            journal = self.env['account.journal'].search([('type', '=', 'purchase'), ('company_id', '=', company.id)], limit=1)
            account = self.env['account.account'].search([('account_type', '=', 'expense'), ('company_ids', 'in', company.id)], limit=1)
        return journal, account

    def _charge_lines(self, account):
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
        if self.water_fee:
            lines.append(line(_('水费'), self.water_fee))
        if self.electric_fee:
            lines.append(line(_('电费'), self.electric_fee))
        if self.property_fee:
            lines.append(line(_('物业费'), self.property_fee))
        if self.garbage_fee:
            lines.append(line(_('垃圾费'), self.garbage_fee))
        return lines or [line(_('租赁费用'), 0.0)]

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

    def action_generate_move(self):
        """生成账单"""
        self.ensure_one()
        
        if not self.lease_start_date:
            raise UserError(_('请先设置租赁开始日期'))
        
        journal, account = self._get_journal_and_account()
        
        move_vals = {
            'move_type': 'out_invoice' if self.contract_type == 'tenant' else 'in_invoice',
            'partner_id': self.partner_id.id,
            'invoice_date': fields.Date.today(),
            'journal_id': journal.id,
            'invoice_line_ids': self._charge_lines(account),
        }
        
        move = self.env['account.move'].create(move_vals)
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': move.id,
            'view_mode': 'form',
            'target': 'current',
            }

    @api.model
    def cron_generate_periodic_bills(self):
        today = date.today()
        contracts = self.search([('state', '=', 'active'), ('next_bill_date', '<=', today)])
        for c in contracts:
            # 跳过免租期
            if c.free_rent_from and c.free_rent_to and c.free_rent_from <= today <= c.free_rent_to:
                months = {'monthly': 1, 'quarterly': 3, 'yearly': 12}.get(c.payment_frequency, 1)
                c.next_bill_date = c.next_bill_date + relativedelta(months=months)
                continue
            c.action_generate_move()

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