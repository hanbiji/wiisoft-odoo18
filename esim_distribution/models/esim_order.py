# -*- coding: utf-8 -*-
from odoo import models, fields, _


class EsimOrder(models.Model):
    _inherit = 'esim.order'

    commission_ids = fields.One2many(
        'esim.commission', 'order_id', string="分销佣金",
    )
    commission_count = fields.Integer(
        string="佣金记录数", compute='_compute_commission_count',
    )

    def _compute_commission_count(self) -> None:
        for order in self:
            order.commission_count = len(order.commission_ids)

    def write(self, vals: dict) -> bool:
        state_changed = 'state' in vals
        old_states = {order.id: order.state for order in self} if state_changed else {}
        result = super().write(vals)
        if state_changed:
            for order in self:
                old_state = old_states.get(order.id)
                if old_state != 'done' and order.state == 'done':
                    order._distribution_generate_commission()
                elif old_state != 'cancelled' and order.state == 'cancelled':
                    order._distribution_cancel_commission()
        return result

    def _distribution_generate_commission(self) -> None:
        """订单完成时生成冻结佣金，比例取订单完成瞬间的分销等级快照。"""
        Commission = self.env['esim.commission'].sudo()
        for order in self:
            partner = order.partner_id.commercial_partner_id
            distributor = partner.referrer_distributor_id
            if (
                not distributor
                or distributor.state != 'approved'
                or not distributor.tier_id
                or order.total_amount <= 0
            ):
                continue
            if distributor.partner_id.commercial_partner_id == partner:
                continue
            if Commission.search_count([
                ('order_id', '=', order.id),
                ('distributor_id', '=', distributor.id),
            ]):
                continue

            commission = Commission.create({
                'distributor_id': distributor.id,
                'order_id': order.id,
                'source_partner_id': partner.id,
                'order_amount': order.total_amount,
                'currency_id': order.currency_id.id,
                'tier_id_snapshot': distributor.tier_id.id,
                'commission_rate': distributor.tier_id.commission_rate,
            })
            order.message_post(
                body=_("已生成分销佣金 %(commission)s，冻结至 %(date)s。") % {
                    'commission': commission.name,
                    'date': fields.Datetime.to_string(commission.lock_release_date),
                }
            )

    def _distribution_cancel_commission(self) -> None:
        for order in self:
            pending_commissions = order.commission_ids.filtered(lambda c: c.state == 'pending')
            if pending_commissions:
                pending_commissions._cancel_pending(_("来源订单已取消。"))
                order.message_post(body=_("已取消该订单关联的待结算分销佣金。"))

    def action_view_commissions(self) -> dict:
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('分销佣金'),
            'res_model': 'esim.commission',
            'view_mode': 'list,form',
            'domain': [('order_id', '=', self.id)],
            'context': {'default_order_id': self.id},
        }
