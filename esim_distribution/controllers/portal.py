# -*- coding: utf-8 -*-
from werkzeug.exceptions import NotFound

from odoo import http
from odoo.http import request
from odoo.addons.portal.controllers.portal import pager as portal_pager
from odoo.addons.esim_access.controllers.portal import EsimPortal

COMMISSIONS_PER_PAGE = 20
REFERRER_SESSION_KEY = 'esim_distribution_referrer_code'


class EsimDistributionPortal(EsimPortal):
    """门户分销中心：申请、推广链接绑定和佣金记录查询。"""

    def _prepare_home_portal_values(self, counters):
        self._consume_referrer_session()
        values = super()._prepare_home_portal_values(counters)
        partner = self._get_portal_partner()
        distributor = self._get_partner_distributor(partner)
        values['esim_distributor'] = distributor
        if 'esim_commission_count' in counters:
            values['esim_commission_count'] = request.env['esim.commission'].sudo().search_count([
                ('distributor_id', '=', distributor.id),
            ]) if distributor else 0
        return values

    @staticmethod
    def _get_partner_distributor(partner):
        return request.env['esim.distributor'].sudo().search([
            ('partner_id', '=', partner.id),
        ], limit=1)

    @staticmethod
    def _get_approved_distributor_by_code(code: str):
        return request.env['esim.distributor'].sudo().search([
            ('referral_code', '=', (code or '').strip().upper()),
            ('state', '=', 'approved'),
        ], limit=1)

    def _consume_referrer_session(self) -> bool:
        """登录后消费推广码 session，只做一次性绑定并立即清除。"""
        if request.env.user._is_public():
            return False
        code = request.session.pop(REFERRER_SESSION_KEY, None)
        if not code:
            return False
        distributor = self._get_approved_distributor_by_code(code)
        if not distributor:
            return False
        return request.env.user.partner_id._bind_referrer_once(distributor)

    @http.route('/distribution/r/<string:code>', type='http', auth='public', website=True)
    def distribution_referral_redirect(self, code, **kw):
        distributor = self._get_approved_distributor_by_code(code)
        if not distributor:
            raise NotFound()

        if request.env.user._is_public():
            request.session[REFERRER_SESSION_KEY] = distributor.referral_code
            return request.redirect('/web/login?redirect=/my/distribution')

        request.env.user.partner_id._bind_referrer_once(distributor)
        return request.redirect('/my/esim/packages')

    @http.route('/my/distribution', type='http', auth='user', website=True)
    def portal_distribution_home(self, **kw):
        self._consume_referrer_session()
        partner = self._get_portal_partner()
        distributor = self._get_partner_distributor(partner)
        recent_commissions = request.env['esim.commission'].sudo().search([
            ('distributor_id', '=', distributor.id),
        ], limit=5, order='create_date desc') if distributor else request.env['esim.commission'].browse()

        return request.render('esim_distribution.portal_distribution_home', {
            'page_name': 'esim_distribution',
            'default_url': '/my/distribution',
            'partner': partner,
            'distributor': distributor,
            'recent_commissions': recent_commissions,
        })

    @http.route(
        '/my/distribution/apply',
        type='http', auth='user', website=True,
        methods=['GET', 'POST'],
    )
    def portal_distribution_apply(self, **post):
        self._consume_referrer_session()
        partner = self._get_portal_partner()
        distributor = self._get_partner_distributor(partner)

        if request.httprequest.method == 'POST':
            apply_reason = (post.get('apply_reason') or '').strip()
            if distributor:
                if distributor.state in ('draft', 'rejected'):
                    distributor.sudo().write({'apply_reason': apply_reason})
                    distributor.sudo().action_apply()
            else:
                request.env['esim.distributor'].sudo().create({
                    'partner_id': partner.id,
                    'apply_reason': apply_reason,
                    'state': 'pending',
                })
            return request.redirect('/my/distribution')

        return request.render('esim_distribution.portal_distribution_apply', {
            'page_name': 'esim_distribution_apply',
            'default_url': '/my/distribution/apply',
            'distributor': distributor,
        })

    @http.route(
        ['/my/distribution/commissions', '/my/distribution/commissions/page/<int:page>'],
        type='http', auth='user', website=True,
    )
    def portal_distribution_commissions(self, page=1, **kw):
        self._consume_referrer_session()
        partner = self._get_portal_partner()
        distributor = self._get_partner_distributor(partner)
        Commission = request.env['esim.commission'].sudo()
        domain = [('distributor_id', '=', distributor.id)] if distributor else [('id', '=', 0)]
        commission_count = Commission.search_count(domain)
        pager = portal_pager(
            url='/my/distribution/commissions',
            total=commission_count,
            page=page,
            step=COMMISSIONS_PER_PAGE,
        )
        commissions = Commission.search(
            domain,
            limit=COMMISSIONS_PER_PAGE,
            offset=pager['offset'],
            order='create_date desc',
        )
        return request.render('esim_distribution.portal_distribution_commissions', {
            'page_name': 'esim_distribution_commissions',
            'default_url': '/my/distribution/commissions',
            'distributor': distributor,
            'commissions': commissions,
            'pager': pager,
        })
