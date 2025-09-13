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
    _rec_name = 'display_name'
    
    # ========== 基本信息字段 ==========
    clothing_type = fields.Selection([
        ('ski_jacket', '滑雪上衣'),
        ('ski_pants', '滑雪裤子'),
        ('ski_suit', '连体滑雪套装'),
        ('shirt', '衬衫'),
        ('pants', '裤子'),
        ('dress', '连衣裙'),
        ('jacket', '外套'),
        ('skirt', '裙子'),
        ('suit', '套装'),
    ], string='服装类型', required=True, help='选择服装的类型')
    
    target_gender = fields.Selection([
        ('male', '男性'),
        ('female', '女性'),
        ('unisex', '中性'),
         ('child', '儿童')
    ], string='目标性别', required=True, help='该尺寸适用的性别')
    
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
            record.display_name = f"{clothing_type_label} - {gender_label} - {size_label}"
