# -*- coding: utf-8 -*-
{
    'name': '服装开发审批流程',
    'version': '18.0.1.0.0',
    'category': 'Manufacturing',
    'summary': '服装开发审批流程管理模块',
    'description': """
服装开发审批流程管理
====================

本模块提供服装开发过程中的审批流程管理功能，包括：

* 开发申请管理
* 审批流程控制
* 状态跟踪
* 权限管理

主要功能：
---------
* 创建和管理服装开发申请
* 多级审批流程
* 审批历史记录
* 状态实时跟踪
* 权限控制和角色管理
    """,
    'author': 'WiiSoft',
    'website': 'https://www.wiisoft.com',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'portal',
        'hr',
        'web',
    ],
    'data': [
        # 安全配置
        'security/security.xml',
        'security/ir.model.access.csv',
        
        # 数据文件
        'data/sequence.xml',
        'data/data.xml',        
        # 视图文件
        'views/clothing_development_request_views.xml',
        'views/clothing_color_views.xml',
        'views/clothing_size_views.xml',
        'views/clothing_sku_views.xml',
        'views/clothing_design_reference_views.xml',
        'views/clothing_config_views.xml',
        'views/views.xml',
        'views/menus.xml',
    ],
    'demo': [
        # 演示数据
        # 'demo/demo.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'clothing_development_approval/static/src/js/wiiboard_gallery.js',
            # 'clothing_development_approval/static/src/css/style.css',
        ],
    },
    'installable': True,
    'auto_install': False,
    'application': True,
    'sequence': 100,
}