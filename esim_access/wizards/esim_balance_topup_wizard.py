# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class EsimBalanceTopupWizard(models.TransientModel):
    _name = 'esim.balance.topup.wizard'
    _description = '客户余额充值向导'

    partner_id = fields.Many2one(
        'res.partner', string="客户", required=True,
    )
    currency_id = fields.Many2one(
        'res.currency', string="币种", required=True,
        default=lambda self: self.env['esim.package']._get_fallback_shop_currency().id,
        domain=[('active', '=', True)],
    )
    current_balance = fields.Monetary(
        string="当前余额", currency_field='currency_id',
        compute='_compute_current_balance',
    )
    amount = fields.Monetary(
        string="充值金额", currency_field='currency_id', required=True,
    )
    note = fields.Char(string="备注")

    @api.depends('partner_id', 'currency_id')
    def _compute_current_balance(self) -> None:
        for wizard in self:
            if wizard.partner_id and wizard.currency_id:
                wizard.current_balance = wizard.partner_id._esim_get_balance(wizard.currency_id)
            else:
                wizard.current_balance = 0.0

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
            currency=self.currency_id,
        )
        balance_after = self.partner_id._esim_get_balance(self.currency_id)
        symbol = self.currency_id.symbol or self.currency_id.name
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("充值成功"),
                'message': _("已为 %s 充值 %s%.2f，当前余额 %s%.2f") % (
                    self.partner_id.name, symbol, self.amount, symbol, balance_after,
                ),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
