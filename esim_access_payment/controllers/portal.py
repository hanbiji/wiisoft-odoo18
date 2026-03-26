# -*- coding: utf-8 -*-
import logging

from werkzeug.exceptions import NotFound

from odoo import _, http
from odoo.exceptions import ValidationError
from odoo.http import request

from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment.controllers import portal as payment_portal

_logger = logging.getLogger(__name__)


class EsimPaymentPortal(payment_portal.PaymentPortal):
    """门户在线支付控制器：余额充值 + 套餐在线购买。"""

    # ==================================================================
    #  通用工具
    # ==================================================================

    @staticmethod
    def _get_package_currency(package):
        """根据套餐的 currency_code 查找 res.currency 记录。"""
        code = (package.currency_code or 'USD').upper()
        currency = request.env['res.currency'].sudo().search(
            [('name', '=', code)], limit=1,
        )
        if not currency:
            raise ValidationError(
                _("找不到套餐对应的货币: %s") % code,
            )
        return currency

    # ==================================================================
    #  通用：构建支付上下文
    # ==================================================================

    def _prepare_payment_rendering_context(
        self, amount: float, currency, partner_sudo, transaction_route: str,
        landing_route: str, reference_prefix: str, extra_values: dict | None = None,
    ) -> dict:
        """构建嵌入 payment.form 所需的完整渲染上下文。"""
        company = request.env.company

        availability_report = {}
        providers_sudo = request.env['payment.provider'].sudo()._get_compatible_providers(
            company.id, partner_sudo.id, amount,
            currency_id=currency.id, report=availability_report,
        )
        payment_methods_sudo = (
            request.env['payment.method'].sudo()._get_compatible_payment_methods(
                providers_sudo.ids, partner_sudo.id,
                currency_id=currency.id, report=availability_report,
            )
        )
        tokens_sudo = request.env['payment.token'].sudo()._get_available_tokens(
            providers_sudo.ids, partner_sudo.id,
        )
        access_token = payment_utils.generate_access_token(
            partner_sudo.id, amount, currency.id,
        )

        ctx = {
            'show_tokenize_input_mapping': self._compute_show_tokenize_input_mapping(providers_sudo),
            'reference_prefix': payment_utils.singularize_reference_prefix(prefix=reference_prefix),
            'amount': amount,
            'currency': currency,
            'partner_id': partner_sudo.id,
            'providers_sudo': providers_sudo,
            'payment_methods_sudo': payment_methods_sudo,
            'tokens_sudo': tokens_sudo,
            'availability_report': availability_report,
            'transaction_route': transaction_route,
            'landing_route': landing_route,
            'access_token': access_token,
            'res_company': company,
        }
        if extra_values:
            ctx.update(extra_values)
        return ctx

    # ==================================================================
    #  余额充值
    # ==================================================================

    @http.route('/my/esim/recharge', type='http', auth='user', website=True)
    def portal_recharge_options(self, **kw):
        """展示可用的充值档位列表。"""
        options = request.env['esim.recharge.option'].sudo().search(
            [('active', '=', True)], order='sequence, id',
        )
        partner = request.env.user.partner_id.commercial_partner_id
        return request.render('esim_access_payment.portal_recharge_options', {
            'options': options,
            'esim_balance': partner.sudo().esim_balance,
            'page_name': 'esim_recharge',
        })

    @http.route('/my/esim/recharge/<int:option_id>', type='http', auth='user', website=True)
    def portal_recharge_pay(self, option_id, **kw):
        """选定档位后展示支付表单。"""
        option = request.env['esim.recharge.option'].sudo().browse(option_id)
        if not option.exists() or not option.active:
            raise NotFound()

        partner_sudo = request.env.user.partner_id
        ctx = self._prepare_payment_rendering_context(
            amount=option.amount,
            currency=option.currency_id,
            partner_sudo=partner_sudo,
            transaction_route=f'/my/esim/recharge/transaction/{option.id}',
            landing_route='/my/esim/balance',
            reference_prefix='RCH',
            extra_values={
                'option': option,
                'esim_balance': partner_sudo.commercial_partner_id.sudo().esim_balance,
                'page_name': 'esim_recharge_pay',
            },
        )
        return request.render('esim_access_payment.portal_recharge_pay', ctx)

    @http.route(
        '/my/esim/recharge/transaction/<int:option_id>',
        type='jsonrpc', auth='user',
    )
    def portal_recharge_transaction(self, option_id, access_token, **kwargs):
        """创建充值单和支付交易，返回 processing values。"""
        option = request.env['esim.recharge.option'].sudo().browse(option_id)
        if not option.exists() or not option.active:
            raise ValidationError(_("充值档位无效。"))

        partner_sudo = request.env.user.partner_id
        amount = option.amount
        currency = option.currency_id

        if not payment_utils.check_access_token(
            access_token, partner_sudo.id, amount, currency.id,
        ):
            raise ValidationError(_("验证信息无效。"))

        recharge = request.env['esim.balance.recharge'].sudo().create({
            'partner_id': partner_sudo.commercial_partner_id.id,
            'amount': amount,
            'currency_id': currency.id,
            'option_id': option.id,
            'state': 'pending',
        })

        self._validate_transaction_kwargs(kwargs)
        kwargs.update({
            'amount': amount,
            'currency_id': currency.id,
            'partner_id': partner_sudo.id,
            'reference_prefix': recharge.name,
        })
        tx_sudo = self._create_transaction(
            custom_create_values={'esim_recharge_id': recharge.id},
            **kwargs,
        )
        recharge.sudo().write({'transaction_ids': [(4, tx_sudo.id)]})
        return tx_sudo._get_processing_values()

    # ==================================================================
    #  套餐在线支付
    # ==================================================================

    @http.route(
        '/my/esim/package/pay/<int:package_id>',
        type='http', auth='user', website=True,
    )
    def portal_package_pay(self, package_id, quantity=1, period_num=0, **kw):
        """展示套餐在线支付页面，嵌入 payment.form。"""
        package = request.env['esim.package'].sudo().browse(package_id)
        if not package.exists() or not package.is_published:
            raise NotFound()

        quantity = max(int(quantity), 1)
        period_num = max(int(period_num), 0)
        amount = package.sale_price * quantity
        currency = self._get_package_currency(package)
        partner_sudo = request.env.user.partner_id

        # quantity 和 period_num 编入 URL 路径，确保 JSON RPC 调用能正确携带
        tx_route = (
            f'/my/esim/package/transaction'
            f'/{package.id}/{quantity}/{period_num}'
        )
        ctx = self._prepare_payment_rendering_context(
            amount=amount,
            currency=currency,
            partner_sudo=partner_sudo,
            transaction_route=tx_route,
            landing_route='/my/esim/orders',
            reference_prefix='PKG',
            extra_values={
                'package': package,
                'quantity': quantity,
                'period_num': period_num,
                'total_amount': amount,
                'page_name': 'esim_package_pay',
            },
        )
        return request.render('esim_access_payment.portal_package_pay', ctx)

    @http.route(
        '/my/esim/package/transaction/<int:package_id>/<int:quantity>/<int:period_num>',
        type='jsonrpc', auth='user',
    )
    def portal_package_transaction(self, package_id, quantity, period_num,
                                   access_token, **kwargs):
        """创建 eSIM 订单和支付交易，返回 processing values。"""
        package = request.env['esim.package'].sudo().browse(package_id)
        if not package.exists() or not package.is_published:
            raise ValidationError(_("套餐无效。"))

        quantity = max(int(quantity), 1)
        period_num = max(int(period_num), 0)
        amount = package.sale_price * quantity
        currency = self._get_package_currency(package)
        partner_sudo = request.env.user.partner_id

        if not payment_utils.check_access_token(
            access_token, partner_sudo.id, amount, currency.id,
        ):
            raise ValidationError(_("验证信息无效。"))

        order_vals = {
            'partner_id': partner_sudo.commercial_partner_id.id,
            'package_id': package.id,
            'quantity': quantity,
            'is_paid_online': True,
        }
        if period_num:
            order_vals['period_num'] = period_num
        order = request.env['esim.order'].sudo().create(order_vals)

        self._validate_transaction_kwargs(kwargs)
        kwargs.update({
            'amount': amount,
            'currency_id': currency.id,
            'partner_id': partner_sudo.id,
            'reference_prefix': order.name,
        })
        tx_sudo = self._create_transaction(
            custom_create_values={'esim_order_id': order.id},
            **kwargs,
        )
        order.sudo().write({'payment_transaction_ids': [(4, tx_sudo.id)]})
        return tx_sudo._get_processing_values()
