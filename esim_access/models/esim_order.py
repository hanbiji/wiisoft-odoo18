# -*- coding: utf-8 -*-
import logging
import uuid

from odoo import models, fields, api, Command, _
from odoo.exceptions import UserError

from ..services.esim_api import EsimAccessAPIError, PRICE_DIVISOR

_logger = logging.getLogger(__name__)

ORDER_STATE_SELECTION = [
    ('draft', '草稿'),
    ('confirmed', '已确认'),
    ('processing', '处理中'),
    ('done', '已完成'),
    ('cancelled', '已取消'),
    ('failed', '失败'),
]


class EsimOrder(models.Model):
    _name = 'esim.order'
    _description = 'eSIM 订单'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    name = fields.Char(
        string="订单编号", required=True, readonly=True,
        default=lambda self: _('New'), copy=False,
    )
    partner_id = fields.Many2one(
        'res.partner', string="客户", required=True,
        tracking=True, index=True,
    )
    package_id = fields.Many2one(
        'esim.package', string="套餐", required=True,
        domain=[('package_type', '=', 'BASE')],
    )
    quantity = fields.Integer(string="数量", default=1, required=True)
    unit_price = fields.Float(string="单价", digits=(12, 2), related='package_id.sale_price', store=True)
    total_amount = fields.Float(string="总金额", digits=(12, 2), compute='_compute_total_amount', store=True)
    transaction_id = fields.Char(string="交易 ID", readonly=True, copy=False, index=True)
    api_order_no = fields.Char(string="API 订单号", readonly=True, copy=False, index=True)
    state = fields.Selection(
        ORDER_STATE_SELECTION, string="状态", default='draft',
        tracking=True, required=True,
    )
    profile_ids = fields.One2many('esim.profile', 'order_id', string="eSIM 档案")
    profile_count = fields.Integer(string="eSIM 数量", compute='_compute_profile_count')
    order_date = fields.Datetime(string="下单时间", readonly=True)
    note = fields.Text(string="备注")

    @api.depends('unit_price', 'quantity')
    def _compute_total_amount(self):
        for order in self:
            order.total_amount = order.unit_price * order.quantity

    def _compute_profile_count(self):
        for order in self:
            order.profile_count = len(order.profile_ids)

    @api.model_create_multi
    def create(self, vals_list: list[dict]) -> 'EsimOrder':
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('esim.order') or _('New')
        return super().create(vals_list)

    def action_confirm(self) -> None:
        """确认订单并调用 API 下单"""
        for order in self:
            if order.state != 'draft':
                raise UserError(_("只能确认草稿状态的订单"))

            api_client = self.env['esim.package']._get_api_client()
            transaction_id = uuid.uuid4().hex
            # API 需要万分之一单位的总金额
            raw_amount = order.package_id.raw_price * order.quantity

            try:
                result = api_client.place_order(
                    package_code=order.package_id.package_code,
                    count=order.quantity,
                    transaction_id=transaction_id,
                    amount=raw_amount,
                )
            except EsimAccessAPIError as e:
                order.write({'state': 'failed'})
                order.message_post(body=_("下单失败: [%s] %s") % (e.error_code, e.error_msg))
                raise UserError(_("下单失败: %s") % e.error_msg) from e

            order.write({
                'state': 'processing',
                'transaction_id': transaction_id,
                'api_order_no': result.get('orderNo', ''),
                'order_date': fields.Datetime.now(),
            })
            order.message_post(body=_("订单已提交至 eSIM Access，等待处理"))

    def action_cancel(self) -> None:
        """取消订单"""
        for order in self:
            if order.state not in ('draft', 'confirmed', 'processing'):
                raise UserError(_("当前状态不允许取消"))

            if order.api_order_no:
                api_client = self.env['esim.package']._get_api_client()
                try:
                    api_client.cancel_order(order.api_order_no)
                except EsimAccessAPIError as e:
                    raise UserError(_("取消失败: %s") % e.error_msg) from e

            order.write({'state': 'cancelled'})
            order.message_post(body=_("订单已取消"))

    def action_check_status(self) -> None:
        """手动检查订单状态"""
        for order in self:
            if not order.api_order_no and not order.transaction_id:
                continue
            api_client = self.env['esim.package']._get_api_client()
            try:
                result = api_client.query_order(
                    order_no=order.api_order_no,
                    transaction_id=order.transaction_id,
                )
            except EsimAccessAPIError as e:
                order.message_post(body=_("查询状态失败: %s") % e.error_msg)
                continue

            order._process_order_result(result)

    def _process_order_result(self, result: dict) -> None:
        """处理 API 返回的订单结果，创建 eSIM 档案"""
        esim_list = result.get('esimList') or result.get('orderList') or []
        if not esim_list:
            return

        profile_model = self.env['esim.profile']
        for esim_data in esim_list:
            iccid = esim_data.get('iccid', '')
            if not iccid:
                continue

            existing = profile_model.search([('iccid', '=', iccid)], limit=1)
            if existing:
                continue

            profile_model.create({
                'iccid': iccid,
                'order_id': self.id,
                'partner_id': self.partner_id.id,
                'package_id': self.package_id.id,
                'state': 'ready',
                'qr_code': esim_data.get('ac', ''),
                'smdp_status': esim_data.get('smdpStatus', ''),
                'expired_time': esim_data.get('expiredTime'),
                'total_volume': round(
                    esim_data.get('totalVolume', 0) / 1073741824, 2
                ) if esim_data.get('totalVolume') else 0,
            })

        if esim_list:
            self.write({'state': 'done'})
            self.message_post(body=_("订单已完成，共创建 %d 个 eSIM 档案") % len(esim_list))

    def action_view_profiles(self):
        """查看关联的 eSIM 档案"""
        return {
            'type': 'ir.actions.act_window',
            'name': _('eSIM 档案'),
            'res_model': 'esim.profile',
            'view_mode': 'list,form',
            'domain': [('order_id', '=', self.id)],
            'context': {'default_order_id': self.id, 'default_partner_id': self.partner_id.id},
        }
