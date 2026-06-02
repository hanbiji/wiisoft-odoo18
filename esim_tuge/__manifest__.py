# -*- coding: utf-8 -*-
{
    'name': '途鸽 Tuge eSIM 集成',
    'version': '19.0.1.0.0',
    'summary': '对接途鸽科技 eSIM API，与 esim_access 共用 Portal 销售与订单体系',
    'description': '集成途鸽全球云通信 eSIM 平台，支持套餐同步、下单、异步回调、'
                   'Profile 管理与 Portal 展示，复用 esim_access 余额/支付/分销能力。',
    'author': 'WiiSoft',
    'license': 'LGPL-3',
    'category': 'Services',
    'depends': ['esim_access'],
    'data': [
        'data/ir_cron.xml',
        'views/esim_config_views.xml',
        'views/esim_package_views.xml',
        'views/esim_order_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
