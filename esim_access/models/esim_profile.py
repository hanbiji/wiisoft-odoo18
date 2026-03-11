# -*- coding: utf-8 -*-
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError

from ..services.esim_api import EsimAccessAPIError, VOLUME_DIVISOR

_logger = logging.getLogger(__name__)

PROFILE_STATE_SELECTION = [
    ('pending', '待处理'),
    ('ready', '待激活'),
    ('active', '使用中'),
    ('suspended', '已挂起'),
    ('revoked', '已吊销'),
    ('expired', '已过期'),
]


class EsimProfile(models.Model):
    _name = 'esim.profile'
    _description = 'eSIM 档案'
    _inherit = ['mail.thread']
    _order = 'create_date desc'
    _rec_name = 'iccid'

    iccid = fields.Char(string="ICCID", required=True, index=True, tracking=True)
    order_id = fields.Many2one('esim.order', string="来源订单", ondelete='set null', index=True)
    partner_id = fields.Many2one('res.partner', string="客户", required=True, tracking=True, index=True)
    package_id = fields.Many2one('esim.package', string="当前套餐")
    state = fields.Selection(
        PROFILE_STATE_SELECTION, string="状态", default='pending',
        tracking=True, required=True,
    )
    qr_code = fields.Char(string="激活码 / QR 链接")
    smdp_status = fields.Char(string="SM-DP+ 状态", tracking=True)
    total_volume = fields.Float(string="总流量 (GB)", digits=(10, 2))
    used_volume = fields.Float(string="已用流量 (GB)", digits=(10, 2))
    remaining_volume = fields.Float(
        string="剩余流量 (GB)", digits=(10, 2),
        compute='_compute_remaining_volume', store=True,
    )
    expired_time = fields.Datetime(string="过期时间")
    topup_ids = fields.One2many('esim.topup', 'profile_id', string="充值记录")
    topup_count = fields.Integer(compute='_compute_topup_count')

    _sql_constraints = [
        ('iccid_uniq', 'UNIQUE(iccid)', 'ICCID 不能重复'),
    ]

    def _compute_display_name(self):
        for rec in self:
            partner_name = rec.partner_id.name or ''
            rec.display_name = f"{partner_name} - {rec.iccid}" if rec.iccid else partner_name

    @api.depends('total_volume', 'used_volume')
    def _compute_remaining_volume(self):
        for rec in self:
            rec.remaining_volume = max(rec.total_volume - rec.used_volume, 0)

    def _compute_topup_count(self):
        for rec in self:
            rec.topup_count = len(rec.topup_ids)

    def action_refresh_status(self) -> None:
        """从 API 刷新 eSIM 状态"""
        api_client = self.env['esim.package']._get_api_client()
        for profile in self:
            if not profile.iccid:
                continue
            try:
                result = api_client.query_profile(iccid=profile.iccid)
            except EsimAccessAPIError as e:
                profile.message_post(body=_("状态刷新失败: %s") % e.error_msg)
                continue

            vals = {}
            if result.get('smdpStatus'):
                vals['smdp_status'] = result['smdpStatus']
            if result.get('totalVolume') is not None:
                vals['total_volume'] = round(result['totalVolume'] / VOLUME_DIVISOR, 2)
            if result.get('orderUsage') is not None:
                vals['used_volume'] = round(result['orderUsage'] / VOLUME_DIVISOR, 2)
            if result.get('expiredTime'):
                vals['expired_time'] = result['expiredTime']

            # 根据 SM-DP+ 状态推导 profile 状态
            smdp = result.get('smdpStatus', '')
            if smdp == 'RELEASED':
                vals['state'] = 'ready'
            elif smdp == 'DOWNLOADED':
                vals['state'] = 'active'
            elif smdp == 'INSTALLED':
                vals['state'] = 'active'
            elif smdp == 'ENABLED':
                vals['state'] = 'active'

            if vals:
                profile.write(vals)

    def action_suspend(self) -> None:
        """挂起 eSIM"""
        api_client = self.env['esim.package']._get_api_client()
        for profile in self:
            if profile.state not in ('ready', 'active'):
                raise UserError(_("只能挂起待激活或使用中的 eSIM"))
            try:
                api_client.suspend_esim(profile.iccid)
            except EsimAccessAPIError as e:
                raise UserError(_("挂起失败: %s") % e.error_msg) from e
            profile.write({'state': 'suspended'})
            profile.message_post(body=_("eSIM 已挂起"))

    def action_revoke(self) -> None:
        """吊销 eSIM（不可逆）"""
        api_client = self.env['esim.package']._get_api_client()
        for profile in self:
            if profile.state in ('revoked',):
                raise UserError(_("该 eSIM 已被吊销"))
            try:
                api_client.revoke_esim(profile.iccid)
            except EsimAccessAPIError as e:
                raise UserError(_("吊销失败: %s") % e.error_msg) from e
            profile.write({'state': 'revoked'})
            profile.message_post(body=_("eSIM 已被永久吊销"))

    @api.model
    def _cron_refresh_profiles(self) -> None:
        """定时任务：刷新活跃 eSIM 的状态"""
        active_profiles = self.search([('state', 'in', ('ready', 'active'))])
        active_profiles.action_refresh_status()

    def action_view_topups(self):
        """查看充值记录"""
        return {
            'type': 'ir.actions.act_window',
            'name': _('充值记录'),
            'res_model': 'esim.topup',
            'view_mode': 'list,form',
            'domain': [('profile_id', '=', self.id)],
            'context': {
                'default_profile_id': self.id,
                'default_partner_id': self.partner_id.id,
            },
        }
