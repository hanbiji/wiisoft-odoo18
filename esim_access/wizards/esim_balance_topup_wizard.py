# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class EsimBalanceTopupWizard(models.TransientModel):
    _name = 'esim.balance.topup.wizard'
    _description = '客户余额充值向导'

    partner_id = fields.Many2one(
        'res.partner', string="客户", required=True,
    )
    current_balance = fields.Float(
        string="当前余额", digits=(12, 2),
        related='partner_id.esim_balance', readonly=True,
    )
    amount = fields.Float(
        string="充值金额", digits=(12, 2), required=True,
    )
    note = fields.Char(string="备注")

    def action_topup(self) -> dict:
        """执行充值"""
        self.ensure_one()
        if self.amount <= 0:
            raise UserError(_("充值金额必须大于 0"))

        description = _("管理员充值")
        if self.note:
            description = f"{description} - {self.note}"

        self.partner_id._esim_change_balance(
            log_type='topup',
            amount=self.amount,
            description=description,
        )
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("充值成功"),
                'message': _("已为 %s 充值 $%.2f，当前余额 $%.2f") % (
                    self.partner_id.name, self.amount, self.partner_id.esim_balance,
                ),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
