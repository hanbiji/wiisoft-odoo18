# -*- coding: utf-8 -*-
{
    'name': 'eSIM 在线支付',
    'version': '19.0.2.0.0',
    'summary': '通过在线支付为 eSIM 余额充值 & 购买套餐',
    'description': '桥接 esim_access 与 payment 模块，'
                   '支持客户在门户通过在线支付网关完成余额充值和套餐购买。',
    'author': 'WiiSoft',
    'license': 'LGPL-3',
    'category': 'Services',
    'depends': ['esim_access', 'payment'],
    'data': [
        'security/esim_recharge_security.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence.xml',
        'data/esim_recharge_option_data.xml',
        'views/esim_recharge_option_views.xml',
        'views/esim_balance_recharge_views.xml',
        'views/portal_recharge_templates.xml',
        'views/portal_package_pay_templates.xml',
        'views/portal_balance_inherit.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'auto_install': False,
}
