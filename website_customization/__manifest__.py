# -*- coding: utf-8 -*-
{
    'name': '网站定制',
    'version': '18.0.1.0.0',
    'summary': '隐藏网站底部Odoo版权信息',
    'description': '移除网站页面底部的 "由 Odoo 提供支持" 版权信息。',
    'author': 'wiisoft',
    'website': 'https://example.com',
    'license': 'LGPL-3',
    'category': 'Website',
    'depends': ['website'],
    'data': [
        'views/website_templates.xml',
    ],
    'installable': True,
    'auto_install': False,
}

