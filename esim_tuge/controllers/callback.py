# -*- coding: utf-8 -*-
"""
途鸽 eSIM 异步回调接收。

路由：POST /esim/tuge/callback
验签失败返回非 0000；业务异常仍返回 0000（避免途鸽无限重试已处理的通知）。
"""
import json
import logging

from odoo import http
from odoo.http import request

from ..services.tuge_api import verify_sign

_logger = logging.getLogger(__name__)

# 途鸽回调事件类型
EVENT_CREATE = 1
EVENT_RENEW = 2
EVENT_PUSH = 3

SUCCESS_RESPONSE = {'code': '0000', 'msg': 'success'}


class TugeCallbackController(http.Controller):
    """接收途鸽 Webhook 开卡/续订/推送模式通知。"""

    @http.route(
        '/esim/tuge/callback',
        type='http',
        auth='public',
        csrf=False,
        save_session=False,
        methods=['POST'],
    )
    def handle_callback(self):
        try:
            payload = request.httprequest.get_data(as_text=True) or '{}'
            data = json.loads(payload)
        except (TypeError, ValueError, json.JSONDecodeError):
            _logger.warning("途鸽回调: 无法解析 JSON")
            return self._error_response('Invalid JSON', status=400)

        if not self._verify_callback_sign(data):
            _logger.warning("途鸽回调: 签名校验失败")
            return self._error_response('Invalid sign', status=403)

        try:
            self._dispatch_callback(
                data,
                top_code=str(data.get('code', '')),
                top_msg=str(data.get('msg', '')),
            )
        except Exception as e:
            # 业务异常仍返回成功，避免途鸽 2 小时内每 5s 重试
            _logger.exception("途鸽回调业务处理异常（已 ACK）: %s", e)

        return request.make_json_response(SUCCESS_RESPONSE)

    def _get_callback_secret(self) -> str:
        ICP = request.env['ir.config_parameter'].sudo()
        secret = ICP.get_param('tuge.callback_secret', '')
        if not secret:
            secret = ICP.get_param('tuge.secret', '')
        return secret

    def _verify_callback_sign(self, data: dict) -> bool:
        secret = self._get_callback_secret()
        if not secret:
            _logger.error("途鸽回调: 未配置 tuge.callback_secret，拒绝请求")
            return False
        return verify_sign(data, secret)

    def _dispatch_callback(self, data: dict, top_code: str = '', top_msg: str = '') -> None:
        """按 eventType 分发回调。"""
        inner = data.get('data') or {}
        event_type = inner.get('eventType')
        if event_type is None:
            _logger.warning("途鸽回调: 缺少 eventType")
            return

        _logger.info("途鸽回调 eventType=%s code=%s", event_type, top_code)

        if event_type in (EVENT_CREATE, EVENT_PUSH):
            order_info = inner.get('orderInfo') or {}
            if isinstance(order_info, dict):
                self._handle_order_callback(
                    inner, order_info, top_code=top_code, top_msg=top_msg,
                )
            else:
                _logger.warning("途鸽回调: orderInfo 格式异常 eventType=%s", event_type)
        elif event_type == EVENT_RENEW:
            order_info = inner.get('orderInfo')
            if isinstance(order_info, list):
                for item in order_info:
                    if isinstance(item, dict):
                        self._handle_order_callback(
                            inner, item, top_code=top_code, top_msg=top_msg,
                        )
            elif isinstance(order_info, dict):
                self._handle_order_callback(
                    inner, order_info, top_code=top_code, top_msg=top_msg,
                )
        else:
            _logger.warning("途鸽回调: 未知 eventType=%s", event_type)

    def _handle_order_callback(
        self,
        inner: dict,
        order_info: dict,
        top_code: str = '',
        top_msg: str = '',
    ) -> None:
        """处理开卡/续订通知，幂等更新订单与 profile。"""
        order_no = order_info.get('orderNo', '')
        channel_order_no = order_info.get('channelOrderNo', '')
        idempotency_key = inner.get('idempotencyKey', '')

        Order = request.env['esim.order'].sudo()
        order = Order.browse()
        if order_no:
            order = Order.search([('api_order_no', '=', order_no)], limit=1)
        if not order and channel_order_no:
            order = Order.search([('name', '=', channel_order_no)], limit=1)
        if not order and idempotency_key:
            order = Order.search([('tuge_idempotency_key', '=', idempotency_key)], limit=1)

        if not order:
            _logger.warning(
                "途鸽回调: 未找到订单 orderNo=%s channelOrderNo=%s",
                order_no, channel_order_no,
            )
            return

        # 幂等：已完成且已有 profile 则跳过
        if order.state == 'done' and order.profile_ids:
            _logger.info("途鸽回调: 订单 %s 已处理，跳过", order.name)
            return

        order.message_post(
            body="收到途鸽开卡回调 (eventType=%s, orderNo=%s, code=%s)" % (
                inner.get('eventType'), order_no or order.api_order_no, top_code,
            ),
        )

        if top_code and top_code != '0000':
            order.write({'state': 'failed'})
            order.message_post(body="途鸽开卡失败 [%s]: %s" % (top_code, top_msg or top_code))
            return

        if not order_info.get('qrCode'):
            _logger.info("途鸽回调: 订单 %s 尚无 qrCode", order.name)
            return

        order._tuge_apply_order_info(order_info, mark_done=True)

    def _error_response(self, message: str, status: int = 400):
        return request.make_json_response(
            {'code': '9999', 'msg': message},
            status=status,
        )
