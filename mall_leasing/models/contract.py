# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from datetime import date
from dateutil.relativedelta import relativedelta

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
    # 运营单位（人）
    operator_id = fields.Many2one('res.partner', 
        string='运营单位（人）', 
        required=True, 
        domain=[('mall_contact_type', '=', 'operator')])
    # 租赁单位（人）
    partner_id = fields.Many2one('res.partner', 
        string='租赁单位（人）', 
        required=True, 
        domain=[('mall_contact_type', '=', 'tenant')])
    # 物业单位（人）
    property_company_id = fields.Many2one('res.partner', 
        string='物业单位（人）', 
        required=True, 
        domain=[('mall_contact_type', '=', 'property_company')])
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

    rent_amount = fields.Monetary('每期租金', currency_field='currency_id')
    deposit = fields.Monetary('押金', currency_field='currency_id')
    deposit_generated = fields.Boolean('押金已生成', default=False, help='标记押金是否已经生成过账单')
    property_fee = fields.Monetary('每期物业费', currency_field='currency_id')
    service_fee = fields.Monetary('每期服务费', currency_field='currency_id')

    water_fee = fields.Monetary('水费', currency_field='currency_id')
    electric_fee = fields.Monetary('电费', currency_field='currency_id')
    garbage_fee = fields.Monetary('垃圾费', currency_field='currency_id')

    payment_frequency = fields.Selection([
        ('monthly', '月付'),
        ('quarterly', '季付'),
        ('yearly', '年付'),
    ], string='支付方式')
    payment_day = fields.Integer('支付日(1-31)', default=1)

    bank_account = fields.Char('收款账户')
    
    # 租赁期限（年）
    lease_term = fields.Integer('租赁期限（年）', default=1)
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

    contract_payment_ids = fields.One2many('mall.leasing.contract.payment', 'contract_id', string='付款记录')
    
    # 发票关联
    invoice_ids = fields.One2many('account.move', 'mall_contract_id', string='相关发票', 
                                  domain=[('move_type', 'in', ['out_invoice', 'in_invoice'])])
    invoice_count = fields.Integer('发票数量', compute='_compute_invoice_count')
    pending_amount = fields.Monetary('待付款金额', currency_field='currency_id', compute='_compute_pending_amount', store=True, readonly=True)

    _sql_constraints = [
        ('name_unique', 'unique(name)', '合同编号必须唯一。')
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) in [False, _('New')]:
                vals['name'] = self.env['ir.sequence'].next_by_code('mall.leasing.contract') or _('New')
        return super().create(vals_list)

    @api.depends('lease_start_date', 'payment_frequency', 'payment_day')
    def _compute_next_bill_date(self):
        """
        计算合同的下次出账日
        :return: None
        """
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
        :return: 包含journal和account的元组
        """
        company = self.env.company
        if self.contract_type in ['tenant', 'property']:
            journal = self.env['account.journal'].search([('type', '=', 'sale'), ('company_id', '=', company.id)], limit=1)
            account = self.env['account.account'].search([('account_type', '=', 'income'), ('company_ids', 'in', company.id)], limit=1)
        else:
            journal = self.env['account.journal'].search([('type', '=', 'purchase'), ('company_id', '=', company.id)], limit=1)
            account = self.env['account.account'].search([('account_type', '=', 'expense'), ('company_ids', 'in', company.id)], limit=1)
        return journal, account

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
        if self.water_fee:
            lines.append(line(_('水费'), self.water_fee))
        if self.electric_fee:
            lines.append(line(_('电费'), self.electric_fee))
        if self.property_fee:
            lines.append(line(_('物业费'), self.property_fee))
        if self.service_fee:
            lines.append(line(_('服务费'), self.service_fee))
        if self.garbage_fee:
            lines.append(line(_('垃圾费'), self.garbage_fee))
        return lines or [line(_('租赁费用'), 0.0)]

    def _create_single_move(self, fee_name, fee_amount, journal, account):
        """
        为单个费用类型创建会计凭证
        :param fee_name: 费用名称
        :param fee_amount: 费用金额
        :param journal: 会计账簿
        :param account: 费用对应的资产账户
        :return: 创建的会计凭证
        """
        if not fee_amount or fee_amount <= 0:
            return None
            
        move_vals = {
            'move_type': 'out_invoice' if self.contract_type in ['tenant', 'property'] else 'in_invoice',
            'partner_id': self.partner_id.id,
            'ref': f'合同# {self.name} - {fee_name}',
            'invoice_date': fields.Date.today(),
            'invoice_date_due': fields.Date.today() + relativedelta(days=15),
            'journal_id': journal.id,
            'invoice_line_ids': [(0, 0, {
                'name': fee_name,
                'quantity': 1.0,
                'price_unit': fee_amount,
                'account_id': account.id,
            })],
            'mall_contract_id': self.id,  # 建立与合同的关联
        }
        
        account_move = self.env['account.move'].create(move_vals)
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
        :return: 包含所有凭证ID的字典
        """
        self.ensure_one()
        
        if not self.lease_start_date:
            raise UserError(_('请先设置租赁开始日期'))
        
        journal, account = self._get_journal_and_account()
        
        # 定义费用类型和对应的金额
        fee_types = [
            (_('租金'), self.rent_amount),
            (_('水费'), self.water_fee),
            (_('电费'), self.electric_fee),
            (_('物业费'), self.property_fee),
            (_('服务费'), self.service_fee),
            (_('垃圾费'), self.garbage_fee),
        ]
        
        # 押金只在第一次生成账单时包含
        if not self.deposit_generated and self.deposit:
            fee_types.insert(1, (_('押金'), self.deposit))
        
        # 为每种费用类型生成单独的会计凭证
        created_moves = []
        deposit_move_created = False
        for fee_name, fee_amount in fee_types:
            if not fee_amount:
                continue
            move = self._create_single_move(fee_name, fee_amount, journal, account)
            if move:
                created_moves.append(move)
                # 如果生成了押金账单，标记为已生成
                if fee_name == _('押金'):
                    deposit_move_created = True
        
        # 更新押金生成状态
        if deposit_move_created:
            self.deposit_generated = True
        
        if not created_moves:
            raise UserError(_('没有需要生成凭证的费用项目'))
        
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
        action = self.env.ref('account.action_move_out_invoice_type').read()[0]
        if len(self.invoice_ids) > 1:
            action['domain'] = [('id', 'in', self.invoice_ids.ids)]
        elif len(self.invoice_ids) == 1:
            action['views'] = [(self.env.ref('account.view_move_form').id, 'form')]
            action['res_id'] = self.invoice_ids.ids[0]
        else:
            action = {'type': 'ir.actions.act_window_close'}
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

    @api.model
    def cron_generate_periodic_bills(self):
        """
        自动生成合同的周期性账单
        """
        today = date.today()
        contracts = self.search([('state', '=', 'active'), ('next_bill_date', '<=', today)])
        for c in contracts:
            # 跳过免租期
            if c.free_rent_from and c.free_rent_to and c.free_rent_from <= today <= c.free_rent_to:
                months = {'monthly': 1, 'quarterly': 3, 'yearly': 12}.get(c.payment_frequency, 1)
                c.next_bill_date = c.next_bill_date + relativedelta(months=months)
                continue
            c.action_generate_move()
            # 更新下一个账单日期
            months = {'monthly': 1, 'quarterly': 3, 'yearly': 12}.get(c.payment_frequency, 1)
            c.next_bill_date = c.next_bill_date + relativedelta(months=months)

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