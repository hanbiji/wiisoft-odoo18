# -*- coding: utf-8 -*-
from odoo import api, fields, models, _

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    vacancy_threshold = fields.Float('空置率预警阈值(%)', config_parameter='mall_leasing.vacancy_threshold', default=30.0)

    @api.model
    def cron_vacancy_warning(self):
        Facade = self.env['mall.facade']
        total = Facade.search_count([])
        if total == 0:
            return True
        vacant = Facade.search_count([('status', '=', 'vacant')])
        rate = (vacant / total) * 100.0
        threshold = float(self.env['ir.config_parameter'].sudo().get_param('mall_leasing.vacancy_threshold', 30.0))
        if rate >= threshold:
            summary = _('空置率预警')
            note = _('当前共有 %s 个门面空置，空置率 %.1f%% 已超过阈值 %.1f%%。') % (vacant, rate, threshold)
            company = self.env.company
            self.env['mail.activity'].create({
                'res_model_id': self.env['ir.model']._get('res.company').id,
                'res_id': company.id,
                'activity_type_id': self.env.ref('mail.mail_activity_data_todo').id,
                'summary': summary,
                'note': note,
            })
        return True