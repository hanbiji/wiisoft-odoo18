# -*- coding: utf-8 -*-
{
    'name': 'Mall Leasing 管理',
    'version': '1.0',
    'summary': '商场门面租赁项目管理（门面/合同/财务/预警/CRM）',
    'description': '管理门面、双合同（房东/租户）、自动账单、到期与欠费预警、租户档案与沟通日志。',
    'author': 'wiisoft',
    'website': 'https://example.com',
    'license': 'LGPL-3',
    'depends': ['base', 'mail', 'contacts', 'account'],
    'data': [
        'security/ir.model.access.csv',
        'views/mall_views.xml',
        'views/facade_views.xml',
        'views/contract_views.xml',
        'views/contract_template_views.xml',
        'views/res_partner_views.xml',
        'views/communication_views.xml',
        'data/ir_cron.xml',
        'views/menu.xml',
    ],
    'application': True,
}