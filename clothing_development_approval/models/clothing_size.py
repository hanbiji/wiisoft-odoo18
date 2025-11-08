# -*- coding: utf-8 -*-
# Copyright 2025 WiiSoft
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl.html).

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ClothingSize(models.Model):
    """服装尺寸模型
    
    用于管理不同服装类型和性别的尺寸规格信息。
    """
    _name = 'clothing.size'
    _description = '服装尺寸'
    _order = 'clothing_type, target_gender, size'
    _rec_name = 'size'
    
    # ========== 基本信息字段 ==========
    clothing_type = fields.Selection([
        ('SU', 'One-piece suit - 连体'),
        ('JK', 'Jacket - 夹克'),
        ('PT', 'Pants - 裤子'),
        ('BB', 'Bibs - 背带裤'),
        ('GG', 'Goggles - 雪镜'),
        ('HM', 'Helmet - 头盔'),
        ('GL', 'Gloves - 手套'),
        ('SK', 'Socks - 袜子')
    ], string='服装分类', required=True)
    
    target_gender = fields.Selection([
        ('M', 'Men - 男'),
        ('W', 'Women - 女'),
        ('U', 'Unisex - 中性'),
        ('K', 'Kids - 小孩')
    ], string='目标性别', required=True)
    
    size = fields.Char(
        string='尺寸',
        required=True,
        help='服装尺寸规格'
    )

    # ========== 计算字段 ==========
    display_name = fields.Char(
        string='显示名称',
        compute='_compute_display_name',
        store=True,
        help='用于显示的完整名称'
    )
    
    @api.depends('clothing_type', 'target_gender', 'size')
    def _compute_display_name(self):
        """计算显示名称"""
        for record in self:
            clothing_type_label = dict(record._fields['clothing_type'].selection).get(record.clothing_type, '')
            gender_label = dict(record._fields['target_gender'].selection).get(record.target_gender, '')
            size_label = record.size
            record.display_name = f"{size_label}"
