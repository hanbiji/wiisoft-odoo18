# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ClothingDesignReference(models.Model):
    """服装设计参考图片模型"""
    _name = 'clothing.design.reference'
    _description = '服装设计参考图片'

    # ========== 基本信息字段 ==========
    name = fields.Char(
        string='图片名称',
        help='设计参考图片的名称',
        default=lambda self: _('参考图片')
    )
    
    image = fields.Image(
        string='参考图片',
        required=True,
        help='设计参考图片文件'
    )
    
    # ========== 关联字段 ==========
    request_id = fields.Many2one(
        'clothing.development.request',
        string='关联申请',
        ondelete='cascade',
        help='关联的服装开发申请'
    )

    @api.constrains('image')
    def _check_image(self):
        """验证必须上传图片"""
        for record in self:
            if not record.image:
                raise ValidationError(_('必须上传参考图片'))

# 设计稿图
class ClothingDesignDraft(models.Model):
    """服装设计草稿模型"""
    _name = 'clothing.design.draft'
    _description = '服装设计草稿'

    # ========== 基本信息字段 ==========
    name = fields.Char(
        string='草稿名称',
        help='设计草稿的名称',
        default=lambda self: _('设计草稿')
    )
    
    image = fields.Image(
        string='草稿图片',
        required=True,
        help='设计草稿图片文件'
    )
    
    # ========== 关联字段 ==========
    request_id = fields.Many2one(
        'clothing.development.request',
        string='关联申请',
        ondelete='cascade',
        help='关联的服装开发申请'
    )

    @api.constrains('image')
    def _check_image(self):
        """验证必须上传图片"""
        for record in self:
            if not record.image:
                raise ValidationError(_('必须上传设计草稿图片'))

# 打板图
class ClothingDesignBoard(models.Model):
    """服装设计打板图模型"""
    _name = 'clothing.design.board'
    _description = '服装设计打板图'

    # ========== 基本信息字段 ==========
    name = fields.Char(
        string='打板名称',
        help='设计打板图的名称',
        default=lambda self: _('打板图')
    )
    
    image = fields.Image(
        string='打板图片',
        required=True,
        help='设计打板图文件'
    )
    
    # ========== 关联字段 ==========
    request_id = fields.Many2one(
        'clothing.development.request',
        string='关联申请',
        ondelete='cascade',
        help='关联的服装开发申请'
    )

    @api.constrains('image')
    def _check_image(self):
        """验证必须上传图片"""
        for record in self:
            if not record.image:
                raise ValidationError(_('必须上传设计打板图'))

# 样衣挂板图
class ClothingDesignSample(models.Model):
    """服装设计样衣挂板图模型"""
    _name = 'clothing.design.sample'
    _description = '服装设计样衣挂板图'

    # ========== 基本信息字段 ==========
    name = fields.Char(
        string='样衣挂板名称',
        help='设计样衣挂板图的名称',
        default=lambda self: _('样衣挂板图')
    )
    
    image = fields.Image(
        string='样衣挂板图片',
        required=True,
        help='设计样衣挂板图文件'
    )
    
    # ========== 关联字段 ==========
    request_id = fields.Many2one(
        'clothing.development.request',
        string='关联申请',
        ondelete='cascade',
        help='关联的服装开发申请'
    )

    @api.constrains('image')
    def _check_image(self):
        """验证必须上传图片"""
        for record in self:
            if not record.image:
                raise ValidationError(_('必须上传设计样衣挂板图'))
