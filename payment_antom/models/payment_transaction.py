# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import pprint
from typing import Any

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

        调用 Antom pay API 创建支付订单，获取重定向 URL。

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
            'paymentMethod': {
                'paymentMethodType': self._antom_get_payment_method_type(),
            },
            'paymentRedirectUrl': f'{return_url}?reference={self.reference}',
            'paymentNotifyUrl': notify_url,
            'env': {
                'terminalType': 'WEB',
            },
        }

        _logger.info(
            "Sending Antom pay request for transaction %s:\n%s",
            self.reference, pprint.pformat(payload),
        )

        response_data = self.provider_id._antom_make_request(
            const.API_PATH_PAY, payload
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

        return {
            'api_url': redirect_url,
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

    def _antom_get_payment_method_type(self) -> str:
        """返回当前交易的 Antom paymentMethodType。

        Cashier Payment 模式下使用 CONNECT_WALLET 作为通用钱包类型，
        Antom 收银台会自动展示可用的支付方式供买家选择。
        """
        return 'CONNECT_WALLET'

    @staticmethod
    def _antom_extract_redirect_url(response_data: dict) -> str:
        """从 Antom pay API 响应中提取重定向 URL。

        响应可能包含 normalUrl、schemeUrl、applinkUrl 等，
        Web 场景优先使用 normalUrl。
        """
        # redirectActionForm 用于需要重定向的场景
        redirect_action = response_data.get('redirectActionForm', {})
        if redirect_action:
            return redirect_action.get('redirectUrl', '')

        # normalUrl 在某些版本的 API 响应中直接返回
        normal_url = response_data.get('normalUrl', '')
        if normal_url:
            return normal_url

        # paymentRedirectUrl 作为兜底
        return response_data.get('paymentRedirectUrl', '')
