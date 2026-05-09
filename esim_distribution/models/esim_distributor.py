# -*- coding: utf-8 -*-
import secrets

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


DISTRIBUTOR_STATE_SELECTION = [
    ('draft', '草稿'),
    ('pending', '待审核'),
    ('approved', '已通过'),
    ('rejected', '已拒绝'),
    ('suspended', '已停用'),
]


class EsimDistributor(models.Model):
    _name = 'esim.distributor'
    _description = 'eSIM 分销商'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    name = fields.Char(
        string="编号", required=True, readonly=True,
        default=lambda self: _('New'), copy=False,
    )
    partner_id = fields.Many2one(
        'res.partner', string="分销商", required=True,
        ondelete='restrict', index=True, tracking=True,
    )
    state = fields.Selection(
        DISTRIBUTOR_STATE_SELECTION, string="状态",
        default='draft', required=True, tracking=True,
    )
    tier_id = fields.Many2one(
        'esim.distributor.tier', string="当前等级",
        domain=[('active', '=', True)], tracking=True,
    )
    referral_code = fields.Char(
        string="推广码", required=True, readonly=True,
        copy=False, index=True,
    )
    referral_url = fields.Char(
        string="推广链接", compute='_compute_referral_url',
    )
    apply_date = fields.Datetime(string="申请时间", readonly=True)
    apply_reason = fields.Text(string="申请说明")
    approve_date = fields.Datetime(string="审核时间", readonly=True)
    approver_id = fields.Many2one(
        'res.users', string="审核人", readonly=True,
    )
    reject_reason = fields.Text(string="拒绝原因")
    commission_ids = fields.One2many(
        'esim.commission', 'distributor_id', string="佣金记录",
    )
    referred_partner_ids = fields.One2many(
        'res.partner', 'referrer_distributor_id', string="推荐客户",
    )
    commission_count = fields.Integer(
        string="佣金记录数", compute='_compute_commission_count',
    )
    referred_partner_count = fields.Integer(
        string="推荐客户数", compute='_compute_referred_partner_count',
    )
    total_sales_amount = fields.Float(
        string="累计销售额", digits=(12, 2),
        compute='_compute_distribution_amounts', store=True,
    )
    total_orders_count = fields.Integer(
        string="有效订单数", compute='_compute_distribution_amounts', store=True,
    )
    pending_commission_amount = fields.Float(
        string="冻结佣金", digits=(12, 2),
        compute='_compute_distribution_amounts', store=True,
    )
    settled_commission_amount = fields.Float(
        string="已结算佣金", digits=(12, 2),
        compute='_compute_distribution_amounts', store=True,
    )
    total_commission_amount = fields.Float(
        string="累计佣金", digits=(12, 2),
        compute='_compute_distribution_amounts', store=True,
    )

    _sql_constraints = [
        ('partner_uniq', 'UNIQUE(partner_id)', '每个客户只能拥有一个分销商档案。'),
        ('referral_code_uniq', 'UNIQUE(referral_code)', '推广码不能重复。'),
    ]

    @api.model_create_multi
    def create(self, vals_list: list[dict]) -> 'EsimDistributor':
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('esim.distributor') or _('New')
            if not vals.get('referral_code'):
                vals['referral_code'] = self._generate_referral_code()
            if vals.get('state') == 'pending' and not vals.get('apply_date'):
                vals['apply_date'] = fields.Datetime.now()
        return super().create(vals_list)

    @api.constrains('partner_id')
    def _check_partner_not_public(self) -> None:
        public_partner = self.env.ref('base.public_partner', raise_if_not_found=False)
        for distributor in self:
            if public_partner and distributor.partner_id == public_partner:
                raise ValidationError(_("公共访客不能申请成为分销商。"))

    def _compute_referral_url(self) -> None:
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        for distributor in self:
            distributor.referral_url = (
                f"{base_url}/distribution/r/{distributor.referral_code}"
                if distributor.referral_code else ''
            )

    @api.depends('commission_ids')
    def _compute_commission_count(self) -> None:
        for distributor in self:
            distributor.commission_count = len(distributor.commission_ids)

    @api.depends('referred_partner_ids')
    def _compute_referred_partner_count(self) -> None:
        for distributor in self:
            distributor.referred_partner_count = len(distributor.referred_partner_ids)

    @api.depends(
        'commission_ids.state',
        'commission_ids.order_amount',
        'commission_ids.commission_amount',
    )
    def _compute_distribution_amounts(self) -> None:
        for distributor in self:
            pending = distributor.commission_ids.filtered(lambda c: c.state == 'pending')
            settled = distributor.commission_ids.filtered(lambda c: c.state == 'settled')
            distributor.total_sales_amount = sum(settled.mapped('order_amount'))
            distributor.total_orders_count = len(settled)
            distributor.pending_commission_amount = sum(pending.mapped('commission_amount'))
            distributor.settled_commission_amount = sum(settled.mapped('commission_amount'))
            distributor.total_commission_amount = (
                distributor.pending_commission_amount + distributor.settled_commission_amount
            )

    def _generate_referral_code(self) -> str:
        """生成不可猜测的推广码，并在数据库层唯一约束之外先做快速冲突检查。"""
        for _attempt in range(10):
            code = secrets.token_urlsafe(8).replace('-', '').replace('_', '')[:10].upper()
            if not self.search_count([('referral_code', '=', code)]):
                return code
        raise UserError(_("推广码生成失败，请重试。"))

    def action_apply(self) -> None:
        for distributor in self:
            if distributor.state not in ('draft', 'rejected'):
                raise UserError(_("只有草稿或已拒绝状态可以重新提交申请。"))
            distributor.write({
                'state': 'pending',
                'apply_date': fields.Datetime.now(),
                'reject_reason': False,
            })

    def action_approve(self) -> None:
        self._check_manager_permission()
        default_tier = self.env['esim.distributor.tier']._get_default_tier()
        if not default_tier:
            raise UserError(_("请先配置默认分销等级。"))

        for distributor in self:
            if distributor.state != 'pending':
                raise UserError(_("只能审核待审核状态的分销商。"))
            distributor.write({
                'state': 'approved',
                'tier_id': distributor.tier_id.id or default_tier.id,
                'approve_date': fields.Datetime.now(),
                'approver_id': self.env.user.id,
                'reject_reason': False,
            })
            distributor.message_post(body=_("分销商申请已审核通过。"))
            distributor._send_state_mail('esim_distribution.mail_template_distributor_approved')

    def action_reject(self) -> None:
        self._check_manager_permission()
        for distributor in self:
            if distributor.state != 'pending':
                raise UserError(_("只能拒绝待审核状态的分销商。"))
            distributor.write({
                'state': 'rejected',
                'approve_date': fields.Datetime.now(),
                'approver_id': self.env.user.id,
                'reject_reason': distributor.reject_reason or _("管理员拒绝申请。"),
            })
            distributor.message_post(body=_("分销商申请已拒绝。"))
            distributor._send_state_mail('esim_distribution.mail_template_distributor_rejected')

    def action_suspend(self) -> None:
        self._check_manager_permission()
        self.filtered(lambda d: d.state == 'approved').write({'state': 'suspended'})

    def action_reactivate(self) -> None:
        self._check_manager_permission()
        self.filtered(lambda d: d.state == 'suspended').write({'state': 'approved'})

    def _check_manager_permission(self) -> None:
        if not self.env.user.has_group('esim_distribution.group_esim_distribution_manager'):
            raise UserError(_("只有分销管理员可以执行此操作。"))

    def _send_state_mail(self, template_xmlid: str) -> None:
        template = self.env.ref(template_xmlid, raise_if_not_found=False)
        if template:
            for distributor in self:
                template.sudo().send_mail(distributor.id, force_send=False)

    def _get_settled_metrics(self) -> tuple[float, int]:
        self.ensure_one()
        commissions = self.env['esim.commission'].search([
            ('distributor_id', '=', self.id),
            ('state', '=', 'settled'),
        ])
        return sum(commissions.mapped('order_amount')), len(commissions)

    def _evaluate_tier_upgrade(self) -> None:
        """佣金结算后按已结算业绩自动升级，历史佣金比例不回溯调整。"""
        Tier = self.env['esim.distributor.tier']
        for distributor in self.filtered(lambda d: d.state == 'approved'):
            sales_amount, order_count = distributor._get_settled_metrics()
            eligible_tier = Tier.search([
                ('active', '=', True),
                ('min_sales_amount', '<=', sales_amount),
                ('min_referral_count', '<=', order_count),
            ], order='sequence desc, id desc', limit=1)
            if (
                eligible_tier
                and (not distributor.tier_id or eligible_tier.sequence > distributor.tier_id.sequence)
            ):
                old_tier = distributor.tier_id
                distributor.tier_id = eligible_tier
                distributor.message_post(
                    body=_("分销等级已从 %(old)s 升级为 %(new)s。") % {
                        'old': old_tier.display_name if old_tier else _('未设置'),
                        'new': eligible_tier.display_name,
                    }
                )

    def action_view_commissions(self) -> dict:
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('佣金记录'),
            'res_model': 'esim.commission',
            'view_mode': 'list,form',
            'domain': [('distributor_id', '=', self.id)],
            'context': {'default_distributor_id': self.id},
        }

    def action_view_referred_partners(self) -> dict:
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('推荐客户'),
            'res_model': 'res.partner',
            'view_mode': 'list,form',
            'domain': [('referrer_distributor_id', '=', self.id)],
        }
