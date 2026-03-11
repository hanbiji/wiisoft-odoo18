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


class EsimPortal(CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        partner = request.env.user.partner_id

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
    def portal_esim_packages(self, page=1, location='', **kw):
        """浏览可购买的 eSIM 套餐"""
        domain = [('is_published', '=', True), ('package_type', '=', 'BASE'), ('active', '=', True)]
        if location:
            domain.append(('location', 'ilike', location))

        Package = request.env['esim.package'].sudo()
        package_count = Package.search_count(domain)

        pager = portal_pager(
            url='/my/esim/packages',
            url_args={'location': location},
            total=package_count,
            page=page,
            step=PACKAGES_PER_PAGE,
        )

        packages = Package.search(domain, limit=PACKAGES_PER_PAGE, offset=pager['offset'],
                                  order='location, volume, duration')

        # 收集所有可用地区供筛选
        all_locations = set()
        all_packages = Package.search([('is_published', '=', True), ('package_type', '=', 'BASE')])
        for pkg in all_packages:
            if pkg.location:
                for loc in pkg.location.split(','):
                    all_locations.add(loc.strip())

        values = {
            'packages': packages,
            'pager': pager,
            'page_name': 'esim_packages',
            'default_url': '/my/esim/packages',
            'current_location': location,
            'available_locations': sorted(all_locations),
        }
        return request.render('esim_access.portal_esim_packages', values)

    @http.route('/my/esim/packages/<int:package_id>', type='http', auth='user', website=True)
    def portal_esim_package_detail(self, package_id, **kw):
        """套餐详情页"""
        package = request.env['esim.package'].sudo().browse(package_id)
        if not package.exists() or not package.is_published:
            raise MissingError(_("套餐不存在"))

        values = {
            'package': package,
            'page_name': 'esim_package_detail',
        }
        return request.render('esim_access.portal_esim_package_detail', values)

    # ── 下单 ─────────────────────────────────────────────

    @http.route('/my/esim/order', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def portal_esim_order(self, package_id, quantity=1, period_num=0, **kw):
        """门户下单"""
        partner = request.env.user.partner_id
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
        partner = request.env.user.partner_id
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
        partner = request.env.user.partner_id
        order = request.env['esim.order'].sudo().browse(order_id)
        if not order.exists() or order.partner_id != partner:
            raise AccessError(_("无权访问此订单"))

        values = {
            'order': order,
            'page_name': 'esim_order_detail',
        }
        return request.render('esim_access.portal_esim_order_detail', values)

    # ── 我的 eSIM ────────────────────────────────────────

    @http.route('/my/esim/profiles', type='http', auth='user', website=True)
    def portal_esim_profiles(self, page=1, **kw):
        """我的 eSIM 列表"""
        partner = request.env.user.partner_id
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
        partner = request.env.user.partner_id
        profile = request.env['esim.profile'].sudo().browse(profile_id)
        if not profile.exists() or profile.partner_id != partner:
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
        partner = request.env.user.partner_id
        profile = request.env['esim.profile'].sudo().browse(profile_id)
        if not profile.exists() or profile.partner_id != partner:
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
