# -*- coding: utf-8 -*-
import logging
import uuid

from odoo import http, fields, _
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager
from odoo.exceptions import AccessError, MissingError, UserError

_logger = logging.getLogger(__name__)

PACKAGES_PER_PAGE = 12
PROFILES_PER_PAGE = 10
TRANSACTIONS_PER_PAGE = 20


class EsimPortal(CustomerPortal):

    @staticmethod
    def _get_portal_partner():
        """门户统一使用商业伙伴作为客户主档，避免联系人与公司余额分裂。"""
        return request.env.user.partner_id.commercial_partner_id

    @staticmethod
    def _normalize_filter_value(value) -> str:
        """统一处理筛选参数，避免 None 和空白字符串干扰 domain。"""
        return (value or '').strip()

    @staticmethod
    def _get_package_duration_option(package) -> dict | None:
        """构建有效期筛选项。"""
        if not package.duration or not package.duration_unit:
            return None
        label_unit = '天' if package.duration_unit == 'DAY' else '月'
        return {
            'value': f"{package.duration}|{package.duration_unit}",
            'label': f"{package.duration} {label_unit}",
        }

    @staticmethod
    def _get_package_volume_option(package) -> dict | None:
        """构建流量筛选项。"""
        if package.volume in (None, False):
            return None
        return {
            'value': str(package.volume),
            'label': f"{package.volume:g} GB",
        }

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        partner = self._get_portal_partner()

        # 余额卡片展示的是实际金额，不属于 portal counter 机制，首页首屏始终提供。
        values['esim_balance'] = partner.sudo().esim_balance

        if 'esim_profile_count' in counters:
            values['esim_profile_count'] = request.env['esim.profile'].sudo().search_count(
                [('partner_id', '=', partner.id)]
            )
        if 'esim_order_count' in counters:
            values['esim_order_count'] = request.env['esim.order'].sudo().search_count(
                [('partner_id', '=', partner.id)]
            )
        return values

    # ── 套餐浏览 ─────────────────────────────────────────

    @http.route('/my/esim/packages', type='http', auth='user', website=True)
    def portal_esim_packages(
        self,
        page=1,
        location='',
        name='',
        duration='',
        volume='',
        data_type='',
        **kw,
    ):
        """浏览可购买的 eSIM 套餐"""
        location = self._normalize_filter_value(location)
        name = self._normalize_filter_value(name)
        duration = self._normalize_filter_value(duration)
        volume = self._normalize_filter_value(volume)
        data_type = self._normalize_filter_value(data_type)

        domain = [('is_published', '=', True), ('package_type', '=', 'BASE'), ('active', '=', True)]
        if location:
            domain.append(('location', 'ilike', location))
        if name:
            domain.append(('name', 'ilike', name))
        if duration:
            duration_value, _, duration_unit = duration.partition('|')
            if duration_value.isdigit() and duration_unit:
                domain.extend([
                    ('duration', '=', int(duration_value)),
                    ('duration_unit', '=', duration_unit),
                ])
        if volume:
            try:
                domain.append(('volume', '=', float(volume)))
            except ValueError:
                volume = ''
        if data_type:
            domain.append(('data_type', '=', data_type))

        Package = request.env['esim.package'].sudo()
        all_packages = Package.search([
            ('is_published', '=', True),
            ('package_type', '=', 'BASE'),
            ('active', '=', True),
        ], order='location, volume, duration')
        package_count = Package.search_count(domain)

        filter_args = {
            'location': location,
            'name': name,
            'duration': duration,
            'volume': volume,
            'data_type': data_type,
        }

        pager = portal_pager(
            url='/my/esim/packages',
            url_args=filter_args,
            total=package_count,
            page=page,
            step=PACKAGES_PER_PAGE,
        )

        packages = Package.search(domain, limit=PACKAGES_PER_PAGE, offset=pager['offset'],
                                  order='location, volume, duration')

        all_locations = set()
        all_durations = {}
        all_volumes = {}
        for pkg in all_packages:
            if pkg.location:
                for loc in pkg.location.split(','):
                    all_locations.add(loc.strip())
            duration_option = self._get_package_duration_option(pkg)
            if duration_option:
                all_durations[duration_option['value']] = duration_option
            volume_option = self._get_package_volume_option(pkg)
            if volume_option:
                all_volumes[volume_option['value']] = volume_option

        data_type_map = dict(request.env['esim.package']._fields['data_type'].selection)
        available_data_types = [
            {'value': key, 'label': label}
            for key, label in data_type_map.items()
        ]

        values = {
            'packages': packages,
            'pager': pager,
            'page_name': 'esim_packages',
            'default_url': '/my/esim/packages',
            'current_filters': filter_args,
            'available_locations': sorted(all_locations),
            'available_durations': sorted(all_durations.values(), key=lambda item: item['label']),
            'available_volumes': sorted(all_volumes.values(), key=lambda item: float(item['value'])),
            'available_data_types': available_data_types,
        }
        return request.render('esim_access.portal_esim_packages', values)

    @http.route('/my/esim/packages/<int:package_id>', type='http', auth='user', website=True)
    def portal_esim_package_detail(self, package_id, **kw):
        """套餐详情页"""
        package = request.env['esim.package'].sudo().browse(package_id)
        if not package.exists() or not package.is_published:
            raise MissingError(_("套餐不存在"))

        partner = self._get_portal_partner()
        values = {
            'package': package,
            'esim_balance': partner.sudo().esim_balance,
            'page_name': 'esim_package_detail',
        }
        return request.render('esim_access.portal_esim_package_detail', values)

    # ── 下单 ─────────────────────────────────────────────

    @http.route('/my/esim/order', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def portal_esim_order(self, package_id, quantity=1, period_num=0, **kw):
        """门户下单"""
        partner = self._get_portal_partner()
        package = request.env['esim.package'].sudo().browse(int(package_id))
        if not package.exists() or not package.is_published:
            raise MissingError(_("套餐不存在"))

        quantity = max(int(quantity), 1)
        period_num = max(int(period_num), 0)

        vals = {
            'partner_id': partner.id,
            'package_id': package.id,
            'quantity': quantity,
        }
        if period_num:
            vals['period_num'] = period_num

        order = request.env['esim.order'].sudo().create(vals)

        try:
            order.action_confirm()
        except UserError as e:
            values = {
                'package': package,
                'error_message': str(e),
                'page_name': 'esim_package_detail',
            }
            return request.render('esim_access.portal_esim_package_detail', values)

        return request.redirect(f'/my/esim/orders/{order.id}')

    # ── 我的订单 ─────────────────────────────────────────

    @http.route('/my/esim/orders', type='http', auth='user', website=True)
    def portal_esim_orders(self, page=1, **kw):
        """我的 eSIM 订单列表"""
        partner = self._get_portal_partner()
        Order = request.env['esim.order'].sudo()
        domain = [('partner_id', '=', partner.id)]

        order_count = Order.search_count(domain)
        pager = portal_pager(
            url='/my/esim/orders',
            total=order_count,
            page=page,
            step=PROFILES_PER_PAGE,
        )
        orders = Order.search(domain, limit=PROFILES_PER_PAGE, offset=pager['offset'],
                              order='create_date desc')

        values = {
            'orders': orders,
            'pager': pager,
            'page_name': 'esim_orders',
            'default_url': '/my/esim/orders',
        }
        return request.render('esim_access.portal_esim_orders', values)

    @http.route('/my/esim/orders/<int:order_id>', type='http', auth='user', website=True)
    def portal_esim_order_detail(self, order_id, **kw):
        """订单详情"""
        partner = self._get_portal_partner()
        order = request.env['esim.order'].sudo().browse(order_id)
        if not order.exists() or order.partner_id.commercial_partner_id != partner:
            raise AccessError(_("无权访问此订单"))

        values = {
            'order': order,
            'page_name': 'esim_order_detail',
            'success_message': _("订单取消成功，相关 eSIM 已取消并完成退款。")
                               if kw.get('cancelled') else '',
            'error_message': '',
        }
        return request.render('esim_access.portal_esim_order_detail', values)

    @http.route('/my/esim/orders/<int:order_id>/cancel', type='http', auth='user',
                website=True, methods=['POST'], csrf=True)
    def portal_esim_order_cancel(self, order_id, **kw):
        """门户取消订单"""
        partner = self._get_portal_partner()
        order = request.env['esim.order'].sudo().browse(order_id)
        if not order.exists() or order.partner_id.commercial_partner_id != partner:
            raise AccessError(_("无权操作此订单"))

        try:
            order.action_cancel()
        except UserError as e:
            values = {
                'order': order,
                'page_name': 'esim_order_detail',
                'success_message': '',
                'error_message': str(e),
            }
            return request.render('esim_access.portal_esim_order_detail', values)

        return request.redirect(f'/my/esim/orders/{order.id}?cancelled=1')

    # ── 我的 eSIM ────────────────────────────────────────

    @http.route('/my/esim/profiles', type='http', auth='user', website=True)
    def portal_esim_profiles(self, page=1, **kw):
        """我的 eSIM 列表"""
        partner = self._get_portal_partner()
        Profile = request.env['esim.profile'].sudo()
        domain = [('partner_id', '=', partner.id)]

        profile_count = Profile.search_count(domain)
        pager = portal_pager(
            url='/my/esim/profiles',
            total=profile_count,
            page=page,
            step=PROFILES_PER_PAGE,
        )
        profiles = Profile.search(domain, limit=PROFILES_PER_PAGE, offset=pager['offset'],
                                  order='create_date desc')

        values = {
            'profiles': profiles,
            'pager': pager,
            'page_name': 'esim_profiles',
            'default_url': '/my/esim/profiles',
        }
        return request.render('esim_access.portal_esim_profiles', values)

    @http.route('/my/esim/profiles/<int:profile_id>', type='http', auth='user', website=True)
    def portal_esim_profile_detail(self, profile_id, **kw):
        """eSIM 详情页"""
        partner = self._get_portal_partner()
        profile = request.env['esim.profile'].sudo().browse(profile_id)
        if not profile.exists() or profile.partner_id.commercial_partner_id != partner:
            raise AccessError(_("无权访问此 eSIM"))

        # 获取可用的充值套餐
        topup_packages = []
        if profile.state in ('ready', 'active') and profile.iccid:
            topup_packages = request.env['esim.package'].sudo().search([
                ('package_type', '=', 'topup'),
                ('is_published', '=', True),
                ('active', '=', True),
            ])

        values = {
            'profile': profile,
            'topup_packages': topup_packages,
            'page_name': 'esim_profile_detail',
        }
        return request.render('esim_access.portal_esim_profile_detail', values)

    # ── 充值 ─────────────────────────────────────────────

    @http.route('/my/esim/topup/<int:profile_id>', type='http', auth='user',
                website=True, methods=['POST'], csrf=True)
    def portal_esim_topup(self, profile_id, package_id, **kw):
        """门户充值"""
        partner = self._get_portal_partner()
        profile = request.env['esim.profile'].sudo().browse(profile_id)
        if not profile.exists() or profile.partner_id.commercial_partner_id != partner:
            raise AccessError(_("无权操作此 eSIM"))

        package = request.env['esim.package'].sudo().browse(int(package_id))
        if not package.exists() or package.package_type != 'TOPUP':
            raise MissingError(_("充值套餐不存在"))

        topup = request.env['esim.topup'].sudo().create({
            'profile_id': profile.id,
            'partner_id': partner.id,
            'package_id': package.id,
        })

        try:
            topup.action_topup()
        except UserError as e:
            topup_packages = request.env['esim.package'].sudo().search([
                ('package_type', '=', 'TOPUP'),
                ('is_published', '=', True),
                ('active', '=', True),
            ])
            values = {
                'profile': profile,
                'topup_packages': topup_packages,
                'error_message': str(e),
                'page_name': 'esim_profile_detail',
            }
            return request.render('esim_access.portal_esim_profile_detail', values)

        return request.redirect(f'/my/esim/profiles/{profile.id}')

    # ── 余额与交易记录 ─────────────────────────────────────

    @http.route('/my/esim/balance', type='http', auth='user', website=True)
    def portal_esim_balance(self, page=1, **kw):
        """余额与交易记录页"""
        partner = self._get_portal_partner()
        BalanceLog = request.env['esim.balance.log'].sudo()
        domain = [('partner_id', '=', partner.id)]

        log_count = BalanceLog.search_count(domain)
        pager = portal_pager(
            url='/my/esim/balance',
            total=log_count,
            page=page,
            step=TRANSACTIONS_PER_PAGE,
        )
        logs = BalanceLog.search(
            domain, limit=TRANSACTIONS_PER_PAGE, offset=pager['offset'],
            order='create_date desc',
        )

        values = {
            'logs': logs,
            'esim_balance': partner.sudo().esim_balance,
            'pager': pager,
            'page_name': 'esim_balance',
            'default_url': '/my/esim/balance',
        }
        return request.render('esim_access.portal_esim_balance', values)
