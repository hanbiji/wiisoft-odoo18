# -*- coding: utf-8 -*-
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

BALANCE_LOG_TYPE_SELECTION = [
    ('topup', '充值'),
    ('consume', '消费'),
    ('refund', '退款'),
]


class EsimPartnerBalance(models.Model):
    """客户按币种隔离的 eSIM 钱包余额。

    与余额逻辑放在同一文件，避免单独文件未同步时模型未注册、
    导致 ir.model.access.csv 找不到 model_esim_partner_balance。
    """

    _name = 'esim.partner.balance'
    _description = 'eSIM 多币种余额'
    _order = 'currency_id'

    partner_id = fields.Many2one(
        'res.partner', string="客户", required=True,
        ondelete='cascade', index=True,
    )
    currency_id = fields.Many2one(
        'res.currency', string="币种", required=True, index=True,
    )
    amount = fields.Monetary(
        string="余额", currency_field='currency_id', default=0.0,
    )
    company_id = fields.Many2one(
        'res.company', string="公司",
        default=lambda self: self.env.company.id, index=True,
    )

    @api.constrains('partner_id', 'currency_id')
    def _check_partner_currency_uniq(self) -> None:
        for rec in self:
            duplicated = self.search_count([
                ('partner_id', '=', rec.partner_id.id),
                ('currency_id', '=', rec.currency_id.id),
                ('id', '!=', rec.id),
            ])
            if duplicated:
                raise ValidationError(_("同一客户同一币种只能有一条余额记录。"))

    @api.constrains('amount')
    def _check_amount_non_negative(self) -> None:
        for rec in self:
            if rec.amount < -1e-9:
                raise ValidationError(_("钱包余额不能为负数。"))


class ResPartner(models.Model):
    _inherit = 'res.partner'

    esim_balance = fields.Float(
        string="eSIM 余额(公司币种)", digits=(12, 2), default=0.0,
        help="公司本位币钱包余额镜像，便于后台概览；门户购物使用所选币种钱包。",
    )
    esim_balance_ids = fields.One2many(
        'esim.partner.balance', 'partner_id', string="多币种钱包",
    )
    esim_balance_log_ids = fields.One2many(
        'esim.balance.log', 'partner_id', string="余额变动记录",
    )
    esim_preferred_currency_id = fields.Many2one(
        'res.currency', string="eSIM 首选币种",
        help="门户购物默认币种，可在门户切换后自动记住。",
    )

    def _esim_sync_company_balance_mirror(self) -> None:
        """将公司本位币钱包金额同步到兼容字段 esim_balance。"""
        company_currency = self.env.company.currency_id
        for partner in self:
            partner.esim_balance = partner._esim_get_balance(company_currency)

    def _esim_get_balance(self, currency) -> float:
        """读取指定币种钱包余额；无钱包时返回 0。"""
        self.ensure_one()
        if not currency:
            return 0.0
        wallet = self.env['esim.partner.balance'].sudo().search([
            ('partner_id', '=', self.id),
            ('currency_id', '=', currency.id),
        ], limit=1)
        return wallet.amount if wallet else 0.0

    def _esim_get_or_create_wallet(self, currency):
        """获取或创建指定币种钱包。"""
        self.ensure_one()
        wallet = self.env['esim.partner.balance'].sudo().search([
            ('partner_id', '=', self.id),
            ('currency_id', '=', currency.id),
        ], limit=1)
        if not wallet:
            wallet = self.env['esim.partner.balance'].sudo().create({
                'partner_id': self.id,
                'currency_id': currency.id,
                'amount': 0.0,
            })
        return wallet

    def action_view_esim_balance_logs(self):
        """查看余额变动记录"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('余额变动记录'),
            'res_model': 'esim.balance.log',
            'view_mode': 'list,form',
            'domain': [('partner_id', '=', self.id)],
            'context': {'default_partner_id': self.id},
        }

    def _esim_change_balance(
        self,
        log_type: str,
        amount: float,
        description: str = '',
        order_id: int | None = None,
        currency=None,
    ) -> 'EsimBalanceLog':
        """
        统一余额变更入口，保证指定币种钱包与日志的原子一致性。
        - log_type: 'topup' / 'consume' / 'refund'
        - amount: 变动金额（正数），方向由 log_type 决定
        - currency: 钱包币种；缺省时使用公司本位币
        """
        self.ensure_one()
        if amount <= 0:
            raise UserError(_("变动金额必须大于 0"))

        currency = currency or self.env.company.currency_id
        if isinstance(currency, int):
            currency = self.env['res.currency'].browse(currency)

        wallet = self._esim_get_or_create_wallet(currency)
        balance_before = wallet.amount
        symbol = currency.symbol or currency.name

        if log_type == 'consume':
            if currency.compare_amounts(balance_before, amount) < 0:
                raise UserError(
                    _("余额不足：当前余额 %(symbol)s%(before).2f，需要 %(symbol)s%(need).2f") % {
                        'symbol': symbol,
                        'before': balance_before,
                        'need': amount,
                    }
                )
            balance_after = balance_before - amount
        elif log_type in ('topup', 'refund'):
            balance_after = balance_before + amount
        else:
            raise UserError(_("未知的余额变动类型: %s") % log_type)

        wallet.amount = balance_after
        self._esim_sync_company_balance_mirror()

        log = self.env['esim.balance.log'].create({
            'partner_id': self.id,
            'type': log_type,
            'amount': amount,
            'currency_id': currency.id,
            'balance_before': balance_before,
            'balance_after': balance_after,
            'description': description,
            'order_id': order_id,
            'operator_id': self.env.uid,
        })
        return log


class EsimBalanceLog(models.Model):
    _name = 'esim.balance.log'
    _description = 'eSIM 余额变动记录'
    _order = 'create_date desc'

    name = fields.Char(
        string="编号", required=True, readonly=True,
        default=lambda self: _('New'), copy=False,
    )
    partner_id = fields.Many2one(
        'res.partner', string="客户", required=True,
        ondelete='cascade', index=True,
    )
    type = fields.Selection(
        BALANCE_LOG_TYPE_SELECTION, string="类型",
        required=True, readonly=True,
    )
    amount = fields.Monetary(
        string="金额", currency_field='currency_id',
        required=True, readonly=True,
    )
    currency_id = fields.Many2one(
        'res.currency', string="币种", required=True, readonly=True,
        default=lambda self: self.env.company.currency_id,
    )
    balance_before = fields.Monetary(
        string="变动前余额", currency_field='currency_id', readonly=True,
    )
    balance_after = fields.Monetary(
        string="变动后余额", currency_field='currency_id', readonly=True,
    )
    description = fields.Char(string="说明", readonly=True)
    order_id = fields.Many2one(
        'esim.order', string="关联订单",
        ondelete='set null', readonly=True,
    )
    operator_id = fields.Many2one(
        'res.users', string="操作人",
        default=lambda self: self.env.uid, readonly=True,
    )

    @api.model_create_multi
    def create(self, vals_list: list[dict]) -> 'EsimBalanceLog':
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('esim.balance.log') or _('New')
            if not vals.get('currency_id'):
                vals['currency_id'] = self.env.company.currency_id.id
        return super().create(vals_list)

    @api.depends('name', 'type', 'amount', 'currency_id')
    def _compute_display_name(self):
        type_map = dict(BALANCE_LOG_TYPE_SELECTION)
        for rec in self:
            symbol = rec.currency_id.symbol or rec.currency_id.name or ''
            rec.display_name = (
                f"{rec.name} - {type_map.get(rec.type, '')} {symbol}{rec.amount:.2f}"
            )
