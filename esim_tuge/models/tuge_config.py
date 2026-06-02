# -*- coding: utf-8 -*-
from odoo import models, fields, api, _

DEFAULT_TUGE_BASE_URL = 'https://enterpriseapisandbox.tugegroup.com:8070/openapi'


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    tuge_account_id = fields.Char(
        string="途鸽 Account ID",
        config_parameter='tuge.account_id',
    )
    tuge_secret = fields.Char(
        string="途鸽 Secret",
        config_parameter='tuge.secret',
    )
    tuge_base_url = fields.Char(
        string="途鸽 API 基础 URL",
        config_parameter='tuge.base_url',
        default=DEFAULT_TUGE_BASE_URL,
    )
    tuge_callback_secret = fields.Char(
        string="途鸽回调验签 Secret",
        config_parameter='tuge.callback_secret',
        help="用于验证途鸽 Webhook 回调的 MD5 签名，通常与 API Secret 相同",
    )
    tuge_default_markup = fields.Float(
        string="途鸽默认加价比例",
        config_parameter='tuge.default_markup',
        default=1.3,
        help="售价 = 成本价(netPrice) × 加价比例",
    )

    def action_tuge_sync_packages(self):
        """从设置页触发途鸽套餐同步。"""
        count = self.env['esim.package']._sync_tuge_packages_from_api()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("途鸽套餐同步完成"),
                'message': _("共同步 %d 个套餐") % count,
                'type': 'success',
                'sticky': False,
            },
        }
