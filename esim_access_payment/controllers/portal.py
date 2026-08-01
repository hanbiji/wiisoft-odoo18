# -*- coding: utf-8 -*-
import logging

from werkzeug.exceptions import NotFound

from odoo import _, fields, http
from odoo.exceptions import ValidationError
from odoo.http import request

from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment.controllers import portal as payment_portal
from odoo.addons.esim_access.controllers.portal import EsimPortal

_logger = logging.getLogger(__name__)


class EsimPaymentPortal(payment_portal.PaymentPortal):
    """门户在线支付控制器：余额充值 + 套餐在线购买。"""

    # ==================================================================
    #  通用工具
    # ==================================================================

    def _get_shop_currency(self):
        """复用 eSIM 门户会话币种。"""
        return EsimPortal()._get_shop_currency()

    def _convert_amount(self, amount: float, from_currency, to_currency) -> float:
        """按公司汇率将金额换算到目标币种。"""
        if not from_currency or not to_currency or from_currency == to_currency:
            return amount
        return from_currency._convert(
            amount,
            to_currency,
            request.env.company,
            fields.Date.context_today(request.env.user),
        )

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
        """展示可用充值档位（金额按当前购物币种换算）。"""
        options = request.env['esim.recharge.option'].sudo().search(
            [('active', '=', True)], order='sequence, id',
        )
        partner = request.env.user.partner_id.commercial_partner_id
        shop_currency = self._get_shop_currency()
        display_options = []
        for opt in options:
            converted = self._convert_amount(opt.amount, opt.currency_id, shop_currency)
            display_options.append({
                'option': opt,
                'amount': converted,
            })
        return request.render('esim_access_payment.portal_recharge_options', {
            'options': options,
            'display_options': display_options,
            'shop_currency': shop_currency,
            'esim_currencies': request.env['esim.package']._get_active_shop_currencies(),
            'esim_balance': partner.sudo()._esim_get_balance(shop_currency),
            'page_name': 'esim_recharge',
        })

    @http.route('/my/esim/recharge/<int:option_id>', type='http', auth='user', website=True)
    def portal_recharge_pay(self, option_id, **kw):
        """选定档位后按当前购物币种展示支付表单。"""
        option = request.env['esim.recharge.option'].sudo().browse(option_id)
        if not option.exists() or not option.active:
            raise NotFound()

        partner_sudo = request.env.user.partner_id
        commercial = partner_sudo.commercial_partner_id
        shop_currency = self._get_shop_currency()
        amount = self._convert_amount(option.amount, option.currency_id, shop_currency)

        ctx = self._prepare_payment_rendering_context(
            amount=amount,
            currency=shop_currency,
            partner_sudo=partner_sudo,
            transaction_route=f'/my/esim/recharge/transaction/{option.id}',
            landing_route='/my/esim/balance',
            reference_prefix='RCH',
            extra_values={
                'option': option,
                'shop_currency': shop_currency,
                'esim_currencies': request.env['esim.package']._get_active_shop_currencies(),
                'pay_amount': amount,
                'esim_balance': commercial.sudo()._esim_get_balance(shop_currency),
                'page_name': 'esim_recharge_pay',
            },
        )
        return request.render('esim_access_payment.portal_recharge_pay', ctx)

    @http.route(
        '/my/esim/recharge/transaction/<int:option_id>',
        type='jsonrpc', auth='user',
    )
    def portal_recharge_transaction(self, option_id, access_token, **kwargs):
        """创建充值单和支付交易（按购物币种收款并入账）。"""
        option = request.env['esim.recharge.option'].sudo().browse(option_id)
        if not option.exists() or not option.active:
            raise ValidationError(_("充值档位无效。"))

        partner_sudo = request.env.user.partner_id
        shop_currency = self._get_shop_currency()
        amount = self._convert_amount(option.amount, option.currency_id, shop_currency)

        if not payment_utils.check_access_token(
            access_token, partner_sudo.id, amount, shop_currency.id,
        ):
            raise ValidationError(_("验证信息无效。"))

        recharge = request.env['esim.balance.recharge'].sudo().create({
            'partner_id': partner_sudo.commercial_partner_id.id,
            'amount': amount,
            'currency_id': shop_currency.id,
            'option_id': option.id,
            'state': 'pending',
        })

        self._validate_transaction_kwargs(kwargs)
        kwargs.update({
            'amount': amount,
            'currency_id': shop_currency.id,
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
        shop_currency = self._get_shop_currency()
        unit_price = package._get_sale_price(shop_currency)
        amount = unit_price * quantity
        partner_sudo = request.env.user.partner_id

        tx_route = (
            f'/my/esim/package/transaction'
            f'/{package.id}/{quantity}/{period_num}'
        )
        ctx = self._prepare_payment_rendering_context(
            amount=amount,
            currency=shop_currency,
            partner_sudo=partner_sudo,
            transaction_route=tx_route,
            landing_route='/my/esim/orders',
            reference_prefix='PKG',
            extra_values={
                'package': package,
                'quantity': quantity,
                'period_num': period_num,
                'unit_price': unit_price,
                'total_amount': amount,
                'shop_currency': shop_currency,
                'esim_currencies': request.env['esim.package']._get_active_shop_currencies(),
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
        """创建 eSIM 订单和支付交易，按购物币种收款。"""
        package = request.env['esim.package'].sudo().browse(package_id)
        if not package.exists() or not package.is_published:
            raise ValidationError(_("套餐无效。"))

        quantity = max(int(quantity), 1)
        period_num = max(int(period_num), 0)
        shop_currency = self._get_shop_currency()
        unit_price = package._get_sale_price(shop_currency)
        amount = unit_price * quantity
        partner_sudo = request.env.user.partner_id

        if not payment_utils.check_access_token(
            access_token, partner_sudo.id, amount, shop_currency.id,
        ):
            raise ValidationError(_("验证信息无效。"))

        order_vals = {
            'partner_id': partner_sudo.commercial_partner_id.id,
            'package_id': package.id,
            'quantity': quantity,
            'currency_id': shop_currency.id,
            'unit_price': unit_price,
            'is_paid_online': True,
        }
        if period_num:
            order_vals['period_num'] = period_num
        order = request.env['esim.order'].sudo().create(order_vals)

        self._validate_transaction_kwargs(kwargs)
        kwargs.update({
            'amount': amount,
            'currency_id': shop_currency.id,
            'partner_id': partner_sudo.id,
            'reference_prefix': order.name,
        })
        tx_sudo = self._create_transaction(
            custom_create_values={'esim_order_id': order.id},
            **kwargs,
        )
        order.sudo().write({'payment_transaction_ids': [(4, tx_sudo.id)]})
        return tx_sudo._get_processing_values()
