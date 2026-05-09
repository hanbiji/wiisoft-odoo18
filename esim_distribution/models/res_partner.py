# -*- coding: utf-8 -*-
from odoo import models, fields, _
from odoo.exceptions import UserError


class ResPartner(models.Model):
    _inherit = 'res.partner'

    referrer_distributor_id = fields.Many2one(
        'esim.distributor', string="推荐分销商",
        ondelete='set null', index=True, tracking=True,
        help="该客户首次通过推广链接绑定的分销商。绑定后不自动覆盖。",
    )
    distributor_ids = fields.One2many(
        'esim.distributor', 'partner_id', string="分销商档案",
    )

    def _bind_referrer_once(self, distributor: 'EsimDistributor') -> bool:
        """仅在客户没有推荐人时绑定，避免后续访问推广链接覆盖真实来源。"""
        self.ensure_one()
        commercial_partner = self.commercial_partner_id
        if distributor.state != 'approved':
            raise UserError(_("只能绑定已审核通过的分销商。"))
        if commercial_partner == distributor.partner_id.commercial_partner_id:
            return False
        if commercial_partner.referrer_distributor_id:
            return False
        commercial_partner.sudo().write({'referrer_distributor_id': distributor.id})
        return True
