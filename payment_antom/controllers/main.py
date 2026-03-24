# Part of Odoo. See LICENSE file for full copyright and licensing details.

import json
import logging
import pprint

from werkzeug.exceptions import Forbidden

from odoo import _, http
from odoo.exceptions import ValidationError
from odoo.http import request

from odoo.addons.payment_antom import const
from odoo.addons.payment_antom import utils as antom_utils

_logger = logging.getLogger(__name__)


class AntomController(http.Controller):
    _return_url = '/payment/antom/return'
    _notify_url = '/payment/antom/notify'

    @http.route(_return_url, type='http', auth='public', methods=['GET'])
    def antom_return(self, **data):
        """处理买家支付后的同步重定向。

        买家完成支付后 Antom 将其重定向回此 URL。
        真正的支付结果依赖异步通知，这里仅做状态查询兜底后跳转状态页。
        """
        reference = data.get('reference')
        if reference:
            tx_sudo = request.env['payment.transaction'].sudo().search([
                ('reference', '=', reference),
                ('provider_code', '=', 'antom'),
            ], limit=1)
            if tx_sudo and tx_sudo.state == 'draft' and tx_sudo.antom_payment_id:
                # 交易仍为草稿状态，主动查询 Antom 获取最新状态
                self._inquiry_payment_status(tx_sudo)

        return request.redirect('/payment/status')

    @http.route(
        _notify_url, type='http', auth='public', methods=['POST'], csrf=False,
    )
    def antom_notify(self):
        """处理 Antom 异步支付结果通知。

        Antom 在支付到达最终状态后向 paymentNotifyUrl 发送 POST 通知。
        我们需要：
        1. 验证通知签名
        2. 处理通知数据更新交易状态
        3. 返回固定格式的 SUCCESS 响应
        """
        raw_body = request.httprequest.get_data(as_text=True)
        notification_data = json.loads(raw_body)

        _logger.info(
            "Notification received from Antom:\n%s", pprint.pformat(notification_data)
        )

        try:
            # 验证通知签名
            self._verify_notification_signature(raw_body)

            # 查找并处理交易
            tx_sudo = request.env['payment.transaction'].sudo()\
                ._get_tx_from_notification_data('antom', notification_data)
            tx_sudo._handle_notification_data('antom', notification_data)

        except ValidationError:
            _logger.exception(
                "Unable to handle Antom notification; acknowledging to avoid retries."
            )

        # 返回 Antom 要求的固定 SUCCESS 响应格式
        response_body = {
            'result': {
                'resultCode': 'SUCCESS',
                'resultStatus': 'S',
                'resultMessage': 'success',
            }
        }
        return request.make_json_response(response_body)

    @staticmethod
    def _verify_notification_signature(raw_body: str):
        """验证 Antom 异步通知的 RSA 签名。

        从请求头中获取 client-id、request-time、signature，
        使用 Antom 公钥验证签名完整性。

        :raises Forbidden: 签名验证失败
        """
        headers = request.httprequest.headers
        client_id = headers.get('client-id', '')
        request_time = headers.get('request-time', '')
        signature_header = headers.get('signature', '')

        if not all((client_id, request_time, signature_header)):
            _logger.warning(
                "Antom notification missing required headers: "
                "client-id=%s, request-time=%s, signature=%s",
                bool(client_id), bool(request_time), bool(signature_header),
            )
            raise Forbidden()

        sig_parts = antom_utils.parse_signature_header(signature_header)
        sig_value = sig_parts.get('signature', '')
        if not sig_value:
            _logger.warning("Antom notification signature header has no signature value.")
            raise Forbidden()

        # 通知的 request URI 就是我们的 notify URL 路径
        request_uri = request.httprequest.path

        # 查找对应的 provider 获取公钥
        provider_sudo = request.env['payment.provider'].sudo().search([
            ('code', '=', 'antom'),
            ('antom_client_id', '=', client_id),
            ('state', 'in', ('enabled', 'test')),
        ], limit=1)

        if not provider_sudo or not provider_sudo.antom_public_key:
            _logger.warning(
                "No active Antom provider found for client_id: %s", client_id
            )
            raise Forbidden()

        public_key_pem = antom_utils.build_antom_public_key_pem(
            provider_sudo.antom_public_key
        )
        if not antom_utils.verify_signature(
            request_uri, client_id, request_time, raw_body, sig_value, public_key_pem
        ):
            _logger.warning("Antom notification signature verification failed.")
            raise Forbidden()

    @staticmethod
    def _inquiry_payment_status(tx_sudo):
        """通过 inquiryPayment API 查询支付最终状态。

        用于同步返回时交易尚未收到异步通知的兜底场景。
        """
        try:
            payload = {'paymentRequestId': tx_sudo.reference}
            if tx_sudo.antom_payment_id:
                payload['paymentId'] = tx_sudo.antom_payment_id

            response_data = tx_sudo.provider_id._antom_make_request(
                const.API_PATH_INQUIRY, payload
            )

            _logger.info(
                "Antom inquiryPayment response for %s:\n%s",
                tx_sudo.reference, pprint.pformat(response_data),
            )

            result = response_data.get('result', {})
            if result.get('resultStatus') == 'S':
                # 将查询结果作为通知数据处理
                notification_data = {
                    'paymentRequestId': response_data.get('paymentRequestId', ''),
                    'paymentId': response_data.get('paymentId', ''),
                    'paymentStatus': response_data.get('paymentStatus', ''),
                    'paymentAmount': response_data.get('paymentAmount', {}),
                    'result': result,
                }
                tx_sudo._handle_notification_data('antom', notification_data)

        except Exception:
            _logger.exception(
                "Failed to inquiry payment status for transaction %s",
                tx_sudo.reference,
            )
