# -*- coding: utf-8 -*-
import logging
import uuid

from odoo import models, fields, api, _
from odoo.exceptions import UserError

from ..services.esim_api import EsimAccessAPIError

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
    can_cancel = fields.Boolean(
        string="可取消",
        compute='_compute_can_cancel',
    )
    profile_ids = fields.One2many('esim.profile', 'order_id', string="eSIM 档案")
    profile_count = fields.Integer(string="eSIM 数量", compute='_compute_profile_count')
    order_date = fields.Datetime(string="下单时间", readonly=True)
    period_num = fields.Integer(
        string="使用天数",
        help="每日套餐的天数（1-365），仅适用于按日计费的套餐",
    )
    note = fields.Text(string="备注")

    @api.depends('unit_price', 'quantity')
    def _compute_total_amount(self):
        for order in self:
            order.total_amount = order.unit_price * order.quantity

    def _compute_profile_count(self):
        for order in self:
            order.profile_count = len(order.profile_ids)

    @api.depends(
        'state',
        'api_order_no',
        'profile_ids.state',
        'profile_ids.esim_status',
        'profile_ids.smdp_status',
    )
    def _compute_can_cancel(self):
        for order in self:
            if order.state == 'draft':
                order.can_cancel = True
                continue

            if order.state in ('cancelled', 'failed'):
                order.can_cancel = False
                continue

            if not order.profile_ids:
                order.can_cancel = bool(order.api_order_no)
                continue

            pending_profiles = order.profile_ids.filtered(lambda profile: profile.state != 'cancelled')
            order.can_cancel = bool(pending_profiles) and all(
                profile.can_cancel for profile in pending_profiles
            )

    @api.model_create_multi
    def create(self, vals_list: list[dict]) -> 'EsimOrder':
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('esim.order') or _('New')
        return super().create(vals_list)

    def _build_package_info(self) -> dict:
        """构建单条 packageInfoList 元素"""
        self.ensure_one()
        info = {
            'packageCode': self.package_id.package_code,
            'count': self.quantity,
            'price': self.package_id.raw_price,
        }
        if self.period_num:
            info['periodNum'] = self.period_num
        return info

    def action_confirm(self) -> None:
        """确认订单：余额校验 → 扣款 → 调用 API 下单"""
        for order in self:
            if order.state != 'draft':
                raise UserError(_("只能确认草稿状态的订单"))

            # 余额校验与扣款
            partner = order.partner_id
            partner._esim_change_balance(
                log_type='consume',
                amount=order.total_amount,
                description=_("购买套餐: %s × %d") % (order.package_id.name, order.quantity),
                order_id=order.id,
            )

            api_client = self.env['esim.package']._get_api_client()
            transaction_id = uuid.uuid4().hex
            package_info = order._build_package_info()
            total_amount = package_info['price'] * package_info['count']

            try:
                result = api_client.place_order(
                    transaction_id=transaction_id,
                    package_info_list=[package_info],
                    amount=total_amount,
                )
            except EsimAccessAPIError as e:
                # API 下单失败，退回余额
                partner._esim_change_balance(
                    log_type='refund',
                    amount=order.total_amount,
                    description=_("下单失败自动退款: %s") % e.error_msg,
                    order_id=order.id,
                )
                order.write({'state': 'failed'})
                order.message_post(body=_("下单失败: [%s] %s") % (e.error_code, e.error_msg))
                raise UserError(_("下单失败: %s") % e.error_msg) from e

            order.write({
                'state': 'processing',
                'transaction_id': transaction_id,
                'api_order_no': result.get('orderNo', ''),
                'order_date': fields.Datetime.now(),
            })
            order.message_post(body=_("订单已提交至 eSIM Access，已扣款 $%.2f") % order.total_amount)

    def _has_balance_consumed(self) -> bool:
        """检查该订单是否已扣过余额"""
        self.ensure_one()
        return bool(self.env['esim.balance.log'].search_count([
            ('order_id', '=', self.id),
            ('type', '=', 'consume'),
        ]))

    def _has_balance_refunded(self) -> bool:
        """检查该订单是否已退过款"""
        self.ensure_one()
        return bool(self.env['esim.balance.log'].search_count([
            ('order_id', '=', self.id),
            ('type', '=', 'refund'),
        ]))

    def _sync_profiles_for_cancel(self):
        """取消前补齐订单对应的 eSIM 档案，避免只拿到 orderNo 却没有本地 profile。"""
        self.ensure_one()
        if self.profile_ids or not self.api_order_no:
            return self.profile_ids

        api_client = self.env['esim.package']._get_api_client()
        try:
            result = api_client.query_esim(order_no=self.api_order_no)
        except EsimAccessAPIError as e:
            raise UserError(_("查询订单 eSIM 失败: %s") % e.error_msg) from e

        self._process_order_result(result, mark_done=False)
        return self.profile_ids

    def _get_uncancelable_profiles(self):
        """返回当前订单中不满足取消条件的 eSIM。"""
        self.ensure_one()
        profiles = self._sync_profiles_for_cancel()
        return profiles.filtered(lambda profile: profile.state != 'cancelled' and not profile.can_cancel)

    def action_cancel(self) -> None:
        """按 eSIM 档案逐个取消订单，并在全部成功后退款。"""
        for order in self:
            if order.state not in ('draft', 'confirmed', 'processing', 'done'):
                raise UserError(_("当前状态不允许取消"))

            if order.state != 'draft':
                profiles = order._sync_profiles_for_cancel()
                if not profiles:
                    raise UserError(_("当前订单尚未生成可取消的 eSIM，请稍后刷新状态后再试。"))

                uncancelable_profiles = order._get_uncancelable_profiles()
                if uncancelable_profiles:
                    profile_lines = [
                        _("%s (状态: %s, esimStatus: %s, smdpStatus: %s)") % (
                            profile.iccid,
                            dict(profile._fields['state'].selection).get(profile.state, profile.state),
                            profile.esim_status or '-',
                            profile.smdp_status or '-',
                        )
                        for profile in uncancelable_profiles
                    ]
                    raise UserError(
                        _("以下 eSIM 当前不满足取消条件，请确认尚未安装且未使用：\n%s")
                        % '\n'.join(profile_lines)
                    )

                profiles.filtered(lambda profile: profile.state != 'cancelled').action_cancel_profile()

            # 退还已扣余额（仅当已扣款且未退款时）
            if order._has_balance_consumed() and not order._has_balance_refunded():
                order.partner_id._esim_change_balance(
                    log_type='refund',
                    amount=order.total_amount,
                    description=_("取消订单退款: %s") % order.name,
                    order_id=order.id,
                )

            order.write({'state': 'cancelled'})
            order.message_post(body=_("订单已取消，关联 eSIM 已取消并完成退款。"))

    def action_check_status(self) -> None:
        """手动检查订单状态"""
        for order in self:
            if not order.api_order_no:
                continue
            api_client = self.env['esim.package']._get_api_client()
            try:
                result = api_client.query_esim(order_no=order.api_order_no)
            except EsimAccessAPIError as e:
                order.message_post(body=_("查询状态失败: %s") % e.error_msg)
                continue

            order._process_order_result(result)

    def _process_order_result(self, result: dict, mark_done: bool = True) -> None:
        """处理 API 返回的查询结果，创建或更新 eSIM 档案。"""
        self.ensure_one()
        esim_list = result.get('esimList') or []
        if not esim_list:
            return

        profile_model = self.env['esim.profile']
        created_count = 0
        for esim_data in esim_list:
            iccid = esim_data.get('iccid', '')
            if not iccid:
                continue

            vals = profile_model._map_esim_data(esim_data)
            existing = profile_model.search([('iccid', '=', iccid)], limit=1)
            if existing:
                vals.pop('iccid', None)
                existing.write(vals)
            else:
                vals.update({
                    'iccid': iccid,
                    'order_id': self.id,
                    'partner_id': self.partner_id.id,
                    'package_id': self.package_id.id,
                })
                profile_model.create(vals)
                created_count += 1

        if mark_done:
            self.write({'state': 'done'})
            self.message_post(
                body=_("订单查询完成，共 %d 个 eSIM 档案（新建 %d 个）") % (len(esim_list), created_count),
            )

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
