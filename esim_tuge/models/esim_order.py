# -*- coding: utf-8 -*-
import logging
import uuid

from odoo import models, fields, api, _
from odoo.exceptions import UserError

from ..services.tuge_api import TugeAPIError, parse_tuge_datetime

_logger = logging.getLogger(__name__)


class EsimOrder(models.Model):
    _inherit = 'esim.order'

    provider = fields.Selection(
        related='package_id.provider',
        string="供应商",
        store=True,
        index=True,
        readonly=True,
    )
    tuge_idempotency_key = fields.Char(
        string="途鸽幂等键",
        readonly=True,
        copy=False,
        index=True,
    )

    def _is_tuge_order(self) -> bool:
        self.ensure_one()
        return self.package_id.provider == 'tuge'

    def _ensure_tuge_idempotency_key(self) -> str:
        """生成或复用途鸽下单幂等键（重试时必须相同）。"""
        self.ensure_one()
        if not self.tuge_idempotency_key:
            self.tuge_idempotency_key = str(uuid.uuid4())
        return self.tuge_idempotency_key

    def _build_package_info(self) -> dict:
        """途鸽订单构建下单参数；Access 订单保持原逻辑。"""
        self.ensure_one()
        if not self._is_tuge_order():
            return super()._build_package_info()
        return {
            'productCode': self.package_id.package_code,
            'channelOrderNo': self.name,
            'idempotencyKey': self._ensure_tuge_idempotency_key(),
        }

    def _confirm_place_order(self) -> None:
        if self._is_tuge_order():
            self._tuge_place_order()
            return
        return super()._confirm_place_order()

    def _tuge_place_order(self) -> None:
        """调用途鸽创建订单 API，进入 processing 等待异步回调。"""
        self.ensure_one()
        package_model = self.env['esim.package']
        idempotency_key = self._ensure_tuge_idempotency_key()
        channel_order_no = self.name

        def do_create(client):
            return client.create_order(
                product_code=self.package_id.package_code,
                channel_order_no=channel_order_no,
                idempotency_key=idempotency_key,
            )

        try:
            result = package_model._tuge_api_call_with_token_retry(do_create)
        except TugeAPIError as e:
            self.write({'state': 'failed'})
            self.message_post(body=_("途鸽下单失败: [%s] %s") % (e.code, e.msg))
            raise UserError(_("途鸽下单失败: %s") % e.msg) from e

        order_no = result.get('orderNo', '')
        self.write({
            'state': 'processing',
            'transaction_id': idempotency_key,
            'api_order_no': order_no,
            'order_date': fields.Datetime.now(),
        })
        self.message_post(body=_("订单已提交至途鸽，等待开卡回调（订单号: %s）") % order_no)

    def _tuge_find_order_info_list(self) -> list[dict]:
        """从途鸽查询接口获取订单信息列表。"""
        self.ensure_one()
        if not self.api_order_no and not self.name:
            return []

        package_model = self.env['esim.package']

        def do_query(client):
            return client.query_orders(
                order_no=self.api_order_no or '',
                channel_order_no=self.name if not self.api_order_no else '',
            )

        try:
            result = package_model._tuge_api_call_with_token_retry(do_query)
        except TugeAPIError as e:
            _logger.warning("途鸽查单失败 order=%s: %s", self.name, e)
            return []

        order_list = result.get('list') or []
        if isinstance(order_list, list):
            return order_list
        return []

    def _tuge_apply_order_info(self, order_info: dict, mark_done: bool = True) -> None:
        """
        根据途鸽 OrderInfo（回调或查单）创建/更新 profile。
        order_info 可能嵌套在 cardInfo 中。
        """
        self.ensure_one()
        profile_model = self.env['esim.profile']

        iccid = order_info.get('iccid', '')
        card_info = order_info.get('cardInfo') or {}
        if not iccid and card_info:
            iccid = card_info.get('iccid', '')

        qr_code = order_info.get('qrCode', '')
        if not qr_code:
            return

        if not iccid:
            iccid = f"TUGE-PENDING-{order_info.get('orderNo', self.api_order_no)}"

        vals = profile_model._map_tuge_order_info(order_info)

        # 优先按订单关联查找（避免 pending 占位 ICCID 与真实 ICCID 重复建档）
        existing = profile_model.search([('order_id', '=', self.id)], limit=1)
        if not existing:
            existing = profile_model.search([('iccid', '=', iccid)], limit=1)
        if existing:
            write_vals = dict(vals)
            # 将占位 ICCID 更新为真实 ICCID
            if iccid and (
                not existing.iccid
                or existing.iccid.startswith('TUGE-PENDING-')
            ):
                write_vals['iccid'] = iccid
            else:
                write_vals.pop('iccid', None)
            existing.write(write_vals)
        else:
            profile_model.create({
                **vals,
                'iccid': iccid,
                'order_id': self.id,
                'partner_id': self.partner_id.id,
                'package_id': self.package_id.id,
            })

        if mark_done and self.state == 'processing':
            self.write({'state': 'done'})
            self.message_post(body=_("途鸽开卡完成，eSIM 档案已更新"))

    def _process_tuge_order_results(self, order_list: list[dict], mark_done: bool = True) -> None:
        """处理查单返回的多条订单记录（续订可能有多条）。"""
        self.ensure_one()
        for order_info in order_list:
            if order_info.get('qrCode') or (order_info.get('cardInfo') or {}).get('iccid'):
                self._tuge_apply_order_info(order_info, mark_done=mark_done)

    def action_check_status(self) -> None:
        tuge_orders = self.filtered(lambda o: o._is_tuge_order())
        other_orders = self - tuge_orders
        for order in tuge_orders:
            if not order.api_order_no:
                continue
            order_list = order._tuge_find_order_info_list()
            if order_list:
                order._process_tuge_order_results(order_list, mark_done=True)
            else:
                order.message_post(body=_("途鸽查单：尚未返回 QR/ICCID，请稍后重试"))
        if other_orders:
            return super(EsimOrder, other_orders).action_check_status()

    def _sync_profiles_for_cancel(self):
        self.ensure_one()
        if self._is_tuge_order():
            if self.profile_ids or not self.api_order_no:
                return self.profile_ids
            order_list = self._tuge_find_order_info_list()
            if order_list:
                self._process_tuge_order_results(order_list, mark_done=False)
            return self.profile_ids
        return super()._sync_profiles_for_cancel()

    @api.model
    def _cron_poll_tuge_processing_orders(self) -> None:
        """兜底：轮询 processing 状态的途鸽订单。"""
        orders = self.search([
            ('provider', '=', 'tuge'),
            ('state', '=', 'processing'),
            ('api_order_no', '!=', False),
        ])
        for order in orders:
            try:
                order.action_check_status()
            except Exception as e:
                _logger.exception("途鸽订单轮询异常 %s: %s", order.name, e)
