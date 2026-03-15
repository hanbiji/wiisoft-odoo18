# -*- coding: utf-8 -*-
import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class EsimWebhookController(http.Controller):
    """接收 eSIM Access 平台的 Webhook 回调通知"""

    @http.route(
        '/esim/webhook',
        type='http',
        auth='public',
        csrf=False,
        save_session=False,
        methods=['POST'],
    )
    def handle_webhook(self):
        try:
            payload = request.httprequest.get_data(as_text=True) or '{}'
            data = json.loads(payload)
        except (TypeError, ValueError, json.JSONDecodeError):
            _logger.warning("eSIM Webhook: 无法解析请求体")
            return request.make_json_response({'status': 'error', 'message': 'Invalid JSON'}, status=400)

        notify_type = data.get('notifyType', '')
        iccid = data.get('iccid', '')
        order_no = data.get('orderNo', '')
        transaction_id = data.get('transactionId', '')

        _logger.info(
            "eSIM Webhook 收到通知: type=%s, iccid=%s, orderNo=%s",
            notify_type, iccid, order_no,
        )

        handler = {
            'ORDER_STATUS': self._handle_order_status,
            'ESIM_STATUS': self._handle_esim_status,
            'DATA_USAGE': self._handle_data_usage,
            'VALIDITY_USAGE': self._handle_validity_usage,
        }.get(notify_type)

        if not handler:
            _logger.warning("eSIM Webhook: 未知通知类型 %s", notify_type)
            return request.make_json_response(
                {'status': 'error', 'message': f'Unknown notifyType: {notify_type}'},
                status=400,
            )

        try:
            handler(data)
        except Exception as e:
            _logger.exception("eSIM Webhook 处理异常: %s", e)
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=500)

        return request.make_json_response({'status': 'ok'})

    def _handle_order_status(self, data: dict) -> None:
        """处理订单状态通知：eSIM 已准备就绪"""
        order_no = data.get('orderNo', '')
        transaction_id = data.get('transactionId', '')

        domain = []
        if order_no:
            domain = [('api_order_no', '=', order_no)]
        elif transaction_id:
            domain = [('transaction_id', '=', transaction_id)]
        else:
            return

        order = request.env['esim.order'].sudo().search(domain, limit=1)
        if not order:
            _logger.warning("eSIM Webhook ORDER_STATUS: 未找到订单 %s", order_no or transaction_id)
            return

        # 调用统一查询端点获取 eSIM 列表
        try:
            api_client = request.env['esim.package'].sudo()._get_api_client()
            result = api_client.query_esim(order_no=order.api_order_no)
            order._process_order_result(result)
        except Exception as e:
            _logger.error("eSIM Webhook: 查询订单详情失败: %s", e)
            order.message_post(body=f"Webhook 通知已收到，但查询订单详情失败: {e}")

    def _handle_esim_status(self, data: dict) -> None:
        """处理 eSIM 状态通知：eSIM 已被使用"""
        iccid = data.get('iccid', '')
        if not iccid:
            return

        profile = request.env['esim.profile'].sudo().search([('iccid', '=', iccid)], limit=1)
        if not profile:
            _logger.warning("eSIM Webhook ESIM_STATUS: 未找到档案 iccid=%s", iccid)
            return

        profile.write({'state': 'active'})
        profile.message_post(body="eSIM 已激活使用（Webhook 通知）")

    def _handle_data_usage(self, data: dict) -> None:
        """处理流量告警通知：剩余流量 ≤ 100MB"""
        iccid = data.get('iccid', '')
        if not iccid:
            return

        profile = request.env['esim.profile'].sudo().search([('iccid', '=', iccid)], limit=1)
        if not profile:
            return

        profile.message_post(body="⚠️ eSIM 流量即将耗尽（剩余 ≤ 100MB），请及时充值")
        # 刷新实际用量数据
        profile.action_refresh_status()

    def _handle_validity_usage(self, data: dict) -> None:
        """处理有效期告警通知：有效期仅剩 1 天"""
        iccid = data.get('iccid', '')
        if not iccid:
            return

        profile = request.env['esim.profile'].sudo().search([('iccid', '=', iccid)], limit=1)
        if not profile:
            return

        profile.message_post(body="⚠️ eSIM 有效期仅剩 1 天，请及时充值续费")
