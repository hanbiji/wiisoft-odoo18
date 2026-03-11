# -*- coding: utf-8 -*-
from odoo import models, fields, api


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
