# Part of Odoo. See LICENSE file for full copyright and licensing details.

import json
import logging
import pprint
import time
from typing import Any

import requests

from odoo import _, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.payment_antom import const
from odoo.addons.payment_antom import utils as antom_utils

_logger = logging.getLogger(__name__)


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    code = fields.Selection(
        selection_add=[('antom', "Antom")], ondelete={'antom': 'set default'}
    )
    antom_client_id = fields.Char(
        string="Antom Client ID",
        help="在 Antom Dashboard > Developers > Quick Start 获取",
        required_if_provider='antom',
    )
    antom_merchant_private_key = fields.Text(
        string="Merchant Private Key",
        help="商户 RSA 私钥（PEM 格式或纯 Base64），用于对请求签名",
        required_if_provider='antom',
        groups='base.group_system',
    )
    antom_public_key = fields.Text(
        string="Antom Public Key",
        help="Antom 平台 RSA 公钥（PEM 格式或纯 Base64），用于验证响应和通知签名",
        required_if_provider='antom',
        groups='base.group_system',
    )
    antom_gateway_region = fields.Selection(
        string="Gateway Region",
        help="选择最近的 Antom API 网关区域以获得最佳访问速度",
        selection=[
            ('asia', "Asia (Singapore)"),
            ('na_us', "North America (US Merchants)"),
            ('na_other', "North America (Non-US Merchants)"),
            ('europe', "Europe (Germany)"),
        ],
        default='asia',
        required_if_provider='antom',
    )

    # === BUSINESS METHODS === #

    def _antom_get_api_url(self) -> str:
        """根据区域和环境返回完整的 API 网关域名。"""
        self.ensure_one()
        region = self.antom_gateway_region or 'asia'
        env_key = 'production' if self.state == 'enabled' else 'sandbox'
        return const.GATEWAY_URLS[region][env_key]

    def _antom_get_endpoint_prefix(self) -> str:
        """正式环境使用 /ams/api，Sandbox 使用 /ams/sandbox/api。"""
        self.ensure_one()
        if self.state == 'enabled':
            return '/ams/api'
        return '/ams/sandbox/api'

    def _antom_make_request(
        self, api_path: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """向 Antom API 发送签名请求并验证响应签名。

        :param api_path: API 路径，如 /v1/payments/pay
        :param payload: 请求体字典
        :return: 响应体字典
        :raises ValidationError: 请求失败或签名验证失败
        """
        self.ensure_one()

        base_url = self._antom_get_api_url()
        prefix = self._antom_get_endpoint_prefix()
        full_uri = prefix + api_path
        url = base_url + full_uri

        body_str = json.dumps(payload, separators=(',', ':'))
        request_time = str(round(time.time() * 1000))

        private_key_pem = antom_utils.build_antom_private_key_pem(
            self.antom_merchant_private_key
        )
        signature = antom_utils.sign_request(
            full_uri, self.antom_client_id, request_time, body_str, private_key_pem
        )

        headers = {
            'Content-Type': 'application/json; charset=UTF-8',
            'Client-Id': self.antom_client_id,
            'Request-Time': request_time,
            'Signature': f'algorithm=RSA256, keyVersion=1, signature={signature}',
        }

        _logger.info(
            "Antom API request to %s:\n%s", url, pprint.pformat(payload)
        )

        try:
            response = requests.post(url, headers=headers, data=body_str, timeout=30)
            response.raise_for_status()
        except requests.exceptions.HTTPError:
            _logger.exception("Antom API HTTP error at %s", url)
            error_msg = ''
            try:
                error_msg = response.json().get('result', {}).get('resultMessage', '')
            except ValueError as exc:
                # HTTP 错误响应可能不是 JSON，记录后回落到通用提示。
                _logger.debug("Failed to parse Antom error response as JSON: %s", exc)
            raise ValidationError(
                "Antom: " + _("API request failed. Details: %s", error_msg)
            )
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            _logger.exception("Antom API connection error at %s", url)
            raise ValidationError(
                "Antom: " + _("Could not establish connection to the API.")
            )

        response_body = response.text
        response_data = response.json()

        _logger.info(
            "Antom API response from %s:\n%s", url, pprint.pformat(response_data)
        )

        # 验证响应签名
        if self.antom_public_key:
            resp_client_id = response.headers.get('Client-Id', '')
            resp_time = response.headers.get('Response-Time', '')
            resp_sig_header = response.headers.get('Signature', '')
            if resp_sig_header:
                sig_parts = antom_utils.parse_signature_header(resp_sig_header)
                sig_value = sig_parts.get('signature', '')
                public_key_pem = antom_utils.build_antom_public_key_pem(
                    self.antom_public_key
                )
                if not antom_utils.verify_signature(
                    full_uri, resp_client_id, resp_time, response_body,
                    sig_value, public_key_pem
                ):
                    _logger.warning("Antom response signature verification failed.")
                    raise ValidationError(
                        "Antom: " + _("Response signature verification failed.")
                    )

        return response_data

    # === BUSINESS METHODS - GETTERS === #

    def _get_supported_currencies(self):
        """Override of `payment` to return Antom supported currencies."""
        supported_currencies = super()._get_supported_currencies()
        if self.code == 'antom':
            supported_currencies = supported_currencies.filtered(
                lambda c: c.name in const.SUPPORTED_CURRENCIES
            )
        return supported_currencies

    def _get_default_payment_method_codes(self) -> set[str]:
        """Override of `payment` to return the default payment method codes."""
        default_codes = super()._get_default_payment_method_codes()
        if self.code != 'antom':
            return default_codes
        return const.DEFAULT_PAYMENT_METHOD_CODES
