# -*- coding: utf-8 -*-
# Copyright 2025 WiiSoft
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl.html).

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError

class ClothingConfig(models.Model):
    _name = 'clothing.config'
    _description = 'Clothing Config'
    _inherit = ['mail.thread']

    name = fields.Char(string='Name', required=True, tracking=True)
    config_code = fields.Char(string='Config Code', required=True, tracking=True)
    config_value = fields.Char(string='Config Value', required=True, tracking=True)
    description = fields.Text(string='描述')
