# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import pprint
from typing import Any
from urllib.parse import urlparse, parse_qsl, urlunparse

from werkzeug import urls

from odoo import _, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.payment_antom import const
from odoo.addons.payment_antom.controllers.main import AntomController

_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    antom_payment_id = fields.Char(
        string="Antom Payment ID", readonly=True,
        help="Antom 平台分配的唯一支付标识",
    )

    def _get_specific_rendering_values(
        self, processing_values: dict[str, Any]
    ) -> dict[str, Any]:
        """Override of `payment` to return Antom-specific rendering values.

        通过 Antom createPaymentSession 创建 Hosted Checkout 会话，
        获取托管收银台 URL。Antom 会在托管页面上动态展示商户开通的
        全部支付方式供买家选择，因此请求中不携带 paymentMethod——
        这是让收银台保持"通用入口"的官方推荐做法。

        Note: self.ensure_one() from `_get_processing_values`.
        """
        res = super()._get_specific_rendering_values(processing_values)
        if self.provider_code != 'antom':
            return res

        base_url = self.provider_id.get_base_url()
        return_url = urls.url_join(base_url, AntomController._return_url)
        notify_url = urls.url_join(base_url, AntomController._notify_url)

        # Antom 金额以最小货币单位表示（如分），字符串类型
        amount_in_minor = self._antom_convert_amount(self.amount, self.currency_id)

        payload = {
            'productCode': 'CASHIER_PAYMENT',
            'productScene': 'CHECKOUT_PAYMENT',
            'paymentRequestId': self.reference,
            'order': {
                'referenceOrderId': self.reference,
                'orderDescription': f'{self.company_id.name}: {self.reference}',
                'orderAmount': {
                    'currency': self.currency_id.name,
                    'value': amount_in_minor,
                },
            },
            'paymentAmount': {
                'currency': self.currency_id.name,
                'value': amount_in_minor,
            },
            'paymentRedirectUrl': f'{return_url}?reference={self.reference}',
            'paymentNotifyUrl': notify_url,
            'env': {
                'terminalType': 'WEB',
            },
        }

        _logger.info(
            "Sending Antom createPaymentSession request for transaction %s:\n%s",
            self.reference, pprint.pformat(payload),
        )

        response_data = self.provider_id._antom_make_request(
            const.API_PATH_CREATE_SESSION, payload
        )

        result = response_data.get('result', {})
        result_status = result.get('resultStatus')

        if result_status == 'F':
            raise ValidationError(
                "Antom: " + _(
                    "Payment creation failed: [%(code)s] %(msg)s",
                    code=result.get('resultCode', ''),
                    msg=result.get('resultMessage', ''),
                )
            )

        # 保存 Antom paymentId
        payment_id = response_data.get('paymentId', '')
        if payment_id:
            self.antom_payment_id = payment_id

        # 从响应中提取重定向 URL
        redirect_url = self._antom_extract_redirect_url(response_data)
        if not redirect_url:
            raise ValidationError(
                "Antom: " + _("No redirect URL received from Antom.")
            )

        # GET form 提交时浏览器会丢弃 action URL 上的查询参数，
        # 需要拆分为 base URL + hidden input 字段。
        parsed = urlparse(redirect_url)
        base_url = urlunparse(parsed._replace(query=''))
        url_params = parse_qsl(parsed.query, keep_blank_values=True)

        return {
            'api_url': base_url,
            'url_params': url_params,
        }

    def _get_tx_from_notification_data(
        self, provider_code: str, notification_data: dict[str, Any]
    ):
        """Override of `payment` to find the transaction based on Antom data.

        Antom 通知使用 paymentRequestId 标识交易，即 Odoo 的 reference。
        """
        tx = super()._get_tx_from_notification_data(provider_code, notification_data)
        if provider_code != 'antom' or len(tx) == 1:
            return tx

        reference = notification_data.get('paymentRequestId')
        if not reference:
            raise ValidationError(
                "Antom: " + _("Received notification with missing paymentRequestId.")
            )

        tx = self.search([
            ('reference', '=', reference),
            ('provider_code', '=', 'antom'),
        ])
        if not tx:
            raise ValidationError(
                "Antom: " + _(
                    "No transaction found matching reference %s.", reference
                )
            )
        return tx

    def _process_notification_data(self, notification_data: dict[str, Any]) -> None:
        """Override of `payment` to process the transaction based on Antom data.

        Note: self.ensure_one()
        """
        super()._process_notification_data(notification_data)
        if self.provider_code != 'antom':
            return

        # 更新 Antom 平台引用
        payment_id = notification_data.get('paymentId', '')
        if payment_id:
            self.provider_reference = payment_id
            self.antom_payment_id = payment_id

        # 校验金额和币种
        payment_amount = notification_data.get('paymentAmount', {})
        notif_amount_str = payment_amount.get('value', '')
        notif_currency = payment_amount.get('currency', '')

        if notif_amount_str and notif_currency:
            notif_amount = self._antom_parse_amount(notif_amount_str, self.currency_id)
            if self.currency_id.compare_amounts(notif_amount, self.amount) != 0:
                raise ValidationError(
                    "Antom: " + _(
                        "Amount mismatch: expected %(expected)s, got %(received)s.",
                        expected=self.amount, received=notif_amount,
                    )
                )
            if notif_currency != self.currency_id.name:
                raise ValidationError(
                    "Antom: " + _(
                        "Currency mismatch: expected %(expected)s, got %(received)s.",
                        expected=self.currency_id.name, received=notif_currency,
                    )
                )

        # 根据支付状态更新交易状态
        payment_status = notification_data.get('paymentStatus', '')
        result = notification_data.get('result', {})
        result_status = result.get('resultStatus', '')

        if payment_status in const.PAYMENT_STATUS_MAPPING['done']:
            self._set_done()
        elif payment_status in const.PAYMENT_STATUS_MAPPING['pending']:
            self._set_pending()
        elif payment_status in const.PAYMENT_STATUS_MAPPING['cancel']:
            self._set_canceled()
        elif payment_status in const.PAYMENT_STATUS_MAPPING['error']:
            error_msg = result.get('resultMessage', payment_status)
            self._set_error("Antom: " + error_msg)
        elif result_status == 'S':
            # 某些场景下只有 result.resultStatus，没有 paymentStatus
            self._set_done()
        elif result_status == 'F':
            error_msg = result.get('resultMessage', 'Payment failed')
            self._set_error("Antom: " + error_msg)
        else:
            _logger.warning(
                "Antom: received unknown payment status '%s' for transaction %s",
                payment_status, self.reference,
            )
            self._set_error(
                "Antom: " + _("Unknown payment status: %s", payment_status)
            )

    # === HELPER METHODS === #

    @staticmethod
    def _antom_convert_amount(amount: float, currency) -> str:
        """将 Odoo 金额转换为 Antom 最小货币单位的字符串。

        Antom 使用最小货币单位，如 USD 1.50 -> "150"，JPY 100 -> "100"。
        """
        # currency.decimal_places 表示小数位数，如 USD=2, JPY=0
        factor = 10 ** currency.decimal_places
        return str(round(amount * factor))

    @staticmethod
    def _antom_parse_amount(amount_str: str, currency) -> float:
        """将 Antom 最小货币单位金额字符串转换回 Odoo 浮点金额。"""
        factor = 10 ** currency.decimal_places
        return int(amount_str) / factor

    @staticmethod
    def _antom_extract_redirect_url(response_data: dict) -> str:
        """从 Antom createPaymentSession 响应中提取托管收银台 URL。

        Web 场景下 Antom 返回 normalUrl 指向托管收银台页面；
        部分历史 / 兼容响应可能使用 redirectActionForm.redirectUrl，
        这里按优先级兜底以兼容响应格式演进。
        """
        normal_url = response_data.get('normalUrl', '')
        if normal_url:
            return normal_url

        redirect_action = response_data.get('redirectActionForm', {})
        if redirect_action:
            return redirect_action.get('redirectUrl', '')

        return response_data.get('paymentRedirectUrl', '')
