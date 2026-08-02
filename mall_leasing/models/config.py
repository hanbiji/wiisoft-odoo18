# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    vacancy_threshold = fields.Float(
        '空置率预警阈值(%)',
        config_parameter='mall_leasing.vacancy_threshold',
        default=30.0,
    )

    @api.model
    def cron_vacancy_warning(self) -> bool:
        """空置率超过阈值时，向当前公司创建待办活动。"""
        Facade = self.env['mall.facade']
        total = Facade.search_count([])
        if total == 0:
            return True
        vacant = Facade.search_count([('status', '=', 'vacant')])
        rate = (vacant / total) * 100.0
        threshold = float(
            self.env['ir.config_parameter'].sudo().get_param(
                'mall_leasing.vacancy_threshold', 30.0
            )
        )
        if rate >= threshold:
            company = self.env.company
            # Odoo 19：为活动指定负责人，避免无指派人的“漂浮”活动
            self.env['mail.activity'].create({
                'res_model_id': self.env['ir.model']._get('res.company').id,
                'res_id': company.id,
                'activity_type_id': self.env.ref('mail.mail_activity_data_todo').id,
                'user_id': self.env.user.id,
                'summary': _('空置率预警'),
                'note': _(
                    '当前共有 %s 个门面空置，空置率 %.1f%% 已超过阈值 %.1f%%。'
                ) % (vacant, rate, threshold),
            })
        return True
