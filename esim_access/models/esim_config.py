# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    esim_access_code = fields.Char(
        string="Access Code",
        config_parameter='esim_access.access_code',
    )
    esim_secret_key = fields.Char(
        string="Secret Key",
        config_parameter='esim_access.secret_key',
    )
    esim_api_base_url = fields.Char(
        string="API 基础 URL",
        config_parameter='esim_access.api_base_url',
        default='https://api.esimaccess.com/api/v1',
    )
    esim_webhook_secret = fields.Char(
        string="Webhook 验证密钥",
        config_parameter='esim_access.webhook_secret',
    )
    esim_default_markup = fields.Float(
        string="默认加价比例",
        config_parameter='esim_access.default_markup',
        default=1.3,
        help="售价 = 成本价 × 加价比例，如 1.3 表示加价 30%",
    )

    def action_esim_sync_all_packages(self):
        """从设置页面触发拉取全部套餐"""
        count = self.env['esim.package']._sync_packages_from_api()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("套餐同步完成"),
                'message': _("共同步 %d 个套餐") % count,
                'type': 'success',
                'sticky': False,
            },
        }
