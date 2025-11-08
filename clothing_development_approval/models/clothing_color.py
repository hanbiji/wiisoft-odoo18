# -*- coding: utf-8 -*-
# Copyright 2025 WiiSoft
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl.html).

from odoo import models, fields, api, _


class ClothingColor(models.Model):
    """服装颜色模型
    
    用于存储服装颜色的名称和对应的颜色代码。
    """
    _name = 'clothing.color'
    _description = '服装颜色'
    _order = 'name'
    _rec_name = 'name'
    
    name = fields.Char(
        string='颜色名称',
        required=True,
        help='颜色的名称，如红色、蓝色等'
    )
    
    color_code = fields.Char(
        string='颜色代码',
        required=True,
        help='颜色的英文代码，如RD表示红色'
    )
    
    active = fields.Boolean(
        string='有效',
        default=True,
        help='设置颜色是否可用'
    )
    
    description = fields.Text(
        string='描述',
        help='关于此颜色的额外描述信息'
    )
    
    _sql_constraints = [
        ('name_uniq', 'unique(name)', '颜色名称必须唯一！'),
        ('color_code_uniq', 'unique(color_code)', '颜色代码必须唯一！'),
    ]