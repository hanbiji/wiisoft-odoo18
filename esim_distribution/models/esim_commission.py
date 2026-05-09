# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import models, fields, api, _
from odoo.exceptions import UserError

COMMISSION_STATE_SELECTION = [
    ('pending', '冻结中'),
    ('settled', '已结算'),
    ('cancelled', '已取消'),
]


class EsimCommission(models.Model):
    _name = 'esim.commission'
    _description = 'eSIM 分销佣金'
    _inherit = ['mail.thread']
    _order = 'create_date desc'

    name = fields.Char(
        string="编号", required=True, readonly=True,
        default=lambda self: _('New'), copy=False,
    )
    distributor_id = fields.Many2one(
        'esim.distributor', string="分销商", required=True,
        ondelete='restrict', index=True, tracking=True,
    )
    order_id = fields.Many2one(
        'esim.order', string="来源订单", required=True,
        ondelete='restrict', index=True, readonly=True,
    )
    source_partner_id = fields.Many2one(
        'res.partner', string="购买客户", required=True,
        ondelete='restrict', index=True, readonly=True,
    )
    order_amount = fields.Float(
        string="订单金额", digits=(12, 2), required=True, readonly=True,
    )
    tier_id_snapshot = fields.Many2one(
        'esim.distributor.tier', string="等级快照",
        ondelete='restrict', readonly=True,
    )
    commission_rate = fields.Float(
        string="佣金比例 (%)", digits=(5, 2), required=True, readonly=True,
    )
    commission_amount = fields.Float(
        string="佣金金额", digits=(12, 2),
        compute='_compute_commission_amount', store=True,
    )
    state = fields.Selection(
        COMMISSION_STATE_SELECTION, string="状态",
        default='pending', required=True, tracking=True,
    )
    lock_release_date = fields.Datetime(
        string="解冻时间", required=True,
        default=lambda self: self._default_lock_release_date(),
        readonly=True, index=True,
    )
    settled_date = fields.Datetime(string="结算时间", readonly=True)
    balance_log_id = fields.Many2one(
        'esim.balance.log', string="余额变动记录",
        ondelete='set null', readonly=True,
    )
    cancel_reason = fields.Char(string="取消原因", readonly=True)

    _sql_constraints = [
        ('order_distributor_uniq',
         'UNIQUE(order_id, distributor_id)',
         '同一订单不能为同一分销商重复生成佣金。'),
    ]

    @api.model
    def _default_lock_release_date(self) -> fields.Datetime:
        cooldown_days = self._get_cooldown_days()
        return fields.Datetime.now() + timedelta(days=cooldown_days)

    @api.model
    def _get_cooldown_days(self) -> int:
        raw_value = self.env['ir.config_parameter'].sudo().get_param(
            'esim_distribution.cooldown_days', '7',
        )
        try:
            cooldown_days = int(raw_value)
        except (TypeError, ValueError):
            cooldown_days = 7
        return max(cooldown_days, 0)

    @api.model_create_multi
    def create(self, vals_list: list[dict]) -> 'EsimCommission':
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('esim.commission') or _('New')
            if not vals.get('lock_release_date'):
                vals['lock_release_date'] = self._default_lock_release_date()
        return super().create(vals_list)

    @api.depends('order_amount', 'commission_rate')
    def _compute_commission_amount(self) -> None:
        for commission in self:
            commission.commission_amount = round(
                commission.order_amount * commission.commission_rate / 100,
                2,
            )

    def action_cancel(self) -> None:
        self._cancel_pending(_("管理员取消。"))

    def _cancel_pending(self, reason: str) -> None:
        pending_commissions = self.filtered(lambda c: c.state == 'pending')
        pending_commissions.write({
            'state': 'cancelled',
            'cancel_reason': reason,
        })

    def action_settle(self) -> None:
        for commission in self:
            commission._settle_one()

    def _settle_one(self) -> None:
        """将冻结佣金入账到分销商 eSIM 余额，保持佣金记录与余额日志可追溯。"""
        self.ensure_one()
        if self.state != 'pending':
            return
        if self.order_id.state != 'done':
            self._cancel_pending(_("来源订单已不是完成状态。"))
            return
        if self.commission_amount <= 0:
            raise UserError(_("佣金金额必须大于 0。"))

        partner = self.distributor_id.partner_id.commercial_partner_id.sudo()
        log = partner._esim_change_balance(
            log_type='topup',
            amount=self.commission_amount,
            description=_("分销佣金: %s") % self.name,
            order_id=self.order_id.id,
        )
        self.write({
            'state': 'settled',
            'settled_date': fields.Datetime.now(),
            'balance_log_id': log.id,
        })
        self.distributor_id._evaluate_tier_upgrade()

    @api.model
    def _cron_settle_pending(self) -> None:
        now = fields.Datetime.now()
        commissions = self.search([
            ('state', '=', 'pending'),
            ('lock_release_date', '<=', now),
        ], order='lock_release_date, id')
        for commission in commissions:
            commission._settle_one()
