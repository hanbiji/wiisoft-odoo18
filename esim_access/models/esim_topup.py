# -*- coding: utf-8 -*-
import logging
import uuid

from odoo import models, fields, api, _
from odoo.exceptions import UserError

from ..services.esim_api import EsimAccessAPIError, VOLUME_DIVISOR

_logger = logging.getLogger(__name__)

TOPUP_STATE_SELECTION = [
    ('draft', '草稿'),
    ('done', '已完成'),
    ('failed', '失败'),
]


class EsimTopup(models.Model):
    _name = 'esim.topup'
    _description = 'eSIM 充值记录'
    _inherit = ['mail.thread']
    _order = 'create_date desc'

    name = fields.Char(
        string="充值编号", required=True, readonly=True,
        default=lambda self: _('New'), copy=False,
    )
    profile_id = fields.Many2one(
        'esim.profile', string="eSIM 档案", required=True,
        domain=[('state', 'in', ('ready', 'active'))],
        index=True,
    )
    partner_id = fields.Many2one(
        'res.partner', string="客户", required=True, index=True,
    )
    package_id = fields.Many2one(
        'esim.package', string="充值套餐", required=True,
        domain=[('package_type', '=', 'topup')],
    )
    amount = fields.Float(string="金额", digits=(12, 2), related='package_id.sale_price', store=True)
    transaction_id = fields.Char(string="交易 ID", readonly=True, copy=False)
    state = fields.Selection(
        TOPUP_STATE_SELECTION, string="状态", default='draft',
        tracking=True, required=True,
    )
    topup_date = fields.Datetime(string="充值时间", readonly=True)

    @api.model_create_multi
    def create(self, vals_list: list[dict]) -> 'EsimTopup':
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('esim.topup') or _('New')
        return super().create(vals_list)

    @api.onchange('profile_id')
    def _onchange_profile_id(self):
        """选择 eSIM 档案时自动填充客户"""
        if self.profile_id and self.profile_id.partner_id:
            self.partner_id = self.profile_id.partner_id

    def action_topup(self) -> None:
        """执行充值"""
        for topup in self:
            if topup.state != 'draft':
                raise UserError(_("只能对草稿状态的记录执行充值"))

            profile = topup.profile_id
            if profile.state not in ('ready', 'active'):
                raise UserError(_("只能为待激活或使用中的 eSIM 充值"))

            api_client = self.env['esim.package']._get_api_client()
            transaction_id = uuid.uuid4().hex
            raw_amount = topup.package_id.raw_price

            try:
                result = api_client.top_up(
                    iccid=profile.iccid,
                    package_code=topup.package_id.package_code,
                    transaction_id=transaction_id,
                    amount=raw_amount,
                )
            except EsimAccessAPIError as e:
                topup.write({'state': 'failed'})
                topup.message_post(body=_("充值失败: [%s] %s") % (e.error_code, e.error_msg))
                raise UserError(_("充值失败: %s") % e.error_msg) from e

            topup.write({
                'state': 'done',
                'transaction_id': transaction_id,
                'topup_date': fields.Datetime.now(),
            })

            # 更新 eSIM 档案的流量和有效期
            profile_vals = {}
            if result.get('totalVolume') is not None:
                profile_vals['total_volume'] = round(result['totalVolume'] / VOLUME_DIVISOR, 2)
            if result.get('expiredTime'):
                profile_vals['expired_time'] = result['expiredTime']
            if result.get('orderUsage') is not None:
                profile_vals['used_volume'] = round(result['orderUsage'] / VOLUME_DIVISOR, 2)
            if profile_vals:
                profile.write(profile_vals)

            topup.message_post(body=_("充值成功"))
